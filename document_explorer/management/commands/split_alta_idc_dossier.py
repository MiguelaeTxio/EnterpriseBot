# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/split_alta_idc_dossier.py
"""
H30 (S66). Parte fisicamente un dosier real ALTA+IDC (Resolucion
sobre Reconocimiento de Alta + Informe de Datos para la Cotizacion,
dos documentos oficiales distintos escaneados juntos en el mismo PDF)
en dos archivos nuevos -- uno por tipo -- unica operacion fisica real
sobre GCS permitida por 4.12: "contenido que mezcla de verdad
documentos distintos".

Patron real confirmado por Miguel Angel (S66), tras revisar el
contenido de al menos dos de los diez archivos reales del dosier:
SIEMPRE pagina 1 = ALTA, pagina 2 = IDC, sin excepcion -- nunca al
reves, nunca mas de dos paginas. A diferencia de split_rm_dossier.py
(RECONOCIMIENTO_MEDICO, texto de plantilla variable segun mutua, OCR
+ regex por pagina para extraer nombre/DNI/fecha), aqui no hace falta
OCR de contenido: el dominio (PersonIdentity) ya se resuelve por
carpeta real (el dosier ya vive dentro de la carpeta de su persona,
_resolve_person_by_folder(), mismo mecanismo que run_fase_a_sweep),
y la fecha se extrae por regex del propio nombre de archivo de origen
(unica fecha real presente, common a las dos paginas del dosier).

Verificacion bloqueante antes de dividir cualquier archivo: el PDF
debe tener EXACTAMENTE 2 paginas. Si no las tiene, se informa y NO se
divide -- nunca se asume el patron sin comprobarlo pagina a pagina.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad: sube dos blobs
nuevos a GCS, indexa via refresh_folder(), escribe document_type/
domain en las filas nuevas, manda el original a papelera
(trash_dossier_entry()) solo cuando las dos paginas se han subido con
exito. Nunca toca blob_name de una fila ya existente (4.12).
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
import fitz

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.index_writer import refresh_folder
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity
from document_explorer.naming_service import build_filename_personal
from spare_parts.gcs_service import download_bytes, upload_bytes

# Fecha real dentro del nombre de archivo de origen -- unica fecha
# presente en los 10 casos reales, comparte formato D(D)-M(M)-AA(AA)
# con separador de guion, en cualquier punto del nombre (antes o
# despues de "IDC", con o sin espacio antes del "+"). Ver los 10
# nombres reales confirmados en la hoja de ruta S66.
_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2,4})")


def _resolve_person_by_folder(entry):
    """Mismo mecanismo que run_fase_a_sweep._resolve_person_by_folder()
    -- nunca por parecido de nombre, solo folder_path exacto o
    contenedor."""
    path = entry.parent_path
    contained = PersonIdentity.objects.filter(
        folder_path__in=[
            "/".join(path.split("/")[:i])
            for i in range(1, len(path.split("/")) + 1)
        ],
    )
    ids = {p.pk for p in contained}
    if len(ids) == 1:
        return contained[0]
    return None


def _parse_date_from_filename(name):
    import datetime

    match = _DATE_RE.search(name)
    if not match:
        return None
    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, int(month), int(day))
    except ValueError:
        return None


def _split_single_page(data, page_index):
    """Devuelve los bytes de un PDF nuevo de una sola pagina."""
    src = fitz.open(stream=data, filetype="pdf")
    new_doc = fitz.open()
    new_doc.insert_pdf(src, from_page=page_index, to_page=page_index)
    out = new_doc.tobytes()
    new_doc.close()
    src.close()
    return out


class Command(BaseCommand):
    help = (
        "H30 (S66) -- parte un dosier real ALTA+IDC (pagina 1 ALTA, "
        "pagina 2 IDC) en dos archivos. Dry-run por defecto, usar "
        "--apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--entry-id", type=int, required=True,
            help="pk de la DocumentIndexEntry del PDF dosier a partir.",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad (sube a GCS, indexa, papelera). "
                 "Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        entry = DocumentIndexEntry.objects.get(pk=options["entry_id"])

        if not entry.name.lower().endswith(".pdf"):
            raise CommandError(
                "%s no es un PDF, fuera de alcance." % entry.name
            )

        alta_type = DocumentTypeCatalog.objects.get(code="ALTA")
        idc_type = DocumentTypeCatalog.objects.get(code="IDC")

        data = download_bytes(entry.bucket, entry.blob_name)
        doc = fitz.open(stream=data, filetype="pdf")
        page_count = doc.page_count
        doc.close()

        self.stdout.write(
            "--- %s: %d paginas ---" % (entry.name, page_count)
        )
        if page_count != 2:
            self.stdout.write(
                "FUERA DE PATRON: %d paginas (se esperaban exactamente "
                "2) -- NO se divide, revision manual." % page_count
            )
            return

        person = _resolve_person_by_folder(entry)
        if not person:
            self.stdout.write(
                "SIN PersonIdentity resuelta por carpeta -- NO se "
                "divide, revision manual."
            )
            return

        date = _parse_date_from_filename(entry.name)
        if not date:
            self.stdout.write(
                "SIN fecha real reconocible en el nombre de origen -- "
                "NO se divide, revision manual."
            )
            return

        self.stdout.write(
            "Persona: %s (pk=%d) | Fecha: %s"
            % (person, person.pk, date.isoformat())
        )
        self.stdout.write(
            "  pagina 1 -> ALTA | pagina 2 -> IDC"
        )

        if not apply_changes:
            self.stdout.write("=== DRY-RUN, nada escrito ===")
            return

        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        target_folder = person.folder_path

        for page_index, doc_type in ((0, alta_type), (1, idc_type)):
            page_bytes = _split_single_page(data, page_index)
            filename = build_filename_personal(
                person.first_surname, person.second_surname,
                person.given_name, doc_type.code, date,
            )
            blob_name = "%s/%s" % (target_folder, filename)
            upload_bytes(entry.bucket, blob_name, page_bytes)
            refresh_folder(entry.bucket, target_folder)

            new_entry = DocumentIndexEntry.objects.get(
                bucket=entry.bucket, parent_path=target_folder,
                name=filename,
            )
            new_entry.document_type = doc_type
            new_entry.domain_content_type = person_ct
            new_entry.domain_object_id = person.pk
            new_entry.save(update_fields=[
                "document_type", "domain_content_type", "domain_object_id",
            ])
            self.stdout.write("CREADO: %s" % blob_name)

        if trash_dossier_entry(entry):
            self.stdout.write(
                "Dosier original enviado a papelera: %s" % entry.name
            )
