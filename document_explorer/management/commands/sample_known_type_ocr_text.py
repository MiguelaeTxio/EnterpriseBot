# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/sample_known_type_ocr_text.py
"""
H30 (S50) -- herramienta de analisis, no de clasificacion. Coge N
ejemplos reales de cada tipo documental YA confirmado (document_type
ya asignado, normalmente por heuristica de nombre de alta confianza)
y les pasa OCR, mostrando el PRINCIPIO del texto extraido.

Origen real: al probar `run_fase_b1_ocr_classify` sobre contenido, se
detectaron 2 falsos positivos claros -- un informe de mantenimiento
que mencionaba "ITV" de pasada se clasifico como ITV; una lista de
chequeo que mencionaba "CE" se clasifico como CE. El diccionario de
Fase A esta calibrado para NOMBRE de archivo (corto, deliberado), no
para CUERPO de texto (largo, lenguaje natural, con menciones de
pasada). Miguel Angel, verbatim (S50): "deberiamos de extraer texto
de tipos de documentos conocidos para dilucidar patrones" -- en vez
de adivinar que marcador de contenido usar, se construye a partir de
ejemplos reales confirmados.

Este comando NUNCA escribe nada en la base de datos -- es puramente
de analisis, para que Miguel Angel y el modelo revisen juntos los
patrones reales de encabezado antes de decidir el diccionario de
contenido definitivo para `run_fase_b1_ocr_classify`.
"""
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from document_explorer.date_verification_service import extract_text
from document_explorer.models import DocumentIndexEntry
from spare_parts.gcs_service import download_bytes

DEFAULT_CODES = [
    "ITV", "CE", "CERT_MANTENIMIENTO", "PERMISO_CIRCULACION",
    "TARJETA_TRANSPORTE", "SOLICITUD_ADMINISTRATIVA",
    "DECLARACION_HOMOLOGACION", "SEGURO", "POLIZA_SEGURO",
    "FICHA_TECNICA", "OCA", "IPO_ITC", "C_ADECUACION",
]


class Command(BaseCommand):
    help = (
        "H30 (S50) -- analisis: OCR de N ejemplos reales por tipo YA "
        "confirmado, para descubrir el patron real de encabezado. "
        "Nunca escribe nada, solo informa. --codes para elegir tipos, "
        "--per-type para cuantos ejemplos por tipo (defecto 3)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--codes", type=str, default=",".join(DEFAULT_CODES),
            help="Codigos de tipo separados por coma.",
        )
        parser.add_argument("--per-type", type=int, default=3)
        parser.add_argument("--chars", type=int, default=400)

    def handle(self, *args, **options):
        codes = [c.strip() for c in options["codes"].split(",") if c.strip()]
        per_type = options["per_type"]
        chars = options["chars"]

        for code in codes:
            # Correccion S50: el OCR de un tipo puede tardar varios
            # minutos (3 documentos), suficiente para que MySQL cierre
            # la conexion por inactividad (wait_timeout, error 4031)
            # antes de la siguiente consulta. Se fuerza reconexion al
            # empezar cada tipo.
            close_old_connections()
            entries = DocumentIndexEntry.objects.filter(
                entry_kind=DocumentIndexEntry.KIND_FILE,
                document_type__code=code,
                deleted_at__isnull=True, purged_at__isnull=True,
            ).order_by("?")[:per_type]

            self.stdout.write("=" * 70)
            self.stdout.write("=== %s (%d ejemplos) ===" % (code, len(entries)))
            for entry in entries:
                try:
                    data = download_bytes(entry.bucket, entry.blob_name)
                    text = extract_text(entry.name, data)
                except Exception as exc:
                    self.stdout.write(
                        "  ERROR [%s] %s -- %s"
                        % (entry.parent_path, entry.name, exc)
                    )
                    continue
                if text is None:
                    self.stdout.write(
                        "  SIN TEXTO (extension no soportada) [%s] %s"
                        % (entry.parent_path, entry.name)
                    )
                    continue
                snippet = " ".join(text.split())[:chars]
                self.stdout.write("  --- %s / %s ---" % (entry.parent_path, entry.name))
                self.stdout.write("  %r" % snippet)
                self.stdout.write("")
