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

# Si Tesseract no esta en el PATH del sistema (Windows), descomenta y
# ajusta -- nunca se commitea activo, es configuracion local por
# maquina (ver SESSION_VARIABLES.md):
# TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

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


def ocr_pdf_to_text(data, max_pages=2, dpi=400):
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
        text_parts.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(text_parts)


def ocr_image_to_text(data):
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="spa")


def docx_to_text(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


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


def extract_text(filename, data):
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return ocr_pdf_to_text(data)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return ocr_image_to_text(data)
    if name_lower.endswith(".docx"):
        return docx_to_text(data)
    if name_lower.endswith(".doc"):
        return doc_to_text(data)
    if name_lower.endswith((".xlsx", ".xls")):
        return xlsx_to_text(data)
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
# ---------------------------------------------------------------
_EXPIRY_CONTEXT = [
    "CADUCA", "CADUCIDAD", "VALID", "VENCE", "VENCIMIENTO", "HASTA EL",
    "PROXIMA REVISION", "PROXIMA INSPECCION", "FECHA LIMITE",
]
_ISSUE_CONTEXT = [
    "EXPEDICION", "EXPEDIDO", "EXPEDIDA", "EMISION", "EMITIDO", "EMITIDA",
]
_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")
_CONTEXT_WINDOW = 70

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
    "CAMBIO_EMPRESA_SUBROGACION": "issue", "CAMBIO_IRPF": "issue",
    "CARTA_BAJA_VOLUNTARIA": "issue", "CERTIFICADO_GIBRALTAR": "issue",
    "CERTIF_TRABAJO_COLEGIO": "issue", "COMUNICACION_CONTRATO": "issue",
    "COMUNICACION_JORNADA": "issue", "COMUNICADO_SEPE": "issue",
    "CONVENIO_FCT": "issue", "CSS": "issue", "IDC": "issue",
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
    norm = _strip_accents(text).upper()
    expiry_candidates, issue_candidates, other_dates = [], [], []
    for match in _DATE_RE.finditer(norm):
        parsed = _parse_date_dmY(*match.groups())
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + norm[match.end():window_end]
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
            "WHERE e.domain_content_type_id = %s "
            "AND t.domain = 'PERSONAL' AND t.tracks_expiry = 1 "
            "AND t.ocr_unreliable = 0 "
            "AND e.expiry_date IS NULL AND e.issue_date IS NULL "
            "AND e.deleted_at IS NULL AND e.purged_at IS NULL "
            "AND p.is_active_employee = 1"
            + shard_clause +
            " ORDER BY e.id",
            (person_ct_id,) + shard_params,
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
        "ocr_unica_fecha": 0, "sin_fecha": 0, "sin_extractor": 0,
        "error": 0,
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
                "  OCR %s -> %s=%s (unica fecha, defecto)"
                % (code, default_field, found.isoformat())
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
        print("  SIN FECHA reconocible")

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
