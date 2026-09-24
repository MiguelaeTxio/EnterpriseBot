# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/date_machine_documents_gemini.py
"""
H30 (S118), punto 8 de la hoja de ruta -- ÚLTIMO RECURSO del fechado:
documentos de tipos que CADUCAN de máquinas ACTIVAS que siguen sin
ninguna fecha tras el paso gratis (nombre + texto guardado,
`date_machine_documents_free`). Gemini lee el texto YA guardado en
`ocr_text` (nada de imágenes ni OCR nuevo) y devuelve la fecha de
emisión y la de caducidad/fin de vigencia del documento. Decisión de
Miguel Ángel (S118): "A ver si terminamos".

Garantías: solo fechas en formato AAAA-MM-DD; una fecha implausible
(anterior a 1980, emisión futura, caducidad posterior a 2045, o
caducidad anterior a la emisión) se descarta; solo rellena huecos.
Respuestas en un JSON de trabajo: el --apply las reutiliza sin volver a
llamar a Gemini. DRY-RUN por defecto. Log propio (0bis).
---
H30 (S118), roadmap item 8 -- LAST RESORT dating: Gemini over the
cached text of still-undated expiring documents of active machines.
"""
import json
import os
import time
from datetime import date, datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from google.genai.types import GenerateContentConfig, HttpOptions

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
TEXT_CHARS = 4000
MIN_DATE = date(1980, 1, 1)
MAX_EXPIRY = date(2045, 12, 31)
APPLY_CONFIDENCES = ("ALTA", "MEDIA")

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "issue_date": {"type": "string"},
        "expiry_date": {"type": "string"},
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
    },
    "required": ["issue_date", "expiry_date", "confidence", "reasoning"],
}

PROMPT = """Te doy el texto extraido (OCR) de UN documento de tipo \
"{label}" de una maquina o vehiculo de una empresa de gruas, y su \
nombre de archivo. Devuelve:
- issue_date: fecha de emision/expedicion/cargo del documento.
- expiry_date: fecha en que deja de estar vigente (caducidad, \
vencimiento, fin del periodo de cobertura del seguro o del recibo, \
proxima inspeccion). En un recibo de seguro es el ultimo dia del \
periodo que cubre.
Formato AAAA-MM-DD. Si una fecha no aparece en el texto, cadena vacia \
"" -- nunca la inventes ni la calcules. confidence: ALTA si las fechas \
son inequivocas, MEDIA si muy probables, BAJA si dudas. reasoning: una \
frase corta en castellano.

Nombre de archivo: {name}
Texto:
\"\"\"
{text}
\"\"\"
"""


def _parse(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


class Command(BaseCommand):
    help = (
        "H30 (S118) -- punto 8, ultimo recurso: fechas con Gemini sobre "
        "el texto guardado de los caducables sin fecha. Dry-run por "
        "defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--cache-file", required=True)
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
            self._run(options)
        finally:
            self._log_handle.close()

    def _run(self, options):
        apply_changes = options["apply"]
        cache_path = options["cache_file"]
        cache = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                cache = json.load(handle)
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        active_pks = list(MachineAsset.objects.filter(
            is_active=True,
        ).values_list("pk", flat=True))
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__tracks_expiry=True,
            expiry_date__isnull=True, issue_date__isnull=True,
            domain_content_type=machine_ct,
            domain_object_id__in=active_pks,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).exclude(ocr_text="").select_related("document_type").order_by("id"))
        total = len(entries)
        self._log(
            "PUNTO 8, GEMINI (%s) -- MODO: %s -- %d caducables sin fecha "
            "con texto; %d ya en la cache" % (
                DEFAULT_MODEL,
                "APLICAR (escribe, confianza ALTA/MEDIA)" if apply_changes
                else "DRY-RUN (no escribe nada)",
                total, sum(1 for e in entries if str(e.id) in cache),
            )
        )
        client = None
        stats = {"expiry": 0, "issue_only": 0, "none": 0, "baja": 0,
                 "errors": 0, "calls": 0}
        examples = []
        today = date.today()
        start_time = datetime.now()
        last_beat = time.monotonic()
        for index, entry in enumerate(entries, start=1):
            key = str(entry.id)
            if key not in cache:
                client = client or get_gemini_client()
                try:
                    response = _generate_content_with_retry(
                        client, model=DEFAULT_MODEL,
                        contents=PROMPT.format(
                            label=entry.document_type.label,
                            name=entry.name,
                            text=entry.ocr_text[:TEXT_CHARS],
                        ),
                        config=GenerateContentConfig(
                            http_options=HttpOptions(timeout=90_000),
                            response_mime_type="application/json",
                            response_schema=RESPONSE_SCHEMA,
                            temperature=0.0,
                        ),
                    )
                    cache[key] = json.loads(response.text)
                    stats["calls"] += 1
                    with open(cache_path, "w", encoding="utf-8") as handle:
                        json.dump(cache, handle, ensure_ascii=False)
                except Exception as exc:  # noqa: BLE001 -- se registra
                    stats["errors"] += 1
                    self._log("ERROR id=%d %s: %s" % (
                        entry.id, entry.name, str(exc)[:200],
                    ))
                    continue
            answer = cache[key]
            issue = _parse(answer.get("issue_date"))
            expiry = _parse(answer.get("expiry_date"))
            if issue and not (MIN_DATE <= issue <= today):
                issue = None
            if expiry and not (MIN_DATE <= expiry <= MAX_EXPIRY):
                expiry = None
            if expiry and issue and expiry <= issue:
                expiry = None
            confidence = answer.get("confidence", "BAJA")
            if confidence not in APPLY_CONFIDENCES:
                stats["baja"] += 1
                continue
            fields = {}
            if expiry:
                fields["expiry_date"] = expiry
                stats["expiry"] += 1
            if issue:
                fields["issue_date"] = issue
                if not expiry:
                    stats["issue_only"] += 1
            if not fields:
                stats["none"] += 1
                continue
            if len(examples) < 40:
                examples.append("id=%d %s (%s) -> emision=%s caducidad=%s "
                                "| %s" % (
                                    entry.id, entry.name,
                                    entry.document_type.code, issue, expiry,
                                    answer.get("reasoning", "")[:90],
                                ))
            if apply_changes:
                DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                    **fields,
                )
            if index % 25 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- llamadas=%d, errores=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60),
                        (datetime.now() + timedelta(seconds=eta_seg)
                         ).strftime("%H:%M:%S"),
                        stats["calls"], stats["errors"],
                    )
                )
        self._log_plain("=== RESUMEN PUNTO 8, GEMINI (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    documentos revisados: %d" % total)
        self._log_plain("    llamadas nuevas a Gemini: %d" % stats["calls"])
        self._log_plain("    con caducidad: %d" % stats["expiry"])
        self._log_plain("    solo emision: %d" % stats["issue_only"])
        self._log_plain("    sin fecha legible: %d" % stats["none"])
        self._log_plain("    confianza baja (no se escribe): %d"
                        % stats["baja"])
        self._log_plain("    errores: %d" % stats["errors"])
        self._log_plain("--- EJEMPLOS (hasta 40) ---")
        for line in examples:
            self._log_plain("    %s" % line)
