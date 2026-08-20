# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/split_rm_dossier.py
"""
H30 (S59). Parte fisicamente un PDF "lote" de RECONOCIMIENTO_MEDICO
(varios trabajadores certificados en un mismo archivo, uno por
pagina) en un archivo nuevo por trabajador, y los indexa/vincula por
DNI -- unica operacion fisica real sobre GCS permitida por 4.12:
"contenido que mezcla de verdad documentos distintos".

---

H30 (S59). Physically splits an RM "batch" dossier PDF (several
workers certified in a single file, one per page) into one new file
per worker, indexed and linked by DNI -- the one real physical GCS
operation 4.12 allows: "content that genuinely mixes distinct
documents".

Patron real confirmado con OCR contra un ejemplo real (S59, ver
EnterpriseBot_021_GET.txt): una pagina por trabajador, texto siempre
con la misma forma:

    Que el trabajador {NOMBRE} y DNI {DNI} , a peticion de la
    empresa {EMPRESA} , ha sido sometido el dia {FECHA} , a
    reconocimiento medico ... resulta {APTO|NO APTO}

`ocr_pdf_to_text()` (date_verification_service) no sirve tal cual --
tiene `max_pages=2` fijo, pensado para verificacion de fecha de un
documento de una sola pagina. Este comando hace su propio OCR
pagina a pagina, sobre `doc.page_count` real completo.

Dos destinos posibles por pagina, decision explicita de Miguel Angel
(S59):
1. DNI resuelve a una `PersonIdentity` ya sembrada
   (`resolve_person_identity()`, coincidencia exacta) -> la pagina
   partida se sube a `{PersonIdentity.folder_path}/...`, nombrada
   con el esquema canonico real (`naming_service.
   build_filename_personal()`, con los apellidos/nombre YA
   confirmados de la identidad, nunca reparseados del OCR).
2. DNI no resuelve (trabajador de baja, o alta nueva sin sembrar
   todavia) -> la pagina partida se sube a
   "DOC. PERSONAL/DOCUMENTACION PENDIENTE DE REVISION", con tipo ya
   asignado pero dominio pendiente -- mismo patron "TIPO OK, DOMINIO
   PENDIENTE" que el resto de H30. Carpeta generica, deliberadamente
   NO exclusiva de RECONOCIMIENTO_MEDICO -- Miguel Angel, corregido
   S59, verbatim: *"cuando estamos haciendo el pipeline de alta de
   los trabajadores van a ir los documentos que no coincidan [...]
   un DNI de un trabajador que todavia no esta dado de alta [...] en
   esta carpeta caera su DNI, su reconocimiento medico, etcetera"* --
   cualquier tipo documental futuro con el mismo problema (DNI sin
   sembrar) comparte esta misma carpeta de espera, no una por tipo.
   Ese enganche con el pipeline de alta
   (`resolve_or_create_person_identity()`,
   `_NEW_WORKER_STAGING_FOLDER`) queda como dependencia futura
   documentada aqui, NO construida en esta sesion.

El dosier original va a papelera (`trash_dossier_entry()`) SOLO
cuando TODAS sus paginas se han podido partir y colocar en alguno de
los dos destinos de arriba -- si una sola pagina no encaja en el
patron regex (letra ilegible, formato distinto), el dosier original
se deja intacto y se reporta para revision manual, nunca se pierde
contenido sin repartir.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad: sube blobs
nuevos a GCS, indexa via `refresh_folder()`, escribe
document_type/domain en las filas nuevas, manda el original a
papelera cuando aplica. Nunca toca `blob_name` de una fila ya
existente (4.12).
"""
import io
import re
import unicodedata

import fitz
import pytesseract
from PIL import Image

from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    _DNI_CHECK_LETTERS, _NIE_PREFIX_DIGIT, is_valid_spanish_dni,
    resolve_person_identity, trash_dossier_entry,
)
from document_explorer.index_writer import refresh_folder
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from document_explorer.naming_service import (
    _sanitize_token, build_filename_personal,
)
from spare_parts.gcs_service import download_bytes, upload_bytes

PENDING_REVIEW_FOLDER = "DOC. PERSONAL/DOCUMENTACION PENDIENTE DE REVISION"

# Patron real confirmado contra OCR de un ejemplo real (S59). El
# grupo `dni` captura 9 caracteres alfanumericos en bruto -- nunca
# exige letra al final aqui, porque el propio OCR puede confundir la
# letra de control con un digito parecido (visto en produccion:
# "A"->"4", "Q"->"0") -- ver `_correct_ocr_dni()` mas abajo, que
# corrige eso de forma deterministica, sin adivinar.
_RECORD_RE = re.compile(
    r"trabajador\s+(?P<nombre>[A-ZÁÉÍÓÚÑ ,.]+?)\s+y\s+DNI\s+"
    r"(?P<dni>[0-9A-Za-z]{9})"
    r".{0,400}?d[ií]a\s+(?P<fecha>\d{1,2}\s+de\s+\w+\s+de\s+\d{4})"
    r".{0,800}?resulta\s+(?P<aptitud>NO\s+APTO|APTO)",
    re.IGNORECASE | re.DOTALL,
)

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _parse_spanish_date(raw):
    """
    Parses "17 de febrero de 2015" into a `date`, or None if the
    OCR text doesn't match the expected shape.

    ---

    Convierte "17 de febrero de 2015" en un `date`, o None si el
    texto OCR no tiene la forma esperada.
    """
    import datetime

    match = re.match(
        r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
        _strip_accents(raw).lower(),
    )
    if not match:
        return None
    day, month_name, year = match.groups()
    month = _MESES.get(month_name)
    if not month:
        return None
    try:
        return datetime.date(int(year), month, int(day))
    except ValueError:
        return None


def _correct_ocr_dni(raw):
    """
    Corrige de forma deterministica una letra de control de DNI mal
    leida por el OCR como digito (confusion real detectada en S59:
    "A"->"4", "Q"->"0"). Nunca adivina: si el noveno caracter ya es
    letra, se deja igual; si es digito, se calcula la letra real a
    partir del algoritmo publico de letra de control (mismo que usa
    `is_valid_spanish_dni`) y se sustituye. Si no se puede calcular
    (los 8 primeros no son digitos ni un prefijo NIE valido), se
    devuelve tal cual, sin forzar nada.

    ---

    Deterministically fixes a DNI check letter misread by OCR as a
    digit (real confusion found in S59: "A"->"4", "Q"->"0"). Never
    guesses: if the ninth character is already a letter, it's left
    as-is; if it's a digit, the real letter is computed from the
    public check-letter algorithm (same one `is_valid_spanish_dni`
    uses) and substituted. If it can't be computed (the first 8
    aren't digits or a valid NIE prefix), returns it unchanged.
    """
    value = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
    if len(value) != 9:
        return value
    digits_part, last = value[:8], value[8]
    if last.isalpha():
        return value

    check_digits = digits_part
    first_char = check_digits[0]
    if first_char in _NIE_PREFIX_DIGIT:
        check_digits = _NIE_PREFIX_DIGIT[first_char] + check_digits[1:]
    if not check_digits.isdigit():
        return value

    correct_letter = _DNI_CHECK_LETTERS[int(check_digits) % 23]
    return digits_part + correct_letter


def _ocr_all_pages(data):
    """
    OCR real de TODAS las paginas de un PDF (a diferencia de
    `ocr_pdf_to_text()`, que tiene `max_pages=2` fijo). Devuelve una
    lista de textos, uno por pagina, en orden.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    texts = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        texts.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return texts


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
        "H30 (S59) -- parte un dosier RM (varios trabajadores, uno "
        "por pagina) en un archivo por trabajador, vinculado por DNI "
        "o enviado a pendientes de revision. Dry-run por defecto, "
        "usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--entry-id", type=int, required=True,
            help="pk de la DocumentIndexEntry del PDF lote a partir.",
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
            self.stdout.write(
                "FUERA DE ALCANCE: %s no es un PDF, no se procesa."
                % entry.name
            )
            return

        rm_type = DocumentTypeCatalog.objects.get(
            code="RECONOCIMIENTO_MEDICO",
        )
        data = download_bytes(entry.bucket, entry.blob_name)
        page_texts = _ocr_all_pages(data)
        self.stdout.write(
            "--- %s: %d paginas ---" % (entry.name, len(page_texts))
        )

        resultados = []
        for page_index, text in enumerate(page_texts):
            clean = _strip_accents(text).upper()
            match = _RECORD_RE.search(clean)
            if not match:
                resultados.append((page_index, "SIN_PATRON", None))
                self.stdout.write(
                    "  pagina %d: SIN PATRON RECONOCIBLE (revision "
                    "manual)" % (page_index + 1)
                )
                continue

            nombre = match.group("nombre").strip()
            dni_raw = _correct_ocr_dni(match.group("dni"))
            aptitud = match.group("aptitud").strip()
            fecha = _parse_spanish_date(match.group("fecha"))

            if not is_valid_spanish_dni(dni_raw) or fecha is None:
                resultados.append((page_index, "DNI_O_FECHA_INVALIDOS", None))
                self.stdout.write(
                    "  pagina %d: DNI/fecha OCR ilegibles (%s / %s) "
                    "-- revision manual"
                    % (page_index + 1, dni_raw, match.group("fecha"))
                )
                continue

            person = resolve_person_identity(dni_raw)
            resultados.append((page_index, "OK", {
                "nombre": nombre, "dni": dni_raw, "aptitud": aptitud,
                "fecha": fecha, "person": person,
            }))
            self.stdout.write(
                "  pagina %d: %s | DNI %s | %s -> %s"
                % (
                    page_index + 1, nombre, dni_raw, aptitud,
                    ("PersonIdentity pk=%d" % person.pk) if person
                    else "SIN SEMBRAR (pendiente de revision)",
                )
            )

        sin_resolver = [r for r in resultados if r[1] != "OK"]
        if sin_resolver:
            self.stdout.write(
                "%d de %d paginas sin patron valido -- el dosier "
                "original NO se manda a papelera." % (
                    len(sin_resolver), len(resultados),
                )
            )

        if not apply_changes:
            self.stdout.write("=== DRY-RUN, nada escrito ===")
            return

        for page_index, status, info in resultados:
            if status != "OK":
                continue
            page_bytes = _split_single_page(data, page_index)
            person = info["person"]
            if person:
                filename = build_filename_personal(
                    person.first_surname, person.second_surname,
                    person.given_name, rm_type.code, info["fecha"],
                )
                target_folder = person.folder_path
            else:
                filename = "%s_%s_%s.pdf" % (
                    _sanitize_token(info["nombre"]), rm_type.code,
                    info["fecha"].strftime("%Y%m%d"),
                )
                target_folder = PENDING_REVIEW_FOLDER

            blob_name = "%s/%s" % (target_folder, filename)
            upload_bytes(entry.bucket, blob_name, page_bytes)
            refresh_folder(entry.bucket, target_folder)

            new_entry = DocumentIndexEntry.objects.get(
                bucket=entry.bucket, parent_path=target_folder,
                name=filename,
            )
            new_entry.document_type = rm_type
            if person:
                from django.contrib.contenttypes.models import ContentType
                from document_explorer.models import PersonIdentity
                new_entry.domain_content_type = (
                    ContentType.objects.get_for_model(PersonIdentity)
                )
                new_entry.domain_object_id = person.pk
            new_entry.save(update_fields=[
                "document_type", "domain_content_type", "domain_object_id",
            ])
            self.stdout.write("CREADO: %s" % blob_name)

        if not sin_resolver:
            if trash_dossier_entry(entry):
                self.stdout.write(
                    "Dosier original enviado a papelera: %s" % entry.name
                )
