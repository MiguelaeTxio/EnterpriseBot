# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/date_machine_documents_free.py
"""
H30 (S118), punto 8 de la hoja de ruta -- fechado de los documentos de
máquinas ACTIVAS, PASO GRATIS: sin descargar nada ni llamar a ninguna
API, con lo que ya existe y está validado.

1. Nombre del archivo: `filename_date_service.extract_date_by_filename`
   (criterios confirmados por Miguel Ángel en S48: ITV/OCA caducidad,
   permiso de circulación emisión, recibos del seguro por rango,
   trimestre o fecha simple). Para el resto de tipos, la última fecha
   del nombre (misma convención del corpus: la fecha va al final) se
   toma como EMISIÓN -- nunca como caducidad, que no se puede deducir
   del nombre.
2. Texto ya guardado (`ocr_text`, paso A del punto 7):
   `date_verification_service.classify_dates_in_text`, con el contexto
   de caducidad/emisión alrededor de cada fecha; una única fecha sin
   contexto cuenta como emisión (mismo criterio de verify_typed_date).

Solo rellena huecos: nunca sobrescribe una fecha ya puesta. En un tipo
que NO caduca nunca escribe caducidad. DRY-RUN por defecto; --apply
escribe. Log propio (0bis).
---
S119: antes que todo lo anterior, reglas de fecha por tipo sobre el texto
guardado (`machine_date_rules`), con emisión y caducidad a la vez
cuando el documento trae un periodo.
---
H30 (S118), roadmap item 8 -- FREE dating step for active machines:
file name first, then the cached OCR text. Only fills blanks.
"""
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.date_verification_service import (
    classify_dates_in_text,
)
from document_explorer.filename_date_service import (
    _extract_date,
    _parse_single_date_str,
    extract_date_by_filename,
)
from document_explorer.machine_date_rules import dates_by_rules, normalize
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
# Fechas fuera de este rango son lecturas falsas (códigos, matrículas).
MIN_DATE = date(1980, 1, 1)
MAX_EXPIRY = date(2045, 12, 31)

# S118, corregido tras el dry-run EnterpriseBot_018 -- nombres cuya
# "fecha" es la del escaneo, la de la subida o una hora, nunca la del
# documento: "Scan2025-10-27_094743" (salía caducidad 25/10/2027 en una
# ITV), "doc06476220240320093349", "img20231019_...", "..._20260924"
# (sello de subida del alta), "Imagen de WhatsApp 2024-11-18 a las
# 13.04.08" (salía 13/04/2008 leyendo la hora).
SCANNER_NAME_RE = re.compile(
    r"^(SCAN\d|DOC\d{6,}|IMG\d{6,})|_\d{8}(_\d+)?\.[A-Z]+$",
    re.IGNORECASE,
)
WHATSAPP_RE = re.compile(
    r"WHATSAPP\s+(\d{4})-(\d{2})-(\d{2})", re.IGNORECASE,
)
# "del X al Y" en el nombre: "17-12-20 A 31-12-20".
RANGE_RE = re.compile(
    r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})\s*[aA]\s*"
    r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})",
)


class Command(BaseCommand):
    help = (
        "H30 (S118) -- punto 8, paso gratis: fecha por nombre de "
        "archivo y por texto ya guardado. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._log_plain(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message),
        )

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    def _plausible(self, value, is_expiry):
        today = date.today()
        if value is None or value < MIN_DATE:
            return False
        return value <= (MAX_EXPIRY if is_expiry else today)

    def _track_undated(self, entry, missing_ids):
        """
        Keep entries of expiring types that still have no date at all.
        ---
        Guarda los de tipo que caduca que siguen sin ninguna fecha --
        el criterio de cierre del punto 1 (S119).
        """
        if entry.document_type.tracks_expiry and entry.issue_date is None \
                and entry.expiry_date is None:
            missing_ids.setdefault(
                entry.document_type.code, [],
            ).append(entry)

    def _decide_by_rules(self, entry):
        """
        Return ({field_name: date}, source) from the S119 type rules.
        ---
        S119 (punto 1): reglas por tipo sobre el texto guardado
        (`machine_date_rules`), antes que nombre y texto genérico. Solo
        rellena campos vacíos; nunca escribe caducidad en un tipo que no
        caduca, ni una caducidad anterior a la emisión ya guardada.
        """
        found = dates_by_rules(
            entry.document_type.code, entry.name, entry.ocr_text,
        )
        if not found:
            return {}, None
        updates = {}
        expiry = found["expiry"]
        issue = found["issue"]
        if expiry and entry.document_type.tracks_expiry \
                and entry.expiry_date is None \
                and (entry.issue_date is None or expiry > entry.issue_date):
            updates["expiry_date"] = expiry
        if issue and entry.issue_date is None:
            updates["issue_date"] = issue
        return updates, found["source"]

    def _decide(self, entry):
        """
        Return (field, date, source) or (None, None, None).
        ---
        Decide la fecha a rellenar: primero el nombre, luego el texto.
        """
        dt = entry.document_type
        by_name = None
        whatsapp = WHATSAPP_RE.search(entry.name)
        range_match = RANGE_RE.search(entry.name)
        if whatsapp:
            by_name = ("issue", date(*(int(g) for g in whatsapp.groups())))
        elif SCANNER_NAME_RE.search(entry.name):
            by_name = None
        elif range_match:
            start = _parse_single_date_str(range_match.group(1))
            end = _parse_single_date_str(range_match.group(2))
            if dt.tracks_expiry and end:
                by_name = ("expiry", end)
            elif start:
                by_name = ("issue", start)
        else:
            by_name = extract_date_by_filename(dt.code, entry.name)
            if by_name is None:
                generic = _extract_date(entry.name)
                if generic:
                    by_name = ("issue", generic)
        if by_name:
            field, value = by_name
            if field == "expiry" and not dt.tracks_expiry:
                field = "issue"
            # S118, corregido tras el dry-run EnterpriseBot_024: en un
            # tipo que caduca, una fecha FUTURA en el nombre es la
            # caducidad ("REV.TACOGRAFO 04-09-2027", "... 31-12-2027") --
            # tratada como emisión se descartaba por futura y el texto
            # ponía una caducidad falsa.
            if field == "issue" and dt.tracks_expiry and value \
                    and value > date.today():
                field = "expiry"
            if self._plausible(value, field == "expiry"):
                return field, value, "nombre"
        if entry.ocr_text:
            expiry, issue, other = classify_dates_in_text(entry.ocr_text)
            # Una caducidad anterior a la emisión del mismo texto es una
            # lectura falsa (informe DGT tipado como ITV, S118).
            if expiry and dt.tracks_expiry and self._plausible(expiry, True) \
                    and (issue is None or expiry > issue):
                return "expiry", expiry, "texto"
            if issue and self._plausible(issue, False):
                return "issue", issue, "texto"
            if len(other) == 1 and self._plausible(other[0], False):
                return "issue", other[0], "texto (fecha unica)"
        return None, None, None

    def _run(self, apply_changes):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        active_pks = list(MachineAsset.objects.filter(
            is_active=True,
        ).values_list("pk", flat=True))
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=False,
            domain_content_type=machine_ct,
            domain_object_id__in=active_pks,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(
            Q(expiry_date__isnull=True, issue_date__isnull=True)
            | Q(document_type__tracks_expiry=True, expiry_date__isnull=True)
        ).select_related("document_type").order_by("id"))
        total = len(entries)
        self._log(
            "PUNTO 8, PASO GRATIS -- MODO: %s -- %d documentos de maquinas "
            "activas sin la fecha que su tipo necesita" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)", total,
            )
        )
        found = Counter()
        missing = Counter()
        missing_ids = {}
        examples = {}
        start_time = datetime.now()
        last_beat = time.monotonic()
        for index, entry in enumerate(entries, start=1):
            code = entry.document_type.code
            updates, rule_source = self._decide_by_rules(entry)
            field, value, source = (None, None, None) if updates \
                else self._decide(entry)
            if updates:
                key = (code, "+".join(
                    sorted(name[:-5] for name in updates)), rule_source)
                found[key] += 1
                examples.setdefault(key, []).append("id=%d %s -> %s" % (
                    entry.id, entry.name, ", ".join(
                        "%s=%s" % (k, v) for k, v in sorted(updates.items())
                    ),
                ))
                if apply_changes:
                    DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                        **updates,
                    )
            elif field is None:
                missing[code] += 1
                self._track_undated(entry, missing_ids)
            else:
                # Nunca sobrescribe: en un caducable con emisión ya puesta
                # y sin caducidad, una "emisión" nueva no aporta nada.
                current = getattr(entry, "%s_date" % field)
                if current is not None:
                    missing[code] += 1
                    self._track_undated(entry, missing_ids)
                else:
                    found[(code, field, source)] += 1
                    examples.setdefault((code, field, source), []).append(
                        "id=%d %s -> %s" % (entry.id, entry.name, value),
                    )
                    if apply_changes:
                        DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                            **{"%s_date" % field: value},
                        )
            if index % 500 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- fechados=%d, sin_fecha=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60),
                        (datetime.now() + timedelta(seconds=eta_seg)
                         ).strftime("%H:%M:%S"),
                        sum(found.values()), sum(missing.values()),
                    )
                )

        self._log_plain("=== RESUMEN PUNTO 8, PASO GRATIS (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    documentos revisados: %d" % total)
        self._log_plain("    fechados: %d" % sum(found.values()))
        self._log_plain("    siguen sin fecha: %d" % sum(missing.values()))
        self._log_plain("--- FECHADOS POR TIPO, CAMPO Y FUENTE ---")
        for key, count in sorted(found.items(), key=lambda kv: -kv[1]):
            self._log_plain("    %s %s (%s): %d" % (key + (count,)))
        self._log_plain("--- SIGUEN SIN FECHA POR TIPO ---")
        for code, count in missing.most_common():
            self._log_plain("    %s: %d" % (code, count))
        self._log_plain("--- EJEMPLOS (hasta 5 por grupo) ---")
        for key, items in sorted(examples.items()):
            self._log_plain("  %s %s (%s)" % key)
            for line in items[:5]:
                self._log_plain("      %s" % line)
        # S119: el cierre del punto 1 son los de tipo que caduca sin
        # NINGUNA fecha; van al final del log, listados por id con el
        # arranque del texto, para leerlos con la cola del relevo sin
        # traer los miles de recibos que solo esperan caducidad.
        self._log_plain(
            "--- CIERRE PUNTO 1: CADUCABLES SIN NINGUNA FECHA, POR ID ---"
        )
        for code, items in sorted(missing_ids.items()):
            self._log_plain("  %s (%d)" % (code, len(items)))
            for item in items:
                self._log_plain("      id=%d %s | %s" % (
                    item.id, item.name,
                    normalize(item.ocr_text)[:220] or "(sin texto)",
                ))
        self._log_plain(
            "=== CIERRE PUNTO 1: %d caducables quedarian sin ninguna "
            "fecha (%s) ===" % (
                sum(len(items) for items in missing_ids.values()),
                "APLICADO" if apply_changes else "DRY-RUN",
            )
        )
