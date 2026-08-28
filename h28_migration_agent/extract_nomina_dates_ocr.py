# C:\EnterpriseBot\h28_migration_agent\extract_nomina_dates_ocr.py
"""
H30 (S78). Extractor OCR de `issue_date` para documentos NOMINA de
personal activo (`PersonIdentity.is_active_employee=True`) sin fecha
reconocible por heuristica de nombre de archivo -- punto 3 de la hoja
de ruta S78, fase OCR.

Script STANDALONE, mismo patron que `local_ocr_classify.py` (H30 S50):
NO depende de Django ni del proyecto completo. Abre tunel SSH a la
base de datos MySQL de PythonAnywhere, se conecta a GCS con la clave
de servicio del agente H28, y escribe con SQL directo (pymysql).

QUEDA TERMINANTEMENTE PROHIBIDO ejecutar esto en la consola Bash de
PythonAnywhere (cuota de CPU) -- se ejecuta SIEMPRE en una VM de
computo (h28-ocr-batch-1/2/3/4) o en el PC de Miguel Angel, dentro del
venv `ocr_venv` (pymysql/sshtunnel/pytesseract/PyMuPDF ya instalados
ahi, ver SESSION_VARIABLES.md seccion "VM h28-ocr-batch").

REQUISITOS DE INSTALACION (si no estan ya, ver local_ocr_classify.py):
    pip install pymysql sshtunnel pytesseract PyMuPDF python-docx

USO:
    python3 extract_nomina_dates_ocr.py --limit 5          (dry-run, 5 docs)
    python3 extract_nomina_dates_ocr.py --apply              (todos los pendientes)

Pide contrasenas de forma interactiva (nunca en texto plano).
"""
import argparse
import getpass
import io
import re
import unicodedata
from datetime import date, datetime

import pymysql

try:
    import pymupdf as fitz  # PyMuPDF -- nombre nuevo del paquete
except ImportError:
    import fitz  # PyMuPDF -- nombre antiguo, por compatibilidad

import paramiko
if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

import pytesseract
import sshtunnel
from google.cloud import storage
from PIL import Image

from config import get_service_account_key_path

# ---------------------------------------------------------------
# CONFIGURACION -- igual que local_ocr_classify.py
# ---------------------------------------------------------------
PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"

# ---------------------------------------------------------------
# Extraccion de texto -- copiado tal cual de local_ocr_classify.py
# ---------------------------------------------------------------
SAFE_MAX_PIXELS = 80_000_000
MIN_DPI = 100


def ocr_pdf_to_text(data, max_pages=2, dpi=300):
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


def extract_text(filename, data):
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return ocr_pdf_to_text(data)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return ocr_image_to_text(data)
    if name_lower.endswith(".docx"):
        return docx_to_text(data)
    return None


# ---------------------------------------------------------------
# Deteccion de fecha especifica de Nomina (H30 S78) -- las palabras
# de contexto de caducidad/expedicion (CADUCA/EXPEDICION...) no
# aparecen en una nomina real; aqui se buscan palabras de periodo de
# liquidacion antes de caer a "unica fecha plausible del documento".
# ---------------------------------------------------------------
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
_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _parse_date_ddmmaaaa(day_s, month_s, year_s):
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


def extraer_fecha_nomina(text):
    """Devuelve un `date` (dia 1 del mes de devengo) o None."""
    norm = _strip_accents(text).upper()

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

    otras = []
    for match in _DATE_RE.finditer(norm):
        parsed = _parse_date_ddmmaaaa(*match.groups())
        if parsed:
            otras.append(parsed)
    if len(set(otras)) == 1:
        return otras[0]

    return None


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, para el tunel SSH): "
    )
    mysql_password = getpass.getpass(
        "Contrasena de MySQL (panel PythonAnywhere, pestana 'Databases'): "
    )

    print("Abriendo tunel SSH a %s ..." % SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOSTNAME,
        ssh_username=PYTHONANYWHERE_USERNAME,
        ssh_password=pa_password,
        remote_bind_address=(MYSQL_HOSTNAME, 3306),
        host_pkey_directories=[],
        allow_agent=False,
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

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM document_explorer_documenttypecatalog "
            "WHERE code = 'NOMINA'"
        )
        nomina_type_id = cur.fetchone()[0]

        cur.execute(
            "SELECT id FROM django_content_type "
            "WHERE app_label = 'document_explorer' AND model = 'personidentity'"
        )
        person_ct_id = cur.fetchone()[0]

        cur.execute(
            "SELECT e.id, e.name, e.bucket, e.blob_name "
            "FROM document_explorer_documentindexentry e "
            "JOIN document_explorer_personidentity p "
            "  ON e.domain_object_id = p.id "
            "WHERE e.document_type_id = %s "
            "AND e.domain_content_type_id = %s "
            "AND e.issue_date IS NULL "
            "AND e.deleted_at IS NULL AND e.purged_at IS NULL "
            "AND p.is_active_employee = 1 "
            "ORDER BY e.id",
            (nomina_type_id, person_ct_id),
        )
        rows = cur.fetchall()

    print("Candidatos NOMINA sin issue_date, personal activo: %d" % len(rows))
    if args.limit:
        rows = rows[:args.limit]
    print("Se van a procesar en esta ejecucion: %d\n" % len(rows))

    stats = {"con_fecha": 0, "sin_fecha": 0, "sin_extractor": 0, "error": 0}

    for i, (entry_id, name, bucket_name, blob_name) in enumerate(rows, start=1):
        _log("[%d/%d] procesando: %s" % (i, len(rows), name))
        try:
            bucket = gcs_client.bucket(bucket_name)
            data = bucket.blob(blob_name).download_as_bytes()
            text = extract_text(name, data)
        except Exception as exc:
            stats["error"] += 1
            print("ERROR [%s] -- %s" % (name, exc))
            continue

        if text is None:
            stats["sin_extractor"] += 1
            print("SIN EXTRACTOR (extension no soportada): %s" % name)
            continue

        fecha = extraer_fecha_nomina(text)
        if not fecha:
            stats["sin_fecha"] += 1
            print("SIN FECHA reconocible: %s" % name)
            continue

        stats["con_fecha"] += 1
        print("OK: %s -> issue_date=%s" % (name, fecha.isoformat()))

        if args.apply:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE document_explorer_documentindexentry "
                    "SET issue_date=%s WHERE id=%s",
                    (fecha, entry_id),
                )
            conn.commit()

    print("\n=== RESUMEN (%s) ===" % ("APLICADO" if args.apply else "DRY-RUN"))
    for key, value in stats.items():
        print("    %s: %d" % (key, value))

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
