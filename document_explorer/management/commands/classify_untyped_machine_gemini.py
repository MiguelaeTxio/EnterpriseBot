# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/classify_untyped_machine_gemini.py
"""
H30 (S118), punto 7 de la hoja de ruta -- PASO C: los documentos SIN
TIPO de máquinas ACTIVAS que los marcadores de cabecera del paso B
(`classify_untyped_machine_text`) no resuelven, clasificados con Gemini
sobre el texto YA guardado en `ocr_text`. Decisión de Miguel Ángel
(S118): "Vamos", a la propuesta de gasto moderado -- solo texto (nada
de imágenes ni OCR nuevo), primeros TEXT_CHARS caracteres.

Lista CERRADA: Gemini solo puede elegir un código del catálogo activo
de máquinas (dominios MACHINE/BOTH) o NINGUNO -- nunca inventa un tipo.
Un código fuera de la lista se trata como NINGUNO. Los NINGUNO son la
lista final de documentos que no corresponden a ningún tipo (a decidir
con Miguel Ángel: tipo nuevo o papelera).

DRY-RUN por defecto (llama a Gemini y enseña el reparto con ejemplos,
sin escribir nada; guarda la respuesta en un JSON de trabajo para que
--apply NO vuelva a llamar a Gemini). --apply escribe document_type
solo con confianza ALTA/MEDIA (BAJA queda pendiente). Nunca toca GCS.
Log propio con heartbeat y ETA (com-standards 0bis/0ter).
---
H30 (S118), roadmap item 7 -- STEP C: Gemini classification of the
remaining untyped documents of active machines over the cached text,
closed list of catalog codes or NONE.
"""
import json
import os
import time
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from google.genai.types import GenerateContentConfig, HttpOptions

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
TEXT_CHARS = 3000
NONE_CODE = "NINGUNO"
APPLY_CONFIDENCES = ("ALTA", "MEDIA")

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type_code": {"type": "string"},
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
    },
    "required": ["document_type_code", "confidence", "reasoning"],
}

PROMPT = """Eres un clasificador documental de una empresa de gruas y \
maquinaria (Gruas Adolfo Alvarez S.L. / Transgrual S.L.). Te doy el \
texto extraido (OCR) del principio de UN documento archivado en la \
carpeta de una maquina o vehiculo, y su nombre de archivo.

Elige el tipo documental de ESTA lista cerrada (codigo: descripcion), \
por lo que el documento ES, no por lo que menciona de pasada:
{catalog}

Si el documento no es claramente ninguno de esos tipos (por ejemplo: \
documento de una persona, folleto comercial, certificado de propiedad, \
documento de envio, correo, otro tipo no listado), responde \
document_type_code = "{none}". Nunca inventes un codigo fuera de la \
lista.

confidence: ALTA si el tipo es inequivoco, MEDIA si es muy probable, \
BAJA si dudas. reasoning: una frase corta en castellano.

Nombre de archivo: {name}
Texto del documento:
\"\"\"
{text}
\"\"\"
"""


class Command(BaseCommand):
    help = (
        "H30 (S118) -- paso C del punto 7: Gemini sobre el texto guardado "
        "para los sin tipo de maquinas activas. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--cache-file", required=True,
            help="JSON de trabajo con las respuestas de Gemini (el "
                 "--apply lo reutiliza sin volver a llamar).",
        )
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

    def _load_cache(self, path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        return {}

    def _save_cache(self, path, cache):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False)

    def _run(self, options):
        apply_changes = options["apply"]
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        catalog = {
            dt.code: dt for dt in DocumentTypeCatalog.objects.filter(
                is_active=True, domain__in=["MACHINE", "BOTH"],
            ).order_by("code")
        }
        catalog_text = "\n".join(
            "- %s: %s" % (code, dt.label) for code, dt in catalog.items()
        )
        active_pks = list(MachineAsset.objects.filter(
            is_active=True,
        ).values_list("pk", flat=True))
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=True,
            domain_content_type=machine_ct,
            domain_object_id__in=active_pks,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).exclude(ocr_text="").order_by("id"))
        if options["limit"]:
            entries = entries[:options["limit"]]
        cache = self._load_cache(options["cache_file"])
        total = len(entries)
        self._log(
            "PASO C (Gemini %s) -- MODO: %s -- %d documentos sin tipo de "
            "maquinas activas con texto; %d ya en la cache de trabajo" % (
                DEFAULT_MODEL,
                "APLICAR (escribe, confianza ALTA/MEDIA)" if apply_changes
                else "DRY-RUN (no escribe nada)",
                total, sum(1 for e in entries if str(e.id) in cache),
            )
        )

        client = None
        by_code = {}
        applied = calls = errors = 0
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            key = str(entry.id)
            if key not in cache:
                if client is None:
                    client = get_gemini_client()
                try:
                    response = _generate_content_with_retry(
                        client,
                        model=DEFAULT_MODEL,
                        contents=PROMPT.format(
                            catalog=catalog_text, none=NONE_CODE,
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
                    calls += 1
                    self._save_cache(options["cache_file"], cache)
                except Exception as exc:  # noqa: BLE001 -- se registra
                    errors += 1
                    self._log("ERROR id=%d %s: %s" % (
                        entry.id, entry.name, str(exc)[:200],
                    ))
                    continue

            answer = cache[key]
            code = (answer.get("document_type_code") or "").strip().upper()
            confidence = answer.get("confidence", "BAJA")
            if code not in catalog:
                code = NONE_CODE
            by_code.setdefault((code, confidence), []).append(
                (entry, answer.get("reasoning", "")),
            )
            if apply_changes and code != NONE_CODE \
                    and confidence in APPLY_CONFIDENCES:
                DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                    document_type=catalog[code],
                )
                applied += 1

            if index % 25 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (
                    datetime.now() + timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- llamadas=%d, errores=%d, aplicados=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        calls, errors, applied,
                    )
                )

        self._summary(apply_changes, total, by_code, applied, calls, errors)

    def _summary(self, apply_changes, total, by_code, applied, calls,
                 errors):
        """
        Final report grouped by (type, confidence) with every document.
        ---
        Resumen por (tipo, confianza) con todos los documentos y el
        motivo que da Gemini.
        """
        self._log_plain("=== RESUMEN PASO C (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    documentos revisados: %d" % total)
        self._log_plain("    llamadas nuevas a Gemini: %d" % calls)
        self._log_plain("    errores: %d" % errors)
        if apply_changes:
            self._log_plain("    tipados (ALTA/MEDIA): %d" % applied)
        self._log_plain("--- RECUENTO POR TIPO Y CONFIANZA ---")
        for (code, confidence), items in sorted(
            by_code.items(), key=lambda kv: (-len(kv[1]), kv[0]),
        ):
            self._log_plain("    %s [%s]: %d" % (code, confidence, len(items)))
        self._log_plain("--- DETALLE (todos, con el motivo) ---")
        for (code, confidence), items in sorted(by_code.items()):
            self._log_plain("  %s [%s]: %d" % (code, confidence, len(items)))
            for entry, reasoning in items:
                self._log_plain("      id=%d %s | %s" % (
                    entry.id, entry.name, reasoning[:140],
                ))
