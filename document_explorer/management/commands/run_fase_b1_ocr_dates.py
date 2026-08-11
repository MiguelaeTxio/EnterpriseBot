# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_b1_ocr_dates.py
"""
H30 (S48) -- Fase B1: OCR local con Tesseract para extraer fecha de
caducidad/emision de los documentos `tracks_expiry=True` que la Fase
B0 (heuristica de nombre) no pudo resolver -- ver anexo H30, seccion
"COMPLETADAS EN S48".

Decision de Miguel Angel (S48): en vez de asumir por defecto que la
fecha del nombre es siempre caducidad, se lee el propio contenido del
documento (OCR) y se busca CONTEXTO real alrededor de cada fecha
encontrada -- "caduca"/"valido hasta"/"vencimiento" indican
`expiry_date`; "expedicion"/"emitido"/"expedido" indican `issue_date`.
Solo si no hay contexto reconocible Y hay una unica fecha en el
documento, se cae al mapeo por defecto ya confirmado en B0 para los
tipos que lo tienen (ITV/OCA/CARNET_CONDUCIR -> expiry;
PERMISO_CIRCULACION/FORMACION -> issue). Para SEGURO/TACOGRAFO/
EXCEDENCIA, sin mapeo por defecto verificado todavia, sin contexto
reconocible se deja SIN resolver -- nunca se adivina.

Extraccion de texto segun tipo real de archivo:
- `.pdf`: primeras 2 paginas renderizadas a imagen (fitz/PyMuPDF, ya
  dependencia del proyecto) -> OCR con pytesseract.
- `.jpg`/`.jpeg`/`.png`: OCR directo.
- `.docx`: texto nativo via python-docx (ya dependencia) -- nunca OCR,
  el texto ya es legible sin escanear.
- Cualquier otra extension: se omite, queda para revision manual.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa. `--limit N` limita
cuantos documentos procesa en esta ejecucion (por defecto 20) --
descargar + OCR-ar 2000+ documentos en una sola llamada arriesga
timeout del servidor; se ejecuta en lotes.
"""
import io
import re
import unicodedata
from datetime import date

import fitz
import pytesseract
from PIL import Image
from django.core.management.base import BaseCommand

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

_EXPIRY_CONTEXT = [
    "CADUCA", "CADUCIDAD", "VALIDO HASTA", "VALIDEZ HASTA", "VENCE",
    "VENCIMIENTO", "HASTA EL", "PROXIMA REVISION", "PROXIMA INSPECCION",
    "FECHA LIMITE", "VALIDO",
]
_ISSUE_CONTEXT = [
    "EXPEDICION", "EXPEDIDO", "EXPEDIDA", "EMISION", "EMITIDO",
    "EMITIDA", "FECHA DE EXPEDICION",
]

_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")
_CONTEXT_WINDOW = 40  # caracteres antes de la fecha a inspeccionar


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _parse_date(day_s, month_s, year_s):
    try:
        day, month, year = int(day_s), int(month_s), int(year_s)
    except ValueError:
        return None
    if year < 100:
        year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _classify_dates(text):
    """
    Devuelve (expiry_date o None, issue_date o None) a partir del
    texto OCR -- busca cada fecha y mira los _CONTEXT_WINDOW
    caracteres anteriores por palabras de contexto. Si dos fechas del
    mismo tipo de contexto compiten, se queda con la mas tardia
    (caducidad) o la mas temprana (emision, la primera vez emitido).
    """
    norm = _strip_accents(text).upper()
    expiry_candidates = []
    issue_candidates = []
    other_dates = []

    for match in _DATE_RE.finditer(norm):
        parsed = _parse_date(*match.groups())
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        context = norm[window_start:match.start()]
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    expiry = max(expiry_candidates) if expiry_candidates else None
    issue = min(issue_candidates) if issue_candidates else None
    return expiry, issue, other_dates


def _ocr_pdf(data):
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index in range(min(2, doc.page_count)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text_parts.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(text_parts)


def _ocr_image(data):
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="spa")


def _text_from_docx(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_text(entry, data):
    name_lower = entry.name.lower()
    if name_lower.endswith(".pdf"):
        return _ocr_pdf(data)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return _ocr_image(data)
    if name_lower.endswith(".docx"):
        return _text_from_docx(data)
    return None


class Command(BaseCommand):
    help = (
        "H30 (S48) -- Fase B1: OCR real para fecha de caducidad/"
        "emision. Dry-run por defecto, --apply para escribir, "
        "--limit N para procesar por lotes (defecto 20)."
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
            "error_descarga_u_ocr": 0,
        }

        qs = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__tracks_expiry=True,
            expiry_date__isnull=True, issue_date__isnull=True,
            domain_object_id__isnull=False,
        ).select_related("document_type").order_by("id")[:limit]

        for entry in qs:
            code = entry.document_type.code
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text = _extract_text(entry, data)
            except Exception as exc:
                stats["error_descarga_u_ocr"] += 1
                self.stdout.write(
                    "ERROR [%s] %s -- %s" % (entry.parent_path, entry.name, exc)
                )
                continue

            if text is None:
                stats["extension_no_soportada"] += 1
                continue

            expiry, issue, other_dates = _classify_dates(text)

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

        self.stdout.write("=== RESUMEN (%s, limit=%d) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito", limit,
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
