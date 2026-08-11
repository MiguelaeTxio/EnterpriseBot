# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_b1_ocr_dates.py
"""
H30 (S48) -- Fase B1: OCR local con Tesseract para extraer fecha de
caducidad/emision de los documentos `tracks_expiry=True` que la Fase
B0 (heuristica de nombre) no pudo resolver -- ver anexo H30, seccion
"COMPLETADAS EN S48".

Reutiliza `document_explorer.date_verification_service` (extraido a
modulo compartido en S48 para no duplicar con el flujo de subida
desde ficha, que usa la misma logica de OCR/contexto).

Tipos marcados `document_type.ocr_unreliable=True` (hoy solo ITV,
verificado con datos reales -- tarjetas manuscritas con fondo de
seguridad que domina la lectura de Tesseract) se EXCLUYEN de este
recorrido masivo -- nunca se llama a Gemini en bloque (directriz de
coste de S46: "nunca otra pasada masiva de clasificacion por
Gemini"). Quedan contados aparte como cola real para una llamada a
Gemini deliberada y acotada, no automatica.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa. `--limit N` limita
cuantos documentos procesa en esta ejecucion (por defecto 20).
"""
from django.core.management.base import BaseCommand

from document_explorer.date_verification_service import (
    classify_dates_in_text, extract_text,
)
from document_explorer.models import DocumentIndexEntry
from spare_parts.gcs_service import download_bytes

BUCKET = "cgs_grupo_alvarez"

# Mapeo por defecto ya confirmado en B0 (S48) -- solo se usa como
# ultimo recurso, cuando el OCR no encuentra contexto reconocible y
# hay una unica fecha en el documento.
DEFAULT_FIELD_BY_CODE = {
    "ITV": "expiry",
    "OCA": "expiry",
    "CARNET_CONDUCIR": "expiry",
    "PERMISO_CIRCULACION": "issue",
    "FORMACION": "issue",
}


class Command(BaseCommand):
    help = (
        "H30 (S48) -- Fase B1: OCR real para fecha de caducidad/"
        "emision. Dry-run por defecto, --apply para escribir, "
        "--limit N para procesar por lotes (defecto 20). Excluye "
        "tipos ocr_unreliable (cola para Gemini deliberado)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        stats = {
            "expiry_por_contexto": 0, "issue_por_contexto": 0,
            "expiry_por_defecto": 0, "issue_por_defecto": 0,
            "sin_fecha_reconocible": 0, "extension_no_soportada": 0,
            "error_descarga_u_ocr": 0, "cola_gemini_ocr_unreliable": 0,
        }

        cola_gemini = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__tracks_expiry=True,
            document_type__ocr_unreliable=True,
            expiry_date__isnull=True, issue_date__isnull=True,
            domain_object_id__isnull=False,
        ).count()
        stats["cola_gemini_ocr_unreliable"] = cola_gemini

        qs = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__tracks_expiry=True,
            document_type__ocr_unreliable=False,
            expiry_date__isnull=True, issue_date__isnull=True,
            domain_object_id__isnull=False,
        ).select_related("document_type").order_by("id")[:limit]

        for entry in qs:
            code = entry.document_type.code
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text = extract_text(entry.name, data)
            except Exception as exc:
                stats["error_descarga_u_ocr"] += 1
                self.stdout.write(
                    "ERROR [%s] %s -- %s" % (entry.parent_path, entry.name, exc)
                )
                continue

            if text is None:
                stats["extension_no_soportada"] += 1
                continue

            expiry, issue, other_dates = classify_dates_in_text(text)

            if expiry:
                stats["expiry_por_contexto"] += 1
                self.stdout.write(
                    "%s -> expiry=%s (contexto)  [%s] %s"
                    % (code, expiry.isoformat(), entry.parent_path, entry.name)
                )
                if apply_changes:
                    entry.expiry_date = expiry
                    entry.save(update_fields=["expiry_date"])
                continue

            if issue:
                stats["issue_por_contexto"] += 1
                self.stdout.write(
                    "%s -> issue=%s (contexto)  [%s] %s"
                    % (code, issue.isoformat(), entry.parent_path, entry.name)
                )
                if apply_changes:
                    entry.issue_date = issue
                    entry.save(update_fields=["issue_date"])
                continue

            default_field = DEFAULT_FIELD_BY_CODE.get(code)
            if default_field and len(other_dates) == 1:
                found = other_dates[0]
                if default_field == "expiry":
                    stats["expiry_por_defecto"] += 1
                    self.stdout.write(
                        "%s -> expiry=%s (defecto B0, sin contexto)  "
                        "[%s] %s" % (
                            code, found.isoformat(),
                            entry.parent_path, entry.name,
                        )
                    )
                    if apply_changes:
                        entry.expiry_date = found
                        entry.save(update_fields=["expiry_date"])
                else:
                    stats["issue_por_defecto"] += 1
                    self.stdout.write(
                        "%s -> issue=%s (defecto B0, sin contexto)  "
                        "[%s] %s" % (
                            code, found.isoformat(),
                            entry.parent_path, entry.name,
                        )
                    )
                    if apply_changes:
                        entry.issue_date = found
                        entry.save(update_fields=["issue_date"])
                continue

            stats["sin_fecha_reconocible"] += 1
            snippet = " ".join(text.split())[:200]
            self.stdout.write(
                "SIN FECHA  [%s] %s | texto OCR (200 char): %r"
                % (entry.parent_path, entry.name, snippet)
            )

        self.stdout.write("=== RESUMEN (%s, limit=%d) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito", limit,
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
