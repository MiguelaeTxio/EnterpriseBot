# C:\EnterpriseBot\h28_migration_agent\extract_personal_dates_bulk.py
"""
H30 (S78). Barrido UNICO de extraccion de fecha (heuristica de
nombre + OCR) para TODO el dominio PERSONAL con
`document_type.tracks_expiry=True`, personal activo confirmado
(`PersonIdentity.is_active_employee=True`). Sustituye al enfoque de
"un tipo, un barrido, mirar resultado, repetir" -- un unico script,
un unico lanzamiento sharded en las 4 VMs (3 procesos cada una).

Mismo patron standalone que `local_ocr_classify.py` /
`extract_nomina_dates_ocr.py`: tunel SSH + pymysql + GCS directo, sin
Django (el venv de la VM no lo tiene).

Dos fases por documento, en orden (nunca se salta ninguna):
1. Heuristica de nombre de archivo (gratis) -- solo para los codigos
   de FIELD_BY_CODE (evidencia real ya confirmada, H30 S48) y los
   codigos de tipo "periodo" (REGISTRO_JORNADA, VACACIONES, mismo
   patron ya verificado hoy con NOMINA).
2. OCR (Tesseract/PyMuPDF) + deteccion de fecha por contexto
   (CADUCA/EXPEDICION...) -- si no hay contexto reconocible y solo
   hay una fecha en el documento, se usa DEFAULT_FIELD_BY_CODE para
   decidir si es caducidad o emision.

Sharding: `--shard-count N --shard-index I` reparte por
`entry_id % N == I`, sin solape entre procesos (mismo mecanismo que
`local_ocr_classify.py`, S51).

USO (un proceso, ejemplo shard 0 de 12):
    python3 extract_personal_dates_bulk.py --shard-count 12 --shard-index 0 --limit 5
    python3 extract_personal_dates_bulk.py --shard-count 12 --shard-index 0 --apply
"""
import argparse
import getpass
import io
import os
import re
import shutil
import unicodedata
from datetime import date, datetime

import pymysql

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import paramiko
if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

# Mismo patron que local_ocr_classify.py (correccion S50): en Windows,
# Tesseract no puede escribir en C:\Program Files\ sin permisos de
# administrador, asi que el paquete de idioma vive en una carpeta
# local propia junto al script (tessdata\) en vez de la ruta real de
# instalacion. En Linux (VM de OCR) esto no hace falta -- el paquete
# tesseract-ocr-spa ya instala el idioma en su sitio real.
if os.name == "nt":
    _TESSDATA_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tessdata",
    )
    os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR

import pytesseract
import sshtunnel
from google.cloud import storage
from PIL import Image

from config import get_service_account_key_path

# Sesion de continuidad tras S79, a peticion explicita de Miguel
# Angel: elimina el comentar/descomentar manual de TESSERACT_CMD por
# maquina. Si Tesseract ya esta en el PATH del sistema (caso normal
# en las VMs de Linux), shutil.which() lo encuentra y no hace falta
# nada mas. Si no esta en el PATH (caso real del PC de Windows de
# Miguel Angel, instalado sin permisos de administrador), prueba la
# ruta tipica de instalacion por defecto -- solo si el archivo existe
# de verdad ahi, nunca fuerza una ruta que no existe.
if not shutil.which("tesseract"):
    _WINDOWS_TESSERACT_DEFAULT = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    if os.path.isfile(_WINDOWS_TESSERACT_DEFAULT):
        pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT_DEFAULT

PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"

# ---------------------------------------------------------------
# Extraccion de texto -- copiado de local_ocr_classify.py
# ---------------------------------------------------------------
SAFE_MAX_PIXELS = 80_000_000
MIN_DPI = 100


def ocr_pdf_to_text(data, max_pages=2, dpi=400, psm=None, debug_save_prefix=None):
    config = ("--psm %d" % psm) if psm else ""
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_index)
        rect = page.rect
        dpi_pagina = dpi
        if rect.width > 0 and rect.height > 0:
            pixeles_estimados = (rect.width / 72 * dpi) * (rect.height / 72 * dpi)
            if pixeles_estimados > SAFE_MAX_PIXELS:
                dpi_pagina = int(
                    72 * (SAFE_MAX_PIXELS / (rect.width * rect.height)) ** 0.5
                )
                dpi_pagina = max(dpi_pagina, MIN_DPI)
        pix = page.get_pixmap(dpi=dpi_pagina)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        # H30 (sesion tras S85): guardar la imagen real, tal cual la
        # recibe Tesseract, para inspeccion visual directa -- nunca
        # mas teorizar sobre por que una linea legible no se lee sin
        # verla primero con los mismos ojos que Miguel Angel.
        if debug_save_prefix:
            img.save("%s_p%d.png" % (debug_save_prefix, page_index))
        text_parts.append(pytesseract.image_to_string(img, lang="spa", config=config))
    doc.close()
    return "\n".join(text_parts)


def ocr_image_to_text(data, psm=None):
    config = ("--psm %d" % psm) if psm else ""
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="spa", config=config)


_DOCUTEN_SIGNATURE_RE = re.compile(
    r"Fecha y hora:\s*(\d{1,2})-(\d{1,2})-(\d{4})"
)


# H30 (sesion S91). Documentos multi-pagina firmados via Docuten (visto
# en PLAN_ACTUACION_CALOR, boletin nacional de varias decenas de
# paginas de boilerplate identico para todos los empleados) llevan la
# fecha real -- la firma individual de ESE empleado concreto, no la
# fecha de aprobacion del plan nacional que aparece en las primeras
# paginas -- en la ULTIMA pagina del PDF ("Firmado por: NOMBRE...
# Fecha y hora: DD-MM-AAAA HH:MM UTC+N"), fuera del alcance de
# ocr_pdf_to_text(max_pages=2). Verificado real: id=40356 (gomez
# gomez), pagina 54, "Fecha y hora: 25-06-2025 17:30 UTC+2". Se OCRea
# solo la ultima pagina (nunca el documento completo -- estos PDFs
# rondan 10MB/50+ paginas de imagenes, OCRearlo entero es coste real
# innecesario) y se busca el patron literal de la cabecera de firma de
# Docuten, nunca el regex generico de fecha (evita capturar cualquiera
# de las decenas de fechas de boilerplate que pueda arrastrar la
# ultima pagina). Sincronizado con la copia Django
# (document_explorer/date_verification_service.py).
def extract_docuten_signature_date(data):
    """
    Devuelve la fecha de la firma electronica individual (bloque
    "Firmado por... Fecha y hora: DD-MM-AAAA") de la ULTIMA pagina de
    un PDF firmado via Docuten, o None si no aparece ese patron
    exacto.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count == 0:
        doc.close()
        return None
    page = doc.load_page(doc.page_count - 1)
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(img, lang="spa")
    doc.close()
    match = _DOCUTEN_SIGNATURE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


# ---------------------------------------------------------------
# H30 (sesion tras S85). EasyOCR -- lector de respaldo, no el
# principal (ver TERCER NIVEL en el bucle principal). Carga perezosa
# del modelo: solo se importa/carga la primera vez que un documento
# real lo necesita, para no pagar el coste (varios segundos) en
# ejecuciones donde Tesseract resuelve todo y nunca hace falta.
# ---------------------------------------------------------------
_EASYOCR_READER = None


def _get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        import easyocr
        print("  (cargando modelo EasyOCR, una sola vez por ejecucion...)")
        _EASYOCR_READER = easyocr.Reader(["es"])
    return _EASYOCR_READER


def easyocr_pdf_to_text(data, max_pages=2, dpi=400):
    import numpy as np
    reader = _get_easyocr_reader()
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_index)
        rect = page.rect
        dpi_pagina = dpi
        if rect.width > 0 and rect.height > 0:
            pixeles_estimados = (rect.width / 72 * dpi) * (rect.height / 72 * dpi)
            if pixeles_estimados > SAFE_MAX_PIXELS:
                dpi_pagina = int(
                    72 * (SAFE_MAX_PIXELS / (rect.width * rect.height)) ** 0.5
                )
                dpi_pagina = max(dpi_pagina, MIN_DPI)
        pix = page.get_pixmap(dpi=dpi_pagina)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        resultados = reader.readtext(np.array(img), detail=0)
        text_parts.append(" ".join(resultados))
    doc.close()
    return "\n".join(text_parts)


def easyocr_image_to_text(data):
    import numpy as np
    reader = _get_easyocr_reader()
    img = Image.open(io.BytesIO(data))
    resultados = reader.readtext(np.array(img), detail=0)
    return " ".join(resultados)


def easyocr_extract_text(filename, data):
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return easyocr_pdf_to_text(data)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return easyocr_image_to_text(data)
    return None


def docx_to_text(data):
    # H30 (sesion tras S89). Bug real corregido -- ver comentario
    # completo en la copia Django (document_explorer/
    # date_verification_service.py): no leia doc.tables, solo
    # doc.paragraphs. Descubierto en ENTREGA_MANUAL_COMBUSTIBLE,
    # 23/23 documentos con texto identico y 0 fechas encontradas.
    import docx
    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def doc_to_text(data):
    """
    .doc antiguo (Word 97-2003, formato binario) -- python-docx NO lo
    lee (solo .docx). Usa `antiword` como subproceso (instalar en la
    VM: `sudo apt-get install -y antiword`), via archivo temporal
    porque antiword no acepta stdin de forma fiable para todos los
    .doc reales vistos en el corpus.
    """
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["antiword", tmp_path],
            capture_output=True, timeout=30,
        )
        return result.stdout.decode("utf-8", errors="ignore")
    finally:
        import os
        os.unlink(tmp_path)


def xlsx_to_text(data):
    """Concatena el texto de todas las celdas de todas las hojas."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    parts = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    parts.append(str(cell.value))
    return "\n".join(parts)


def txt_to_text(data):
    """
    H30 (sesion S91). Bug real corregido: extract_text() no
    reconocia .txt en absoluto -- descubierto en CERTIFICADO_BANCARIO,
    donde 4 de 15 documentos pendientes son notas de texto plano
    ("cta bco Apellido.txt") nunca leidas por ningun barrido anterior
    (ocr_text_cacheado=0 para los cuatro). No requiere OCR: se
    decodifica directamente. utf-8 primero (mayoria real de estos
    ficheros); latin-1 como red de seguridad para el resto sin fallar
    nunca por encoding. Sincronizado con la copia Django
    (document_explorer/date_verification_service.py).
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(filename, data, psm=None, debug_save_prefix=None):
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return ocr_pdf_to_text(data, psm=psm, debug_save_prefix=debug_save_prefix)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return ocr_image_to_text(data, psm=psm)
    if name_lower.endswith(".docx"):
        return docx_to_text(data)
    if name_lower.endswith(".doc"):
        return doc_to_text(data)
    if name_lower.endswith((".xlsx", ".xls")):
        return xlsx_to_text(data)
    if name_lower.endswith(".txt"):
        return txt_to_text(data)
    return None


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


# ---------------------------------------------------------------
# FASE 1 -- heuristica de nombre (evidencia real, H30 S48, copiado de
# filename_date_service.py) + patron de periodo (H30 S78, ya
# verificado hoy con NOMINA)
# ---------------------------------------------------------------
FIELD_BY_CODE = {
    "ITV": "expiry",
    "OCA": "expiry",
    "CARNET_CONDUCIR": "expiry",
    "PERMISO_CIRCULACION": "issue",
    "FORMACION": "issue",
}
PERIODO_CODES = {"REGISTRO_JORNADA", "VACACIONES"}

_DATE_RE_NAME = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")

_MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
_MES_ANIO_RE = re.compile(
    r"\b(" + "|".join(_MESES.keys()) + r")\b\D{0,15}(\d{4})",
)
_PERIODO_CONTEXT = [
    "PERIODO", "LIQUIDACION", "DEVENGO", "MES DE", "CORRESPONDIENTE AL MES",
]


def _parse_date_dmY(day_s, month_s, year_s):
    # H30 (S87): anno impreso con separador de miles espanol ("1.996")
    # -- incidente real (ALTA AUTONOMO.pdf, "6 NOVIEMBRE 1.996"): sin
    # este strip, int("1.996") lanza ValueError y la fecha se pierde
    # por completo en vez de leerse como 1996.
    year_s = year_s.replace(".", "") if year_s else year_s
    try:
        day, month, year = int(day_s), int(month_s), int(year_s)
    except ValueError:
        return None
    # H30 (S87): ventana de siglo real para anno de 2 digitos --
    # incidente real (mismo documento de arriba): "6-11-96" (fecha de
    # iniciacion de actividad, campo distinto) se leia como 2096
    # porque el codigo sumaba siempre 2000 sin comprobar plausibilidad.
    # Mismo criterio que ya usa _mrz_century_cutoff(): ningun documento
    # de la plantilla es del futuro, asi que AA se resuelve como 20AA
    # si AA <= año actual (2 digitos), y como 19AA en caso contrario.
    if year < 100:
        year += 2000 if year <= _mrz_century_cutoff() else 1900
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_date_from_name(name):
    matches = list(_DATE_RE_NAME.finditer(name))
    for match in reversed(matches):
        parsed = _parse_date_dmY(*match.groups())
        if parsed:
            return parsed
    return None


def _extract_periodo_from_name(name):
    norm = _strip_accents(name).upper()
    for match in _MES_ANIO_RE.finditer(norm):
        window_start = max(0, match.start() - 60)
        window = norm[window_start:match.start()]
        if any(word in window for word in _PERIODO_CONTEXT):
            mes = _MESES[match.group(1)]
            anio = int(match.group(2))
            if 2000 <= anio <= 2026:
                try:
                    return date(anio, mes, 1)
                except ValueError:
                    pass
    candidatos = []
    for match in _MES_ANIO_RE.finditer(norm):
        mes = _MESES[match.group(1)]
        anio = int(match.group(2))
        if 2000 <= anio <= 2026:
            try:
                candidatos.append(date(anio, mes, 1))
            except ValueError:
                continue
    if len(set(candidatos)) == 1:
        return candidatos[0]
    return None


def extract_date_by_filename(code, name):
    """Devuelve (field, date) o None -- nunca adivina."""
    if code in PERIODO_CODES:
        found = _extract_periodo_from_name(name)
        if found:
            return "issue", found
        return None
    if code not in FIELD_BY_CODE:
        return None
    found = _extract_date_from_name(name)
    if not found:
        return None
    return FIELD_BY_CODE[code], found


# ---------------------------------------------------------------
# FASE 1bis -- MRZ de DNI/NIE (H30 S79, hallazgo real de sesion,
# copiado de date_verification_service.py). Nunca usa el nombre de
# archivo -- el MRZ es contenido real impreso en el documento, la
# misma via de "OCR/contenido real" que exige el comentario de mas
# abajo tras la retirada de la heuristica de nombre en S78.
# ---------------------------------------------------------------
MRZ_CODES = {"DNI", "NIE"}
_MRZ_LINE2_RE = re.compile(r"(\d{6})(\d)([MF])(\d{6})(\d)([A-Z]{3})")
_MRZ_WEIGHTS = (7, 3, 1)


def _mrz_check_digit(digits):
    total = 0
    for i, ch in enumerate(digits):
        total += int(ch) * _MRZ_WEIGHTS[i % 3]
    return total % 10


def extract_dni_mrz_expiry(text):
    """Fecha de caducidad del MRZ, validada por su propio digito de
    control ICAO 9303 -- None si no valida o no hay MRZ."""
    norm = _strip_accents(text).upper()
    for match in _MRZ_LINE2_RE.finditer(norm):
        _, _, _, expiry_digits, expiry_check, _ = match.groups()
        if _mrz_check_digit(expiry_digits) != int(expiry_check):
            continue
        year, month, day = (
            int(expiry_digits[0:2]), int(expiry_digits[2:4]),
            int(expiry_digits[4:6]),
        )
        try:
            return date(2000 + year, month, day)
        except ValueError:
            continue
    return None


# H30 (S83), copiado de date_verification_service.py -- ver ese
# archivo para la explicacion completa de la ventana de siglo.
def _mrz_century_cutoff():
    return date.today().year % 100


def extract_dni_mrz_birthdate(text):
    """Fecha de nacimiento del MRZ (mismo match que la caducidad),
    validada por su propio digito de control ICAO 9303 -- None si no
    valida o no hay MRZ."""
    norm = _strip_accents(text).upper()
    cutoff = _mrz_century_cutoff()
    for match in _MRZ_LINE2_RE.finditer(norm):
        birth_digits, birth_check, _, _, _, _ = match.groups()
        if _mrz_check_digit(birth_digits) != int(birth_check):
            continue
        year_2d, month, day = (
            int(birth_digits[0:2]), int(birth_digits[2:4]),
            int(birth_digits[4:6]),
        )
        century = 2000 if year_2d <= cutoff else 1900
        try:
            return date(century + year_2d, month, day)
        except ValueError:
            continue
    return None


# S79 -- cara frontal del DNI/NIE, etiquetas EMISION/VALIDEZ con
# fecha "DD MM AAAA" separada por espacios (copiado de
# date_verification_service.py).
_DNI_FRONT_LABEL_RE = re.compile(r"(EMISION|VALIDEZ)")
_SPACED_DATE_RE = re.compile(
    r"(\d{1,2})[\s./,;\"'\u2019\u201c\u201d]+"
    r"(\d{1,2})[\s./,;\"'\u2019\u201c\u201d]+(\d{4})"
)
_DNI_FRONT_PLAUSIBLE_YEARS = range(2015, 2046)


def extract_dni_front_expiry(text):
    """Caducidad tras EMISION/VALIDEZ. Si aparecen ambas etiquetas
    pero solo se lee una fecha limpia, no se adivina -- None. Entre
    varias fechas validas, la mas tardia (copiado de
    date_verification_service.py)."""
    norm = _strip_accents(text).upper()
    label_matches = list(_DNI_FRONT_LABEL_RE.finditer(norm))
    if not label_matches:
        return None
    labels_found = {m.group(1) for m in label_matches}
    window = norm[label_matches[0].end():label_matches[0].end() + 100]
    candidatas = []
    for d, m, y in _SPACED_DATE_RE.findall(window):
        year = int(y)
        if year not in _DNI_FRONT_PLAUSIBLE_YEARS:
            continue
        try:
            candidatas.append(date(year, int(m), int(d)))
        except ValueError:
            continue
    if not candidatas:
        return None
    if "EMISION" in labels_found and "VALIDEZ" in labels_found and len(candidatas) < 2:
        return None
    return max(candidatas)


# ---------------------------------------------------------------
# FASE 2 -- OCR + deteccion por contexto (copiado de
# date_verification_service.py, sin la parte de Gemini)
#
# Sesion de continuidad tras S79: esta copia se habia quedado
# desincronizada de la version real del servicio Django -- le
# faltaban _DATE_LARGO_RE (fecha en letra, "10 de Enero de 2022" /
# "10 Enero 2022"), _LABELED_DATE_PATTERNS (etiquetas explicitas tipo
# PERIODO/FECHA DE INICIO) y varias palabras de _ISSUE_CONTEXT. Con
# solo el patron numerico, nunca reconocia fechas escritas en letra
# -- que es como escriben la fecha la mayoria de los reconocimientos
# medicos, formacion y comunicados oficiales. Sincronizada completa.
# ---------------------------------------------------------------
_EXPIRY_CONTEXT = [
    "CADUCA", "CADUCIDAD", "VALIDO HASTA", "VALIDA HASTA", "VENCE",
    "VENCIMIENTO", "HASTA EL", "PROXIMA REVISION", "PROXIMA INSPECCION",
    "FECHA LIMITE",
    # H30 (S91). Impreso oficial "COMUNICACION DE LA PRORROGA DEL
    # CONTRATO DE TRABAJO" (SEPE/Seguridad Social) -- campo
    # estructurado "Fecha de Termino: DD/MM/AAAA", verificado en
    # COMUNICACION_CONTRATO (id=34826, id=36361). Sincronizado con la
    # copia Django.
    "FECHA DE TERMINO",
]
_ISSUE_CONTEXT = [
    "EXPEDICION", "EXPEDIDO", "EXPEDIDA", "EMISION", "EMITIDO",
    "EMITIDA", "CON FECHA", "SOMETIDO EL DIA", "MALAGA A",
    # H30 (S87): "CONFECHA" fusionado sin espacio -- artefacto real
    # de OCR de baja calidad, visto repetido en resoluciones de la
    # Seguridad Social ("...D.N.I. 033356574L ,confecha 06-07-2012").
    # "CON FECHA" (con espacio) ya estaba en la lista; esto cubre el
    # caso en que Tesseract funde las dos palabras en una.
    "CONFECHA",
    # H30 (S87): etiqueta real de impreso antiguo REA (regimen
    # autonomos, "ALTA AUTONOMO.pdf") -- "Fecha de alta Núm.
    # identificación | | Ye : ese 6 NOVIEMBRE 1.996".
    "FECHA DE ALTA",
    # H30 (S87): etiqueta real del "PARTE MEDICO DE BAJA/ALTA DE
    # INCAPACIDAD TEMPORAL (P.9)" -- "PARTE DE BAJA [X] Fecha de la
    # baja 19/10/2020".
    "FECHA DE LA BAJA",
    # H30 (S91). Plantilla real de "Firma/recibi del trabajador... A
    # fecha(DD/MM/AAAA)" -- verificada en EVALUACION_RIESGO (id=22002,
    # id=22018, mismo impreso "ENTREGA DE EVALUACION DE RIESGO" de
    # GRUPO ALVAREZ). "CON FECHA" ya estaba cubierto, "A FECHA" suelta
    # nunca lo estuvo -- template usado en varios tipos con recibi
    # firmado, no solo en este. Sincronizado con la copia Django
    # (document_explorer/date_verification_service.py).
    "A FECHA",
    # H30 (S91). Cierre real de "CLAUSULA_PROTECCION_DATOS" (LOPD,
    # plantilla de 2014) -- "...mediante la presente y firma de
    # conformidad, en Santa Rosalía a 30 de septiembre de 2014."
    # Verificado en 8 documentos reales. Mismo cierre "en <Ciudad> a
    # <fecha>" que "MALAGA A", pero con ciudad variable. "FIRMA DE
    # CONFORMIDAD" es la frase fija que precede a la fecha, sin
    # depender de la ciudad. Sincronizado con la copia Django.
    "FIRMA DE CONFORMIDAD",
    # H30 (S91). Mismo impreso oficial que "FECHA DE TERMINO" arriba.
    # Sincronizado con la copia Django.
    "FECHA DE INICIO",
]
# Sesion de continuidad tras S79 -- incidente real: fechas de
# nacimiento coladas como "unica fecha, por defecto" en
# RECONOCIMIENTO_MEDICO. Ver date_verification_service.py para el
# detalle completo. Se descartan por completo, nunca entran ni
# siquiera en "otras fechas".
_BIRTHDATE_CONTEXT = [
    "NACIDO", "NACIDA", "NACIO", "FECHA DE NACIMIENTO", "NACIMIENTO",
]
# H30 (S89). Recibos domiciliados (AUTONOMO, CSS) traen fechas ruido
# ademas de la fecha real -- ver comentario completo en la copia
# Django (document_explorer/date_verification_service.py).
_RECEIPT_NOISE_CONTEXT = [
    "PERIODO", "INSCRITA", "INSCRIPC", "SERVLETOPERATION", "ELOPERATION",
    "COOPERATIVO CAJAMAR",
]
_NOISE_SPAN_PATTERNS = [
    re.compile(r"DEVOLUCION[\s\S]{0,200}?(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})"),
]
_NOISE_LITERAL_DATES = {date(2012, 10, 31)}
_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")
_CONTEXT_WINDOW = 70

_MESES_LARGO = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
# "DE"/"DEL" opcional en los dos huecos -- cubre "10 de Enero de 2022"
# y "10 Enero 2022" con la misma expresion (documento real confirmado
# por Miguel Angel, certificado CENTRO MEDICO ALAMEDA).
_DATE_LARGO_RE = re.compile(
    r"(\d{1,2})\s+(?:DE\s+)?(" + "|".join(_MESES_LARGO.keys()) + r")\s+(?:DEL?\s+)?(\d\.?\d{3})",
)

_GAP = r"[^\d]{0,15}"
# Par "4a."/"4b." del formato comunitario (permiso de conduccion UE,
# reutilizado tal cual por la Tarjeta de Cualificacion del Conductor
# -- misma disposicion de campos). Confirmado con Miguel Angel (S86)
# y verificado contra fuentes independientes (DGT, Comunidad de
# Madrid, Generalitat Valenciana, gestorias): 4a = fecha de expedicion
# (issue), 4b = fecha de caducidad (expiry), 4c = autoridad emisora.
# Maxima prioridad -- por delante incluso de _LABELED_DATE_PATTERNS,
# porque un documento con el par completo es evidencia mas fuerte que
# una unica fecha etiquetada, y evita que el escaneo generico de
# fechas sueltas descarte por ambiguedad (nacimiento, numero de
# carne, codigo comunitario) lo que el propio documento ya resuelve
# sin dudas.
_FIELD_4A_4B_RE = re.compile(
    r"4A\.?\s*(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"
    r".{0,40}?"
    r"4B\.?\s*(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})",
    re.DOTALL,
)

_LABELED_DATE_PATTERNS = [
    re.compile(r"PERIODO" + _GAP + r"DESDE" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"FECHA\s+DE\s+INICIO\s+DEL\s+CONTRATO" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"FECHA\s+DE\s+TRANSFORMACION" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"(?:SE\s+)?EXTENDER[AÁ]\s+DESDE" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"RELACION\s+LABORAL\s+EN\s+FECHA" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(
        r"PRORROGA[\s\S]{0,120}?DESDE" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})",
        re.DOTALL,
    ),
    # "A FECHA (DD/MM/AAAA)" -- sello real junto a la firma del
    # administrador (Grupo Alvarez), visto en AUTORIZACION_USO_MAQUINARIA
    # y otros tipos con el mismo pie de firma. Maxima prioridad porque
    # desambigua documentos que llevan otras fechas de ruido (fecha de
    # firma electronica, fechas de un curso de formacion adjunto,
    # numero de carne con fechas de vigencia de categorias) -- incidente
    # real S86, 4 de 8 fallos de un barrido tenian esta etiqueta
    # presente y el documento se marcaba SIN FECHA por ambiguedad pese
    # a que la etiqueta ya la resolvia sin dudas.
    re.compile(r"A\s+FECHA" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    # H30 (S87): "...es la que se indica a continuacion: DD-MM-AAAA"
    # -- boilerplate real de las resoluciones de Alta/Baja de la
    # Seguridad Social (RECONOCIMIENTO DE ALTA/BAJA). Maxima prioridad
    # porque en varios documentos reales la etiqueta "CON FECHA"/
    # "CONFECHA" queda lejos (OCR reordena celdas de tabla) pero esta
    # frase de cierre siempre aparece pegada a la fecha real de
    # efectos.
    re.compile(r"INDICA\s+A\s+CONTINUACION" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    # H30 (S87): etiqueta "ALTA:" pegada a la fecha real, formato fijo
    # del impreso "Informe de Datos para la Cotizacion" (IDC) --
    # "TIPO CONTRATO: ... ALTA: 27-01-2004 BAJA:". "L" opcional porque
    # el OCR de baja calidad a veces la funde ("ATA 21-04-2025").
    re.compile(r"AL?TA" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
]

DEFAULT_FIELD_BY_CODE = {
    # EXPIRY -- documentos con caducidad real
    "CARNET_CONDUCIR": "expiry", "CARNET_GRUISTA": "expiry",
    "TARJETA_CUALIF_CONDUCTOR": "expiry", "TACOGRAFO": "expiry",
    "DNI": "expiry", "NIE": "expiry",
    "AUTORIZACION_TEMPORAL_CONDUCIR": "expiry",
    "CERT_EXENCION_TACOGRAFO": "expiry", "CERTIF_DISCAPACIDAD": "expiry",
    # ISSUE -- el mas reciente es el vigente, sin caducidad propia
    "CAP": "issue", "ACUERDO_SALARIAL": "issue", "ALTA": "issue",
    "AUTONOMO": "issue", "BAJA_PERSONAL": "issue",
    # H30 (S87): activado tracks_expiry en el catalogo para este tipo
    # (estaba en False, motivo real de que el barrido devolviera 0
    # candidatos pese a 133 documentos reales sin fecha). "El mas
    # reciente cuenta" -- mismo criterio que BAJA_PERSONAL, sin
    # caducidad propia.
    "PARTE_BAJA_MEDICA": "issue",
    "CAMBIO_EMPRESA_SUBROGACION": "issue", "CAMBIO_IRPF": "issue",
    "CARTA_BAJA_VOLUNTARIA": "issue", "CERTIFICADO_GIBRALTAR": "issue",
    "CERTIF_TRABAJO_COLEGIO": "issue", "COMUNICACION_CONTRATO": "issue",
    "COMUNICACION_JORNADA": "issue", "COMUNICADO_SEPE": "issue",
    "CONVENIO_FCT": "issue", "CSS": "issue", "IDC": "issue",
    # H30 (S89): tipo nuevo creado esta sesion (documentos "Vida
    # laboral autonomo..." mal tipados como CSS). Sin caducidad
    # propia, "el mas reciente cuenta" -- mismo criterio que CSS.
    "INFORME_VIDA_LABORAL": "issue",
    "MOD_145": "issue", "TC2": "issue", "VACACIONES": "issue",
    "REGISTRO_JORNADA": "issue", "CURSO": "issue",
    "ENTREGA_INFORMACION": "issue", "ENTREGA_MANUAL_COMBUSTIBLE": "issue",
    "ENTREGA_PROTOCOLO_AUXILIO_CARRETERA": "issue",
    "EVALUACION_RIESGO": "issue", "FORMACION_ITC_MINERA": "issue",
    "FORMACION_PRL_MAQUINARIA": "issue",
    "INFORMACION_MEDIDAS_PROTECCION": "issue",
    "NOMBRAMIENTO_JEFE_MANIOBRAS": "issue",
    "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD": "issue",
    "PLAN_ACTUACION_CALOR": "issue", "ALTA_MEDICA": "issue",
    "CERT_LIMITACIONES": "issue", "DOC_MUTUA": "issue",
    "RECONOCIMIENTO_MEDICO": "issue", "FICHA_TECNICA_EPI": "issue",
    "AUTORIZACION_GENERICA": "issue", "AUTORIZACION_LIBRO_SUBCONTRATA": "issue",
    "AUTORIZACION_MEDIOS_COMUNICACION": "issue", "CERTIFICADO_BANCARIO": "issue",
    "CLAUSULA_PROTECCION_DATOS": "issue", "ENTREGA_DOCUMENTACION_VARIA": "issue",
    "ENTREGA_MOVIL": "issue", "CONTRATO": "issue", "EXCEDENCIA": "issue",
    "FORMACION": "issue", "AUTORIZACION_USO_MAQUINARIA": "issue",
}


def classify_dates_in_text(text):
    # H30 (S87): normalizar espacios en blanco (incluidos saltos de
    # linea reales del OCR) a un unico espacio ANTES de la comprobacion
    # de contexto -- ver comentario completo en
    # document_explorer/date_verification_service.py (copia sincronizada).
    norm = _strip_accents(text).upper()
    norm = re.sub(r"\s+", " ", norm)
    # H30 (S91). Mismo principio que arriba, para comas: "En MALAGA, a
    # 16 de JUNIO de 2026" no coincidia con "MALAGA A" ya existente por
    # la coma real de en medio -- ver comentario completo en la copia
    # Django (document_explorer/date_verification_service.py).
    norm = re.sub(r",", " ", norm)
    norm = re.sub(r"\s+", " ", norm)
    expiry_candidates, issue_candidates, other_dates = [], [], []

    # H30 (S89): fechas de ruido por posicion exacta -- ver comentario
    # completo en la copia Django (document_explorer/date_verification_service.py).
    _noise_spans = [
        m.span(1)
        for pattern in _NOISE_SPAN_PATTERNS
        for m in pattern.finditer(norm)
    ]

    def _en_fecha_ruido(match, parsed=None):
        for s, e in _noise_spans:
            if match.start() >= s - 1 and match.end() <= e + 1:
                return True
        if parsed is not None and parsed in _NOISE_LITERAL_DATES:
            return True
        return False

    # Maxima prioridad absoluta: par "4a."/"4b." del formato
    # comunitario -- ver comentario junto a _FIELD_4A_4B_RE. Devuelve
    # los DOS campos a la vez (unico caso de todo el extractor que lo
    # hace), porque el propio documento ya distingue expedicion de
    # caducidad sin ninguna ambiguedad.
    match_4a4b = _FIELD_4A_4B_RE.search(norm)
    if match_4a4b:
        issue_4a = _parse_date_dmY(*match_4a4b.groups()[0:3])
        expiry_4b = _parse_date_dmY(*match_4a4b.groups()[3:6])
        if issue_4a and expiry_4b:
            return expiry_4b, issue_4a, []

    # Maxima prioridad: etiqueta explicita -- nunca ambigua.
    for pattern in _LABELED_DATE_PATTERNS:
        match = pattern.search(norm)
        if match:
            parsed = _parse_date_dmY(*match.groups())
            if parsed:
                return None, parsed, []

    for match in _DATE_RE.finditer(norm):
        parsed = _parse_date_dmY(*match.groups())
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + norm[match.end():window_end]
        if any(word in context for word in _BIRTHDATE_CONTEXT):
            continue
        if any(word in context for word in _RECEIPT_NOISE_CONTEXT):
            continue
        if _en_fecha_ruido(match, parsed):
            continue
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    for match in _DATE_LARGO_RE.finditer(norm):
        day_s, mes_s, year_s = match.groups()
        month = _MESES_LARGO.get(mes_s)
        parsed = _parse_date_dmY(day_s, month, year_s) if month else None
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + norm[match.end():window_end]
        if any(word in context for word in _BIRTHDATE_CONTEXT):
            continue
        if any(word in context for word in _RECEIPT_NOISE_CONTEXT):
            continue
        if _en_fecha_ruido(match, parsed):
            continue
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    expiry = max(expiry_candidates) if expiry_candidates else None
    issue = min(issue_candidates) if issue_candidates else None
    return expiry, issue, other_dates


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument(
        "--document-type", type=str, default=None,
        help="Acota el barrido a un unico codigo de DocumentTypeCatalog "
             "(p.ej. RECONOCIMIENTO_MEDICO). Sin este flag, barre todos "
             "los tipos con tracks_expiry=True.",
    )
    parser.add_argument(
        "--entry-ids", type=str, default=None,
        help="H30 (S87). Lista de ids de DocumentIndexEntry separados "
             "por coma (p.ej. 35390,39463) -- acota el barrido a "
             "exactamente esos ids, ignorando shard/limit. Pensado para "
             "usar tras la auditoria de 'realmente pendientes' (persona "
             "sin OTRO documento del mismo tipo ya fechado), evitando "
             "reprocesar en VM el resto del lote que ya es historico.",
    )
    args = parser.parse_args()
    if not (0 <= args.shard_index < max(args.shard_count, 1)):
        parser.error("--shard-index debe estar entre 0 y --shard-count - 1")

    mysql_password = getpass.getpass(
        "Contrasena de MySQL (panel PythonAnywhere, pestana 'Databases'): "
    )

    # Sesion de continuidad tras S79. Version anterior forzaba
    # host_pkey_directories=[] / allow_agent=False (solo contraseña),
    # y ese camino fallaba en el gateway de PythonAnywhere
    # (sshtunnel.BaseSSHTunnelForwarderError: "Could not establish
    # session to SSH gateway"). Diagnostico real con paramiko.SSHClient
    # directo (descubrimiento de clave por defecto) autentico al
    # instante por clave publica -- la clave de Miguel Angel
    # (C:\Users\Usuario\.ssh\id_rsa) ya esta registrada en
    # PythonAnywhere y funciona. Se deja que sshtunnel la descubra
    # igual que hace `ssh` normal -- ya no hace falta pedir la
    # contraseña de PythonAnywhere en absoluto.
    print("Abriendo tunel SSH a %s (autenticando por clave ya registrada) ..." % SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOSTNAME,
        ssh_username=PYTHONANYWHERE_USERNAME,
        remote_bind_address=(MYSQL_HOSTNAME, 3306),
    )
    tunnel.start()
    print("Tunel abierto, puerto local %d." % tunnel.local_bind_port)

    conn = pymysql.connect(
        host="127.0.0.1", port=tunnel.local_bind_port,
        user=MYSQL_USERNAME, passwd=mysql_password,
        db=MYSQL_DB_NAME, charset="utf8mb4",
    )

    print("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        get_service_account_key_path()
    )

    shard_clause = ""
    shard_params = ()
    if args.shard_count > 1:
        shard_clause = " AND e.id %% %s = %s"
        shard_params = (args.shard_count, args.shard_index)

    type_clause = ""
    type_params = ()
    if args.document_type:
        type_clause = " AND t.code = %s"
        type_params = (args.document_type,)

    entry_ids_clause = ""
    entry_ids_params = ()
    if args.entry_ids:
        try:
            ids = [int(x.strip()) for x in args.entry_ids.split(",") if x.strip()]
        except ValueError:
            parser.error("--entry-ids debe ser una lista de ids separados por coma")
        if not ids:
            parser.error("--entry-ids no puede quedar vacio")
        placeholders = ", ".join(["%s"] * len(ids))
        entry_ids_clause = " AND e.id IN (%s)" % placeholders
        entry_ids_params = tuple(ids)

    # H31 (S96): con --entry-ids el filtro de domain='PERSONAL' del
    # catalogo se relaja -- la auditoria de esa sesion encontro tipos
    # con domain mal etiquetado en DocumentTypeCatalog (SEGURO,
    # POLIZA_SEGURO: domain=MACHINE; CONVENIO_FORMACION_BONIFICADA:
    # domain=COMPANY) que tienen documentos reales vinculados a
    # PersonIdentity, confirmados personales por auditoria uno a uno
    # (nunca por heuristica). El join contra personidentity ya
    # garantiza que el documento cuelga de una persona; exigir ademas
    # domain='PERSONAL' del tipo excluiria exactamente estos casos ya
    # verificados. Sin --entry-ids (barrido abierto) el filtro se
    # mantiene tal cual, para no arrastrar sin querer documentos de
    # tipos mal etiquetados que no se han auditado.
    domain_clause = "" if args.entry_ids else " AND t.domain = 'PERSONAL'"

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM django_content_type "
            "WHERE app_label = 'document_explorer' AND model = 'personidentity'"
        )
        person_ct_id = cur.fetchone()[0]

        cur.execute(
            "SELECT e.id, e.name, e.bucket, e.blob_name, t.code "
            "FROM document_explorer_documentindexentry e "
            "JOIN document_explorer_documenttypecatalog t "
            "  ON e.document_type_id = t.id "
            "JOIN document_explorer_personidentity p "
            "  ON e.domain_object_id = p.id "
            "WHERE e.domain_content_type_id = %s"
            + domain_clause +
            " AND t.tracks_expiry = 1 "
            "AND t.ocr_unreliable = 0 "
            "AND e.expiry_date IS NULL AND e.issue_date IS NULL "
            "AND e.deleted_at IS NULL AND e.purged_at IS NULL "
            "AND p.is_active_employee = 1"
            + type_clause + shard_clause + entry_ids_clause +
            " ORDER BY e.id",
            (person_ct_id,) + type_params + shard_params + entry_ids_params,
        )
        rows = cur.fetchall()

    if args.shard_count > 1:
        print("Reparto: shard %d de %d (entry_id %% %d == %d)"
              % (args.shard_index, args.shard_count,
                 args.shard_count, args.shard_index))
    print("Candidatos en este shard: %d" % len(rows))
    if args.limit:
        rows = rows[:args.limit]
    print("Se van a procesar en esta ejecucion: %d\n" % len(rows))

    stats = {
        "heuristica_nombre": 0, "mrz": 0, "frente": 0, "ocr_contexto": 0,
        "ocr_unica_fecha": 0, "par_4a_4b": 0, "sin_fecha": 0,
        "sin_extractor": 0, "error": 0,
    }
    start_time = datetime.now()

    for i, (entry_id, name, bucket_name, blob_name, code) in enumerate(rows, start=1):
        if i % 20 == 0:
            conn.ping(reconnect=True)
        _log("[%d/%d] [%s] %s" % (i, len(rows), code, name))

        # H30 (S78): heuristica de nombre de archivo RETIRADA por
        # decision explicita de Miguel Angel -- ya causo dos errores
        # reales (identidad falsa por nombre de carpeta, tipo
        # documental cruzado). Todo pasa por OCR/contenido real.

        # OCR
        try:
            bucket = gcs_client.bucket(bucket_name)
            data = bucket.blob(blob_name).download_as_bytes()
            text = extract_text(name, data)
        except Exception as exc:
            stats["error"] += 1
            print("  ERROR -- %s" % exc)
            continue

        if text is None:
            stats["sin_extractor"] += 1
            print("  SIN EXTRACTOR (extension no soportada)")
            continue

        # FASE 1bis -- MRZ de DNI/NIE (S79). Contenido real impreso
        # en el documento, nunca el nombre de archivo. Se prueba
        # antes del OCR de contexto porque el MRZ es mas fiable que
        # el patron generico cuando la cara frontal esta degradada.
        if code in MRZ_CODES:
            mrz_expiry = extract_dni_mrz_expiry(text)
            if mrz_expiry:
                stats["mrz"] = stats.get("mrz", 0) + 1
                print("  MRZ %s -> expiry=%s" % (code, mrz_expiry.isoformat()))
                if args.apply:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE document_explorer_documentindexentry "
                            "SET ocr_text=%s, expiry_date=%s WHERE id=%s",
                            (text, mrz_expiry, entry_id),
                        )
                    conn.commit()
                continue
            front_expiry = extract_dni_front_expiry(text)
            if front_expiry:
                stats["frente"] = stats.get("frente", 0) + 1
                print("  FRENTE %s -> expiry=%s" % (code, front_expiry.isoformat()))
                if args.apply:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE document_explorer_documentindexentry "
                            "SET ocr_text=%s, expiry_date=%s WHERE id=%s",
                            (text, front_expiry, entry_id),
                        )
                    conn.commit()
                continue

        # H30 (S78): cachear el texto OCR ya extraido, para que
        # cualquier pasada futura de campos nuevos (numero de DNI,
        # categorias, etc.) no tenga que repetir descarga+OCR.
        if args.apply:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE document_explorer_documentindexentry "
                    "SET ocr_text=%s WHERE id=%s",
                    (text, entry_id),
                )
            conn.commit()

        expiry, issue, other = classify_dates_in_text(text)

        # H30 (sesion de continuidad tras S84/S85). Incidente real,
        # confirmado con evidencia visual por Miguel Angel: el PSM
        # automatico por defecto de Tesseract (PSM 3) se salta por
        # completo una linea de texto perfectamente legible a simple
        # vista cuando un sello/grafico la corta visualmente (caso
        # real: certificado CENTRO MEDICO ALAMEDA, linea "expido el
        # presente CERTIFICADO en... a 10 Enero 2022" ausente del OCR
        # pese a no estar tapada por el sello). Mismo patron ya
        # resuelto para EPIS en S82/S83 (reintento con otro PSM) --
        # portado aqui. Solo se reintenta cuando la primera pasada no
        # encontro NINGUNA fecha (ni siquiera "otras"), y solo para
        # PDF/imagen (el OCR es lo unico que puede fallar asi -- docx/
        # xlsx no pasan por Tesseract).
        #
        # H31 (S97, corregido tras incidente real S96). Cadena unica
        # de tres pasos -- Tesseract PSM automatico -> Tesseract PSM 6
        # -> EasyOCR (ultimo recurso) -- que se ejecuta siempre, en
        # ese orden, mientras no aparezca ninguna fecha. La version
        # anterior a esta correccion solo probaba EasyOCR cuando el
        # PSM 6 SI devolvia texto (aunque sin fecha): si el PSM 6 no
        # devolvia nada en absoluto, EasyOCR nunca llegaba a probarse
        # -- hueco real que S96 intento tapar añadiendo una SEGUNDA
        # llamada a EasyOCR mas abajo (duplicada con esta) en vez de
        # corregir esta condicion. Esa segunda llamada queda retirada.
        if not (expiry or issue or other) and name.lower().endswith(
            (".pdf", ".jpg", ".jpeg", ".png")
        ):
            retry_text = extract_text(name, data, psm=6)
            if retry_text:
                r_expiry, r_issue, r_other = classify_dates_in_text(retry_text)
                if r_expiry or r_issue or r_other:
                    print(
                        "  REINTENTO PSM 6 -- encontro fecha que el PSM por "
                        "defecto no vio"
                    )
                    text = retry_text
                    expiry, issue, other = r_expiry, r_issue, r_other
                    if args.apply:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE document_explorer_documentindexentry "
                                "SET ocr_text=%s WHERE id=%s",
                                (text, entry_id),
                            )
                        conn.commit()
                else:
                    # H30 (sesion tras S85): el reintento tambien
                    # fallo -- nunca descartar el PSM alternativo sin
                    # ver que leyo de verdad, podria ser un problema
                    # distinto (linea realmente ausente del OCR, no
                    # solo mal clasificada).
                    retry_preview = retry_text.replace("\n", " | ")
                    print(
                        "    REINTENTO PSM 6 tampoco encontro fecha "
                        "(%d caracteres): %r"
                        % (len(retry_preview), retry_preview)
                    )
                    text = retry_text
            else:
                print("    REINTENTO PSM 6 no devolvio texto")

            if not (expiry or issue or other):
                # H30 (sesion tras S85). TERCER NIVEL -- EasyOCR como
                # red de seguridad final, decision explicita de Miguel
                # Angel: Tesseract primero (rapido), EasyOCR solo
                # cuando Tesseract falla del todo (ni PSM automatico
                # ni PSM 6, tenga o no tenga texto ese PSM 6). Calidad
                # ya validada dos veces con el documento real que
                # motivo todo esto (certificado CENTRO MEDICO ALAMEDA,
                # lee "10 Enero 2022" donde Tesseract nunca lo
                # encontro) -- pero es ~6-7x mas lento (benchmark real
                # en h28-ocr-batch-1, 8 vCPU: 3.0s Tesseract vs 19.2s
                # EasyOCR), por eso es el ultimo recurso, nunca el
                # metodo por defecto.
                print("    Probando EASYOCR (ultimo recurso, mas lento)...")
                try:
                    easy_text = easyocr_extract_text(name, data)
                except Exception as exc:
                    easy_text = None
                    print("  EASYOCR ERROR -- %s" % exc)
                if easy_text:
                    e_expiry, e_issue, e_other = classify_dates_in_text(
                        easy_text
                    )
                    if e_expiry or e_issue or e_other:
                        print(
                            "  EASYOCR -- encontro fecha que Tesseract "
                            "no vio (ni PSM automatico ni PSM 6)"
                        )
                        text = easy_text
                        expiry, issue, other = e_expiry, e_issue, e_other
                        if args.apply:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "UPDATE document_explorer_documentindexentry "
                                    "SET ocr_text=%s WHERE id=%s",
                                    (text, entry_id),
                                )
                            conn.commit()
                    else:
                        easy_preview = easy_text.replace("\n", " | ")
                        print(
                            "    EASYOCR tampoco encontro fecha "
                            "(%d caracteres): %r"
                            % (len(easy_preview), easy_preview)
                        )
                        # H31 (S97). Aunque EasyOCR no encuentre
                        # fecha, se cachea su texto si aporta mas
                        # contenido que el ya guardado -- objetivo
                        # explicito de Miguel Angel: tener el OCR real
                        # de TODOS los documentos, encuentren fecha o
                        # no, para que la revision visual posterior de
                        # los que sigan sin fecha parta ya del mejor
                        # texto disponible.
                        if easy_text != text:
                            text = easy_text
                            if args.apply:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        "UPDATE document_explorer_documentindexentry "
                                        "SET ocr_text=%s WHERE id=%s",
                                        (text, entry_id),
                                    )
                                conn.commit()
                else:
                    print("    EASYOCR no devolvio texto")

        if expiry and issue:
            # Par 4a/4b -- unico caso en que llegan los dos campos a
            # la vez desde classify_dates_in_text. Escribir ambos en
            # la misma actualizacion.
            stats["par_4a_4b"] += 1
            print(
                "  OCR %s -> issue=%s / expiry=%s (par 4a/4b)"
                % (code, issue.isoformat(), expiry.isoformat())
            )
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry "
                        "SET issue_date=%s, expiry_date=%s WHERE id=%s",
                        (issue, expiry, entry_id),
                    )
                conn.commit()
            continue

        if expiry:
            stats["ocr_contexto"] += 1
            print("  OCR %s -> expiry=%s (contexto)" % (code, expiry.isoformat()))
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry "
                        "SET expiry_date=%s WHERE id=%s",
                        (expiry, entry_id),
                    )
                conn.commit()
            continue

        if issue:
            stats["ocr_contexto"] += 1
            print("  OCR %s -> issue=%s (contexto)" % (code, issue.isoformat()))
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry "
                        "SET issue_date=%s WHERE id=%s",
                        (issue, entry_id),
                    )
                conn.commit()
            continue

        default_field = DEFAULT_FIELD_BY_CODE.get(code)
        if default_field and len(set(other)) == 1:
            found = other[0]
            stats["ocr_unica_fecha"] += 1
            print(
                "  OCR %s -> %s=%s (unica fecha, defecto, ocr_text_len=%d)"
                % (code, default_field, found.isoformat(), len(text or ""))
            )
            if args.apply:
                with conn.cursor() as cur:
                    col = "expiry_date" if default_field == "expiry" else "issue_date"
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry "
                        "SET %s=%%s WHERE id=%%s" % col,
                        (found, entry_id),
                    )
                conn.commit()
            continue

        stats["sin_fecha"] += 1
        print(
            "  SIN FECHA reconocible (ocr_text_len=%d, fechas_sueltas=%s)"
            % (len(text or ""), other)
        )
        # H30 (sesion tras S85): guardar la imagen real que recibio
        # Tesseract, en el directorio de trabajo actual, para que
        # Miguel Angel la abra directamente y la compare con el PDF --
        # nunca mas asumir que es visible/tapado/lo-que-sea sin verla.
        if name.lower().endswith(".pdf"):
            debug_prefix = "debug_entry_%d" % entry_id
            extract_text(name, data, debug_save_prefix=debug_prefix)
            print("    Imagen real guardada en: %s\\%s_p0.png (y siguientes paginas si las hay)"
                  % (os.getcwd(), debug_prefix))
        preview = (text or "").replace("\n", " | ")
        print("    TEXTO REAL COMPLETO (%d caracteres): %r" % (len(preview), preview))

    total_min = (datetime.now() - start_time).total_seconds() / 60
    print("\n=== RESUMEN (%s, shard %d/%d) -- %.1f min ===" % (
        "APLICADO" if args.apply else "DRY-RUN",
        args.shard_index, args.shard_count, total_min,
    ))
    for key, value in stats.items():
        print("    %s: %d" % (key, value))

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
