# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/split_capacitacion_epis_burgos.py
"""
H30 (S72). Parte fisicamente el dosier real
"CAPACITACION Y EPIS MANOLO BURGOS.pdf" (entry pk=30592,
cgs_grupo_alvarez) -- un PDF escaneado de UNA sola pagina que mezcla
tres documentos distintos con firma propia cada uno: entrega de EPIs,
autorizacion de manejo de maquinaria, y entrega de informacion PRL.
Mismo problema estructural ya resuelto para RECONOCIMIENTO_MEDICO
(split_rm_dossier.py) y ALTA+IDC (split_alta_idc_dossier.py), unica
operacion fisica real sobre GCS permitida por 4.12: "contenido que
mezcla de verdad documentos distintos".

A diferencia de los dos comandos anteriores, aqui NO hay paginas
distintas que repartir -- es una unica pagina escaneada (sin capa de
texto, pdftotext no devuelve nada, confirmado) con las tres secciones
apiladas verticalmente. El corte no es por pagina sino por
coordenadas Y reales, verificadas visualmente contra el propio PDF
subido por Miguel Angel (nunca asumidas): se renderizo la pagina y se
localizaron los huecos en blanco reales entre secciones por perfil de
densidad de tinta, confirmando despues cada recorte con inspeccion
visual de los tres PNG resultantes antes de escribir este comando.
Cortes fijos, en puntos (pagina A4, 595x841pt):

    seccion 1 (EPIS):              y 0.0   -> 383.0
    seccion 2 (AUTORIZACION):      y 383.0 -> 569.3
    seccion 3 (INFORMACION):       y 569.3 -> 841.0

Caso puntual, NO patron detectado en mas archivos (Miguel Angel, S72:
"N.P.I." -- no sabe si hay mas casos iguales). Por eso este comando
es de un solo uso, con el pk de la fila y los cortes ya fijos en el
propio codigo -- igual que split_alta_idc_dossier.py trata su patron
de 2 paginas. Si en el futuro aparece OTRO archivo con el mismo
formato de plantilla (3 secciones EPIS/AUTORIZACION/INFORMACION en
una sola pagina), ese caso se evalua entonces para decidir si merece
generalizarse a un detector real -- no se asume aqui.

PersonIdentity resuelta por DNI real del documento (25663148R), NUNCA
por carpeta -- el dosier original vivia mal archivado bajo
".../BAJAS/OPERARIOS BAJAS/BURGOS FERNANDEZ, MANUEL (TR)/..." pese a
que la persona real (pk=85) tiene `is_active_employee=True` y
folder_path real en
"DOC. PERSONAL/PERSONAL/OPERARIOS/BURGOS FERNANDEZ, MANUEL (GR)" --
mismo patron ya documentado de trabajadores activos mezclados dentro
de la rama BAJAS. Verificado con datos reales (EnterpriseBot_013),
NO por resolucion automatica de carpeta -- justo la leccion aprendida
con el caso Daniel Serrano Rojas / Gomez Rivero de esta misma sesion
(el nombre del archivo/carpeta de origen no es de fiar, el DNI real
del contenido si).

DRY-RUN POR DEFECTO. Con --apply escribe de verdad: sube tres blobs
nuevos a GCS, indexa via refresh_folder(), escribe document_type/
domain en las filas nuevas, manda el original a papelera
(trash_dossier_entry()) solo cuando las tres secciones se han subido
con exito. Nunca toca blob_name de una fila ya existente (4.12).
"""
import datetime

import fitz
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.index_writer import refresh_folder
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from document_explorer.naming_service import build_filename_personal
from spare_parts.gcs_service import download_bytes, upload_bytes

ENTRY_PK = 30592
PERSON_PK = 85
DOCUMENT_DATE = datetime.date(2011, 2, 11)

# (nombre de seccion, codigo DocumentTypeCatalog, y0, y1) -- en puntos,
# verificados visualmente contra el PDF real (ver docstring arriba).
SECTIONS = [
    ("seccion1_EPIS", "EPIS", 0.0, 383.0),
    ("seccion2_AUTORIZACION", "AUTORIZACION_USO_MAQUINARIA", 383.0, 569.3),
    ("seccion3_INFORMACION", "ENTREGA_INFORMACION", 569.3, 841.0),
]


def _crop_section(data, y0, y1):
    """Devuelve los bytes de un PDF nuevo con solo la franja [y0, y1)
    de la pagina 1 del PDF de origen."""
    src = fitz.open(stream=data, filetype="pdf")
    page = src[0]
    width = page.rect.width
    clip = fitz.Rect(0, y0, width, y1)
    new_doc = fitz.open()
    new_page = new_doc.new_page(width=width, height=y1 - y0)
    new_page.show_pdf_page(new_page.rect, src, 0, clip=clip)
    out = new_doc.tobytes()
    new_doc.close()
    src.close()
    return out


class Command(BaseCommand):
    help = (
        "H30 (S72) -- caso puntual: parte "
        "'CAPACITACION Y EPIS MANOLO BURGOS.pdf' (pk=30592) en tres "
        "archivos (EPIS / AUTORIZACION_USO_MAQUINARIA / "
        "ENTREGA_INFORMACION). Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        entry = DocumentIndexEntry.objects.get(pk=ENTRY_PK)
        if not entry.name.lower().endswith(".pdf"):
            raise CommandError(
                "%s no es un PDF, fuera de alcance." % entry.name
            )

        person = PersonIdentity.objects.get(pk=PERSON_PK)
        self.stdout.write(
            "Persona (resuelta por DNI, no por carpeta): %s %s %s "
            "(pk=%d) | folder_path real: %s"
            % (
                person.first_surname, person.second_surname,
                person.given_name, person.pk, person.folder_path,
            )
        )

        data = download_bytes(entry.bucket, entry.blob_name)
        doc = fitz.open(stream=data, filetype="pdf")
        page_count = doc.page_count
        page_height = doc[0].rect.height
        doc.close()

        self.stdout.write(
            "--- %s: %d pagina(s), alto %.1fpt ---"
            % (entry.name, page_count, page_height)
        )
        if page_count != 1:
            raise CommandError(
                "Se esperaba 1 sola pagina, hay %d -- NO se divide, "
                "revision manual (los cortes de este comando son "
                "fijos para el PDF real ya verificado)." % page_count
            )

        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        target_folder = person.folder_path

        for name, type_code, y0, y1 in SECTIONS:
            self.stdout.write(
                "  %s -> tipo %s (y %.1f-%.1f)"
                % (name, type_code, y0, y1)
            )

        if not apply_changes:
            self.stdout.write("=== DRY-RUN, nada escrito ===")
            return

        created = []
        for name, type_code, y0, y1 in SECTIONS:
            doc_type = DocumentTypeCatalog.objects.get(code=type_code)
            section_bytes = _crop_section(data, y0, y1)
            # Sin ordinal: los tres nombres ya son distintos entre si
            # porque cada uno lleva un document_type_code diferente
            # (EPIS / AUTORIZACION_USO_MAQUINARIA / ENTREGA_INFORMACION)
            # -- no hay colision real que romper.
            filename = build_filename_personal(
                person.first_surname, person.second_surname,
                person.given_name, doc_type.code, DOCUMENT_DATE,
            )
            blob_name = "%s/%s" % (target_folder, filename)
            upload_bytes(entry.bucket, blob_name, section_bytes)
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
            created.append(blob_name)
            self.stdout.write("CREADO: %s" % blob_name)

        if trash_dossier_entry(entry):
            self.stdout.write(
                "Dosier original enviado a papelera: %s" % entry.name
            )
        else:
            self.stdout.write(
                "AVISO: no se pudo enviar el original a papelera -- "
                "las tres secciones ya estan creadas y clasificadas, "
                "revisar manualmente el original (pk=%d)." % entry.pk
            )
