# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_nomina_dates_ocr.py
"""
H30 (S78). Extractor OCR de `issue_date` para documentos NOMINA de
personal activo cuyo nombre de archivo no trajo fecha reconocible por
heuristica (punto 3 de la hoja de ruta S78, fase OCR tras la fase de
heuristica de nombre ya aplicada -- ver anexo).

QUEDA TERMINANTEMENTE PROHIBIDO ejecutar este comando en la consola
Bash de PythonAnywhere (cuota de CPU, directriz de obligado
cumplimiento del proyecto). Se ejecuta SIEMPRE en una VM de computo
(h28-ocr-batch-1/2/3/4), via SSH, mismo patron que el resto de
barridos OCR del proyecto.

Reutiliza el servicio real ya construido
(document_explorer.date_verification_service): extract_text() para
convertir el documento a texto plano (Tesseract/PyMuPDF para
PDF/imagen, python-docx para .docx), y una busqueda de fecha
especifica de nomina -- las palabras de contexto de
classify_dates_in_text() (CADUCA/EXPEDICION...) no aparecen en una
nomina real, asi que aqui se buscan palabras propias de nomina
(PERIODO, LIQUIDACION, DEVENGO, MES) antes de caer a "unica fecha
plausible en el documento" como ultimo recurso.

Alcance: solo documentos ya vinculados a PersonIdentity con
is_active_employee=True (mismo criterio que el resto del piloto S78 --
nunca se extrae dato de personal de baja) y sin issue_date todavia.

DRY-RUN POR DEFECTO. --apply escribe de verdad. --limit para sondeo.
"""
import re
import unicodedata

from django.core.management.base import BaseCommand

from document_explorer.date_verification_service import (
    classify_dates_in_text, extract_text,
)
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

_PERIODO_CONTEXT = [
    "PERIODO", "LIQUIDACION", "DEVENGO", "MES DE", "CORRESPONDIENTE AL MES",
]
_MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
_MES_ANIO_RE = re.compile(
    r"\b(" + "|".join(_MESES.keys()) + r")\b\D{0,15}(\d{4})",
)


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _extraer_fecha_nomina(text):
    """
    Devuelve un `date` (dia 1 del mes de devengo) o None. Prioridad:
    1. Patron MES + ANIO en contexto de periodo/liquidacion/devengo.
    2. classify_dates_in_text(): si hay una unica fecha "otra" (sin
       contexto CADUCA/EXPEDICION), se usa como plausible.
    """
    import datetime

    norm = _strip_accents(text).upper()

    for match in _MES_ANIO_RE.finditer(norm):
        window_start = max(0, match.start() - 60)
        window = norm[window_start:match.start()]
        if any(word in window for word in _PERIODO_CONTEXT):
            mes = _MESES[match.group(1)]
            anio = int(match.group(2))
            if 2000 <= anio <= 2026:
                try:
                    return datetime.date(anio, mes, 1)
                except ValueError:
                    pass

    # Sin contexto de periodo explicito: cualquier MES+ANIO suelto,
    # si es el UNICO que aparece en el documento (evita ambiguedad).
    candidatos = []
    for match in _MES_ANIO_RE.finditer(norm):
        mes = _MESES[match.group(1)]
        anio = int(match.group(2))
        if 2000 <= anio <= 2026:
            try:
                candidatos.append(datetime.date(anio, mes, 1))
            except ValueError:
                continue
    if len(set(candidatos)) == 1:
        return candidatos[0]

    # Ultimo recurso: classify_dates_in_text (formato DD/MM/AAAA),
    # solo si hay una unica fecha "otra" sin contexto de caducidad.
    expiry, issue, other = classify_dates_in_text(text)
    if not expiry and not issue and len(set(other)) == 1:
        return other[0]

    return None


class Command(BaseCommand):
    help = (
        "H30 (S78) -- extractor OCR de issue_date para NOMINA de "
        "personal activo sin fecha por heuristica de nombre. "
        "EJECUTAR SOLO EN VM, nunca en PythonAnywhere. Dry-run por "
        "defecto, --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]

        t = DocumentTypeCatalog.objects.get(code="NOMINA")
        qs = DocumentIndexEntry.objects.filter(
            document_type=t, issue_date__isnull=True,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("id")

        entries = []
        for e in qs:
            try:
                p = PersonIdentity.objects.get(pk=e.domain_object_id)
            except PersonIdentity.DoesNotExist:
                continue
            if p.is_active_employee is True:
                entries.append(e)
        if limit:
            entries = entries[:limit]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d documento(s) NOMINA en alcance (%s) ==="
            % (len(entries), "APLICANDO" if apply_changes else "DRY-RUN")
        ))

        totals = {
            "procesados": 0, "con_fecha": 0, "sin_fecha": 0,
            "fallos_lectura": 0,
        }

        for entry in entries:
            totals["procesados"] += 1
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text = extract_text(entry.name, data)
            except Exception as exc:
                self.stdout.write(
                    "FALLO lectura: %s/%s -- %s"
                    % (entry.parent_path, entry.name, exc)
                )
                totals["fallos_lectura"] += 1
                continue

            if text is None:
                self.stdout.write(
                    "SIN EXTRACTOR para extension: %s" % entry.name
                )
                totals["sin_fecha"] += 1
                continue

            fecha = _extraer_fecha_nomina(text)
            if not fecha:
                self.stdout.write("SIN FECHA reconocible: %s" % entry.name)
                totals["sin_fecha"] += 1
                continue

            totals["con_fecha"] += 1
            if apply_changes:
                entry.issue_date = fecha
                entry.save(update_fields=["issue_date"])
                self.stdout.write(
                    "OK (escrito): %s -> issue_date=%s"
                    % (entry.name, fecha.isoformat())
                )
            else:
                self.stdout.write(
                    "OK (dry-run): %s -> issue_date=%s"
                    % (entry.name, fecha.isoformat())
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
