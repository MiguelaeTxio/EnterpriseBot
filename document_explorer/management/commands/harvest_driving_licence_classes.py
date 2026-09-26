# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/harvest_driving_licence_classes.py
"""
H30 (S120), punto 3 of the roadmap -- harvest, from every driving
licence card of ACTIVE people, the class matrix printed on its reverse
(columns 9-12) into DrivingLicenceGrant.
---
H30 (S120), punto 3 de la hoja de ruta -- recolecta, de TODOS los
carnés de conducir (`CARNET_CONDUCIR`) de las personas ACTIVAS, la
matriz de clases impresa en el reverso (columnas 9 a 12) y la guarda
en `DrivingLicenceGrant`.

Cómo:
- Gemini (`DEFAULT_MODEL`) lee el archivo tal cual (PDF o imagen, sin
  renderizar ni OCR en el servidor) y transcribe cada fila de la
  matriz tal como está impresa, más el modelo de carné y si se ve el
  reverso. Se leen TODOS los carnés de cada persona, no solo el
  último: anverso y reverso vienen a menudo en archivos separados, y
  solo el reverso lleva la matriz.
- La traducción de clases la hace este código, nunca Gemini
  (decisiones S120 de Miguel Ángel): "C+E" -> "CE"; 96/97 son códigos
  de su clase, nunca clases; clases del modelo anterior al RD 772/1997
  a su equivalente actual (DT 1ª del RGC): B1 -> B, A2 -> A,
  C2 -> C y CE, B1+E -> BE. BTP ya no existe (RD 1055/2015): se
  descarta y se informa. Lo que no tenga traducción inequívoca (p. ej.
  el C1 antiguo, que puede ser C1 o C según la masa) NO se escribe --
  sale en el informe para revisión manual.
- Fechas inverosímiles se descartan (primera expedición anterior a
  1950 o futura; caducidad anterior a 1980 o posterior a 2060; o
  caducidad anterior a la primera expedición).
- --apply, por cada carné con matriz legible: sustituye sus
  `DrivingLicenceGrant` por las filas leídas y pone en
  `DocumentIndexEntry.expiry_date` la caducidad MÁS LEJANA de sus
  clases (decisión 2 de Miguel Ángel, S120). Un carné sin reverso
  visible no se toca.

RELECTURA (S120, incidente real): dos lecturas de confianza MEDIA
salieron mal (años confundidos) en PDF que son fotos de móvil de poca
resolución -- y eran justo los carnés más recientes de esas personas.
--reread-ids vuelve a leer SOLO esos documentos renderizando cada
página del PDF a --reread-dpi (220 por defecto, `fitz`, el mismo motor
que ya usa el relevo en el servidor) y enviando las imágenes, y
sustituye su respuesta en la caché. Renderizar no es OCR: coste de CPU
despreciable para unos pocos documentos.

DRY-RUN por defecto. Respuestas en un JSON de trabajo (--cache-file):
el --apply las reutiliza sin volver a llamar a Gemini. Log propio,
pantalla y archivo a la vez (com-standards 0bis), progreso con ETA
(0ter). El informe lleva datos de personas: se lee por el relevo de
Drive, nunca por git.
"""
import json
import os
import time
from datetime import date, datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer.models import (
    DocumentIndexEntry,
    DrivingLicenceCategory,
    DrivingLicenceGrant,
    PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

BUCKET = "cgs_grupo_alvarez"
CARD_CODE = "CARNET_CONDUCIR"
MIN_FIRST_ISSUE = date(1950, 1, 1)
MIN_EXPIRY = date(1980, 1, 1)
MAX_EXPIRY = date(2060, 12, 31)
SUPPORTED_MIME = ("application/pdf", "image/jpeg", "image/png",
                  "image/webp", "image/heic", "image/heif")

# Traducción del modelo antiguo (DT 1ª del RGC) -- solo las
# inequívocas. Clave: clase tal cual impresa, ya normalizada.
# Valor: clases actuales equivalentes.
OLD_MODEL_EQUIVALENCES = {
    "B1": ("B",),
    "A2": ("A",),
    "C2": ("C", "CE"),
    "B1E": ("BE",),
    "B2E": ("BE",),
}
# Clases del modelo antiguo sin traducción inequívoca -> revisión.
OLD_MODEL_AMBIGUOUS = {"C1", "C1E", "B2", "E"}
DISCARDED_CLASSES = {"BTP"}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_driving_licence": {"type": "boolean"},
        "card_model": {
            "type": "string",
            "enum": ["TARJETA_UE", "ANTIGUO_PAPEL", "NO_DETERMINADO"],
        },
        "reverse_visible": {"type": "boolean"},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "first_issue_date": {"type": "string"},
                    "expiry_date": {"type": "string"},
                    "codes": {"type": "string"},
                },
                "required": [
                    "category", "first_issue_date", "expiry_date", "codes",
                ],
            },
        },
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "notes": {"type": "string"},
    },
    "required": [
        "is_driving_licence", "card_model", "reverse_visible", "rows",
        "confidence", "notes",
    ],
}

PROMPT = """Este archivo deberia ser un permiso de conduccion espanol \
(carne de conducir), anverso, reverso o ambos. Devuelve:
- is_driving_licence: false si NO es un permiso de conduccion (p. ej. \
tarjeta de tacografo, CAP, otro documento).
- card_model: TARJETA_UE (tarjeta de plastico, modelo comunitario), \
ANTIGUO_PAPEL (modelo antiguo de papel/cartulina anterior a 1998) o \
NO_DETERMINADO.
- reverse_visible: true solo si se ve la tabla de categorias con sus \
fechas (en la tarjeta UE, el reverso con las columnas 9, 10, 11 y 12).
- rows: UNA fila por cada categoria que tenga fechas escritas, \
transcrita TAL CUAL esta impresa (no traduzcas ni deduzcas \
categorias): category (p. ej. "B", "C1", "C+E", "BTP", "B1"), \
first_issue_date (columna 10, fecha de primera expedicion de esa \
categoria), expiry_date (columna 11, caducidad de esa categoria), \
codes (columna 12 tal cual, p. ej. "96" o "97"; "" si no hay). Las \
categorias sin fechas (casilla vacia o tachada) NO se incluyen. \
Fechas en formato AAAA-MM-DD; "" si no se lee -- nunca inventes ni \
calcules una fecha. Si el reverso no se ve, rows = [].
- confidence: ALTA si la lectura es inequivoca, MEDIA si muy probable, \
BAJA si dudas.
- notes: una frase corta en castellano.

Nombre de archivo: {name}
"""


def _parse(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _normalize_class(raw):
    """
    Normalize a printed class: uppercase, no spaces, no '+'.
    ---
    Normaliza una clase impresa: mayúsculas, sin espacios ni "+"
    ("C + E" -> "CE", "c1e" -> "C1E").
    """
    return (raw or "").upper().replace(" ", "").replace("+", "")


class Command(BaseCommand):
    help = (
        "H30 (S120) -- punto 3: recolecta la matriz de clases de los "
        "carnes de conducir de las personas activas. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--cache-file", required=True)
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )
        parser.add_argument(
            "--reread-ids", default="",
            help="Ids separados por comas a releer renderizados.",
        )
        parser.add_argument("--reread-dpi", type=int, default=220)

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
            self._run(options)
        finally:
            self._log_handle.close()

    def _file_parts(self, entry, render_dpi):
        """
        Return the Gemini parts for the card file.
        ---
        Partes para Gemini: el archivo tal cual, o -- si `render_dpi`
        y es PDF -- cada página renderizada a esa resolución como PNG.
        """
        data = download_bytes(BUCKET, entry.blob_name)
        if not render_dpi or entry.content_type != "application/pdf":
            return [Part.from_bytes(data=data, mime_type=entry.content_type)]
        import fitz

        parts = []
        with fitz.open(stream=data, filetype="pdf") as document:
            for page in document:
                parts.append(Part.from_bytes(
                    data=page.get_pixmap(dpi=render_dpi).tobytes("png"),
                    mime_type="image/png",
                ))
        return parts

    def _ask_gemini(self, client, entry, render_dpi=None):
        """
        Send the card file to Gemini and return its parsed JSON answer.
        ---
        Envía el archivo del carné a Gemini (tal cual, o renderizado si
        `render_dpi`) y devuelve su respuesta JSON ya parseada.
        """
        response = _generate_content_with_retry(
            client, model=DEFAULT_MODEL,
            contents=self._file_parts(entry, render_dpi) + [
                PROMPT.format(name=entry.name),
            ],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=120_000),
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        return json.loads(response.text)

    def _translate_rows(self, answer, today):
        """
        Translate printed rows into {class_code: (first, expiry, codes)}.
        ---
        Traduce las filas impresas a {clase_actual: (primera,
        caducidad, códigos)} y devuelve también las incidencias
        (filas descartadas o para revisión manual), con las reglas de
        la docstring del módulo.
        """
        old_model = answer.get("card_model") == "ANTIGUO_PAPEL"
        grants, issues = {}, []
        for row in answer.get("rows") or []:
            printed = _normalize_class(row.get("category"))
            first = _parse(row.get("first_issue_date"))
            expiry = _parse(row.get("expiry_date"))
            codes = (row.get("codes") or "").strip()
            if first and not (MIN_FIRST_ISSUE <= first <= today):
                issues.append("%s: primera expedicion inverosimil (%s), "
                              "descartada" % (printed, first))
                first = None
            if expiry and not (MIN_EXPIRY <= expiry <= MAX_EXPIRY):
                issues.append("%s: caducidad inverosimil (%s), descartada"
                              % (printed, expiry))
                expiry = None
            if first and expiry and expiry < first:
                issues.append("%s: caducidad %s anterior a expedicion %s, "
                              "descartada" % (printed, expiry, first))
                expiry = None
            if printed in DISCARDED_CLASSES:
                issues.append("%s: clase suprimida (RD 1055/2015), no se "
                              "guarda" % printed)
                continue
            if old_model:
                if printed in OLD_MODEL_EQUIVALENCES:
                    targets = OLD_MODEL_EQUIVALENCES[printed]
                elif printed in OLD_MODEL_AMBIGUOUS:
                    issues.append("%s (modelo antiguo): sin traduccion "
                                  "inequivoca, REVISION MANUAL" % printed)
                    continue
                else:
                    targets = (printed,)
            else:
                targets = (printed,)
            for target in targets:
                if target not in self._categories:
                    issues.append("%s: clase no reconocida, REVISION "
                                  "MANUAL" % printed)
                    continue
                if target in grants:
                    issues.append("%s: clase repetida en el carne, se "
                                  "conserva la primera lectura" % target)
                    continue
                grants[target] = (first, expiry, codes)
        return grants, issues

    def _run(self, options):
        apply_changes = options["apply"]
        cache_path = options["cache_file"]
        cache = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                cache = json.load(handle)
        self._categories = {
            category.code: category
            for category in DrivingLicenceCategory.objects.all()
        }
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        people = {
            person.pk: person
            for person in PersonIdentity.objects.filter(
                is_active_employee=True,
            )
        }
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code=CARD_CODE,
            domain_content_type=person_ct,
            domain_object_id__in=list(people.keys()),
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("domain_object_id", "id"))
        total = len(entries)
        self._log(
            "PUNTO 3, CLASES DE CARNES (%s) -- MODO: %s -- %d activos, %d "
            "carnes; %d ya en la cache" % (
                DEFAULT_MODEL,
                "APLICAR (escribe clases y caducidad mas lejana)"
                if apply_changes else "DRY-RUN (no escribe nada)",
                len(people), total,
                sum(1 for entry in entries if str(entry.id) in cache),
            )
        )
        client = None
        reread_ids = {
            int(value) for value in options["reread_ids"].split(",")
            if value.strip()
        }
        stats = {"calls": 0, "errors": 0, "with_matrix": 0,
                 "no_reverse": 0, "not_licence": 0, "low_confidence": 0,
                 "unsupported": 0, "grants": 0}
        people_with_matrix = set()
        report = {}
        today = date.today()
        start_time = datetime.now()
        last_beat = time.monotonic()
        for index, entry in enumerate(entries, start=1):
            lines = report.setdefault(entry.domain_object_id, [])
            key = str(entry.id)
            if entry.id in reread_ids:
                client = client or get_gemini_client()
                try:
                    cache[key] = self._ask_gemini(
                        client, entry, render_dpi=options["reread_dpi"],
                    )
                    stats["calls"] += 1
                    with open(cache_path, "w", encoding="utf-8") as handle:
                        json.dump(cache, handle, ensure_ascii=False)
                    self._log("RELEIDO id=%d a %d DPI" % (
                        entry.id, options["reread_dpi"],
                    ))
                except Exception as exc:  # noqa: BLE001 -- se registra
                    stats["errors"] += 1
                    self._log("ERROR relectura id=%d: %s" % (
                        entry.id, str(exc)[:200],
                    ))
            if key not in cache:
                if entry.content_type not in SUPPORTED_MIME:
                    stats["unsupported"] += 1
                    lines.append("id=%d %s -- formato no soportado (%s)"
                                 % (entry.id, entry.name,
                                    entry.content_type))
                    continue
                client = client or get_gemini_client()
                try:
                    cache[key] = self._ask_gemini(client, entry)
                    stats["calls"] += 1
                    with open(cache_path, "w", encoding="utf-8") as handle:
                        json.dump(cache, handle, ensure_ascii=False)
                except Exception as exc:  # noqa: BLE001 -- se registra
                    stats["errors"] += 1
                    self._log("ERROR id=%d %s: %s" % (
                        entry.id, entry.name, str(exc)[:200],
                    ))
                    lines.append("id=%d %s -- ERROR de lectura" % (
                        entry.id, entry.name,
                    ))
                    continue
            answer = cache[key]
            header = "id=%d %s [%s, %s]" % (
                entry.id, entry.name, answer.get("card_model"),
                answer.get("confidence"),
            )
            if not answer.get("is_driving_licence"):
                stats["not_licence"] += 1
                lines.append("%s -- NO ES PERMISO DE CONDUCCION: %s" % (
                    header, answer.get("notes", "")[:120],
                ))
            elif not answer.get("reverse_visible") or not answer.get("rows"):
                stats["no_reverse"] += 1
                lines.append("%s -- sin reverso/matriz visible" % header)
            elif answer.get("confidence") == "BAJA":
                stats["low_confidence"] += 1
                lines.append("%s -- confianza BAJA, no se escribe: %s" % (
                    header, answer.get("notes", "")[:120],
                ))
            else:
                grants, issues = self._translate_rows(answer, today)
                if grants:
                    stats["with_matrix"] += 1
                    stats["grants"] += len(grants)
                    people_with_matrix.add(entry.domain_object_id)
                    ordered = sorted(
                        grants.items(),
                        key=lambda item: self._categories[
                            item[0]].display_order,
                    )
                    lines.append("%s -- %s" % (header, "; ".join(
                        "%s exp=%s cad=%s%s" % (
                            code, first or "?", expiry or "?",
                            " cod=%s" % codes if codes else "",
                        )
                        for code, (first, expiry, codes) in ordered
                    )))
                    if apply_changes:
                        self._apply(entry, grants)
                else:
                    lines.append("%s -- ninguna clase utilizable" % header)
                for issue in issues:
                    lines.append("    ! %s" % issue)
            if index % 25 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- llamadas=%d, errores=%d, con matriz=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60),
                        (datetime.now() + timedelta(seconds=eta_seg)
                         ).strftime("%H:%M:%S"),
                        stats["calls"], stats["errors"],
                        stats["with_matrix"],
                    )
                )
        self._write_summary(apply_changes, people, entries, report,
                            people_with_matrix, stats)

    def _apply(self, entry, grants):
        """
        Replace the card's grants and set its farthest class expiry.
        ---
        Sustituye las clases del carné por las leídas y pone en el
        documento la caducidad MÁS LEJANA de sus clases (decisión 2,
        S120). Todo o nada por carné.
        """
        with transaction.atomic():
            DrivingLicenceGrant.objects.filter(entry=entry).delete()
            for code, (first, expiry, codes) in grants.items():
                DrivingLicenceGrant.objects.create(
                    entry=entry, category=self._categories[code],
                    first_issue_date=first, expiry_date=expiry,
                    codes=codes,
                )
            expiries = [
                expiry for _first, expiry, _codes in grants.values()
                if expiry
            ]
            if expiries:
                DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                    expiry_date=max(expiries),
                )

    def _write_summary(self, apply_changes, people, entries, report,
                       people_with_matrix, stats):
        """
        Log the final per-person report and the totals (no timings).
        ---
        Informe final por persona y totales -- sin ningún dato de
        tiempo (0ter), vía _log_plain.
        """
        people_with_card = {entry.domain_object_id for entry in entries}
        self._log_plain("=== RESUMEN PUNTO 3, CLASES DE CARNES (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    personas activas: %d" % len(people))
        self._log_plain("    activos con algun carne: %d"
                        % len(people_with_card))
        self._log_plain("    activos con matriz leida: %d"
                        % len(people_with_matrix))
        self._log_plain("    carnes revisados: %d" % len(entries))
        self._log_plain("    llamadas nuevas a Gemini: %d" % stats["calls"])
        self._log_plain("    carnes con matriz utilizable: %d"
                        % stats["with_matrix"])
        self._log_plain("    clases leidas en total: %d" % stats["grants"])
        self._log_plain("    sin reverso visible: %d" % stats["no_reverse"])
        self._log_plain("    no son permiso de conduccion: %d"
                        % stats["not_licence"])
        self._log_plain("    confianza baja (no se escribe): %d"
                        % stats["low_confidence"])
        self._log_plain("    formato no soportado: %d" % stats["unsupported"])
        self._log_plain("    errores: %d" % stats["errors"])
        self._log_plain("--- ACTIVOS SIN NINGUN CARNE SUBIDO ---")
        for pk, person in sorted(
            people.items(), key=lambda item: str(item[1]),
        ):
            if pk not in people_with_card:
                self._log_plain("    pk=%d %s" % (pk, person))
        self._log_plain("--- ACTIVOS CON CARNE PERO SIN MATRIZ LEIDA ---")
        for pk in sorted(people_with_card - people_with_matrix):
            self._log_plain("    pk=%d %s" % (pk, people[pk]))
        self._log_plain("--- DETALLE POR PERSONA ---")
        for pk in sorted(report, key=lambda item: str(people[item])):
            self._log_plain("pk=%d %s" % (pk, people[pk]))
            for line in report[pk]:
                self._log_plain("    %s" % line)
