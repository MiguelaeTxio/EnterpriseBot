# C:\EnterpriseBot\h28_migration_agent\local_ocr_classify.py
"""
H30 (S50) -- version LOCAL de `run_fase_b1_ocr_classify`, para correr
en el PC de Miguel Angel en vez de en el servidor de PythonAnywhere.

Origen real: el tarpit de CPU de PythonAnywhere (cuota de segundos
agotada, 6000 de 5000) hace que el OCR real -- lo mas caro de CPU de
toda la sesion -- vaya a paso de tortuga en el servidor. Miguel Angel,
verbatim: "Necesitariamos ejecutar esto desde local, porque se lleva
muchisima CPU."

NO depende de Django ni del proyecto completo -- es un script
independiente que:
1. Abre un tunel SSH a la base de datos MySQL de PythonAnywhere (solo
   disponible en cuentas de pago -- ver
   https://help.pythonanywhere.com/pages/AccessingMySQLFromOutsidePythonAnywhere/).
2. Se conecta a GCS directamente con la clave de servicio ya usada por
   el agente H28 (`agent_data\\service_account_key.json`).
3. Reutiliza LITERALMENTE la misma logica que
   `run_fase_b1_ocr_classify.py` (CONTENT_MARKERS, extraccion OCR,
   resolucion de fecha) y `run_fase_a_sweep_scoped.py` (SCOPE) -- 
   copiadas aqui tal cual, no reimplementadas, para no divergir del
   comando real del servidor.

REQUISITOS DE INSTALACION (una sola vez):

    pip install pymysql sshtunnel pytesseract PyMuPDF python-docx

Ademas, Tesseract-OCR tiene que estar instalado como programa aparte
en Windows (no es un paquete de pip) -- descargar el instalador de
UB Mannheim: https://github.com/UB-Mannheim/tesseract/wiki
Durante la instalacion, marcar el paquete de idioma "Spanish". Anotar
la ruta de instalacion (por defecto
"C:\\Program Files\\Tesseract-OCR\\tesseract.exe") y pegarla abajo en
TESSERACT_CMD si no coincide.

USO:

    python local_ocr_classify.py --limit 50          (dry-run, 50 docs)
    python local_ocr_classify.py --limit 50 --apply   (aplica de verdad)
    python local_ocr_classify.py --apply              (todo lo que quede)

Pide la contrasena de PythonAnywhere de forma interactiva (nunca en
texto plano en el script ni en ningun archivo).
"""
import argparse
import getpass
import io
import re
import sys
import unicodedata
from datetime import date

import pymysql
import pytesseract
import sshtunnel
from google.cloud import storage
from PIL import Image

try:
    import pymupdf as fitz  # PyMuPDF -- nombre nuevo del paquete
except ImportError:
    import fitz  # PyMuPDF -- nombre antiguo, por compatibilidad

from config import get_service_account_key_path

# ---------------------------------------------------------------
# CONFIGURACION -- editar si algo no coincide con tu entorno real
# ---------------------------------------------------------------
PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"  # global US -- NO eu.pythonanywhere.com
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"  # mismo usuario que PythonAnywhere en la mayoria de cuentas

# Si Tesseract no esta en el PATH del sistema, descomenta y ajusta:
# TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

BUCKET = "cgs_grupo_alvarez"
MACHINE_ROOT = "DOC. MAQUINAS"

# ---------------------------------------------------------------
# SCOPE -- copiado literal de run_fase_a_sweep_scoped.py (S50)
# ---------------------------------------------------------------
SCOPE = [
    (
        "%s/CABEZAS TRACTORAS (P)" % MACHINE_ROOT, "only", [
            "P-14 3232-DLM (TR)", "P-16 9184-FNK (TR)",
            "P-17 MA-7810-DB (AGG)", "P-18 7864-DXZ (TR)",
            "P-19 5083-GRV (TR)", "P-20 0964-GTM (TR)",
            "P-21 2455-CDM (TR)", "P-22 8099-JFK (AGG)",
            "P-23 4884-HNB (TR)", "P-24 8233-CKZ",
            "P-25 2323-FJH (PTE)", "P-26 7585-KHG", "P-27 3860-GLY",
            "SE7625CT VEIASA- CABEZ CON PLUMA",
        ],
    ),
    (
        "%s/CAMIONES BRAZO (B)" % MACHINE_ROOT, "all_except",
        ["PROPUESTA SEGURO CAMION BRAZO", "VEHICULOS DE BAJA"],
    ),
    ("%s/CARRETILLAS (T)" % MACHINE_ROOT, "all_except", ["CARRETILLA (HL)"]),
    (
        "%s/GRUAS MOVILES (A)" % MACHINE_ROOT, "all_except",
        ["OBSOLETO", "PROPUESTA SEGURO", "VEHICULOS BAJA", "MK 100"],
    ),
    (
        "%s/GRUPO ELECTROGENOS" % MACHINE_ROOT, "all_except",
        ["PEPE ASISTENCIA"],
    ),
    (
        "%s/PLATAFORMAS (Z)" % MACHINE_ROOT, "all_except",
        ["BAJAS", "ALTESUR", "ESTIBA PLATAFORMAS", "POLIZA RC"],
    ),
    (
        "%s/REMOLQUES Y GONDOLAS (R y G)/GONDOLAS" % MACHINE_ROOT,
        "all_except", ["BAJA DEFINITIVA"],
    ),
    (
        "%s/REMOLQUES Y GONDOLAS (R y G)/REMOLQUES" % MACHINE_ROOT,
        "all_except", ["BAJA"],
    ),
    (
        "%s/VEHICULOS DE EMPRESA" % MACHINE_ROOT, "all_except",
        ["DOCUMENT 1884JB (MUJER ADOLFO)"],
    ),
    ("%s/VENTOSA" % MACHINE_ROOT, "all_except", []),
]

# ---------------------------------------------------------------
# CONTENT_MARKERS -- copiado literal de run_fase_b1_ocr_classify.py (S50)
# ---------------------------------------------------------------
CONTENT_MARKERS = {
    "CE": [
        "DECLARACION DE CONFORMIDAD", "DECLARATION DE CONFORMITE",
        "DECLARATION OF CONFORMITY",
    ],
    "CERT_MANTENIMIENTO": [
        "REALIZA TODAS SUS REVISIONES DE MANTENIMIENTO",
        "COMO EMPRESA CONSERVADORA",
    ],
    "TARJETA_TRANSPORTE": ["TARJETA DE TRANSPORTE"],
    "SEGURO": ["DOMICILIACION DE PAGOS", "COMUNICACION OPERACION EN CUENTA"],
    "POLIZA_SEGURO": [
        "CONDICIONES PARTICULARES DEL SEGURO", "POLIZA DE SEGURO",
    ],
    "DECLARACION_HOMOLOGACION": [
        "HOMOLOGACION INDIVIDUAL", "CERTIFICADO DE HOMOLOGACION",
    ],
    "OCA": ["OCA GLOBAL", "ACREDITADO POR ENAC"],
    "C_ADECUACION": [
        "CERTIFICADO DE ADECUACION",
        "CONDICIONES DE SEGURIDAD Y SALUD EN LAS MAQUINAS",
    ],
    "IPO_ITC": [
        "ACTA DE INSPECCION PERIODICA", "INSPECCION PERIODICA OFICIAL",
        "INSPECCION PERIODICA DE GRUAS MOVILES",
    ],
}

_FOLDER_MACHINE_CODE_RE = re.compile(r"^([A-Z]+-?\d+)")

IMG_EXT = re.compile(r"\.(jpe?g|png|heic|gif|bmp|tiff?)$", re.IGNORECASE)
IMG_NAME = re.compile(
    r"^(img[-_]|whatsapp image|imagen de whatsapp|foto\b|_?foto\b)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------
# Funciones puras de date_verification_service.py (S48), copiadas
# tal cual, sin las partes de Gemini (no hace falta aqui).
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


def classify_dates_in_text(text):
    norm = _strip_accents(text).upper()
    expiry_candidates, issue_candidates, other_dates = [], [], []
    for match in _DATE_RE.finditer(norm):
        parsed = _parse_date(*match.groups())
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


def ocr_pdf_to_text(data, max_pages=2, dpi=300):
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=dpi)
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


def _is_photo(name):
    return bool(IMG_EXT.search(name) or IMG_NAME.match(name))


def _in_scope(parent_path):
    for root, mode, names in SCOPE:
        if mode == "only":
            for name in names:
                sub = "%s/%s" % (root, name)
                if parent_path == sub or parent_path.startswith(sub + "/"):
                    return True
            continue
        if parent_path == root or parent_path.startswith(root + "/"):
            for name in names:
                sub = "%s/%s" % (root, name)
                if parent_path == sub or parent_path.startswith(sub + "/"):
                    return False
            return True
    return False


def _match_content(text_upper):
    matched = set()
    for code, phrases in CONTENT_MARKERS.items():
        for phrase in phrases:
            if phrase in text_upper:
                matched.add(code)
                break
    if len(matched) == 1:
        return next(iter(matched)), None
    if len(matched) > 1:
        return None, matched
    return None, None


def _resolve_machine_code(parent_path, machine_codes):
    """Mismo criterio que resolve_machine_asset(): primer segmento de
    la ruta con forma de codigo de flota que exista de verdad en
    fleet_machineasset."""
    for segment in parent_path.split("/"):
        for word in segment.split():
            match = _FOLDER_MACHINE_CODE_RE.match(word.upper())
            if not match:
                continue
            candidate = match.group(1).replace("-", "")
            if candidate in machine_codes:
                return machine_codes[candidate]
    return None


def _resolve_machine_by_filename(name, machine_codes):
    for word in name.upper().replace(".PDF", "").split():
        match = _FOLDER_MACHINE_CODE_RE.match(word)
        if not match:
            continue
        candidate = match.group(1).replace("-", "")
        if candidate in machine_codes:
            return machine_codes[candidate]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, no la de MySQL): "
    )

    print("Abriendo tunel SSH a %s ..." % SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOSTNAME,
        ssh_username=PYTHONANYWHERE_USERNAME,
        ssh_password=pa_password,
        remote_bind_address=(MYSQL_HOSTNAME, 3306),
        # Correccion S50: version de paramiko instalada ya no tiene
        # DSSKey (claves DSA, obsoletas y retiradas) -- sshtunnel
        # intenta enumerar claves del sistema por defecto incluso
        # usando solo contrasena, y eso revienta con AttributeError.
        # Como aqui NUNCA usamos autenticacion por clave, se desactiva
        # la busqueda de claves por completo.
        host_pkey_directories=[],
        allow_agent=False,
    )
    tunnel.start()
    print("Tunel abierto, puerto local %d." % tunnel.local_bind_port)

    conn = pymysql.connect(
        host="127.0.0.1", port=tunnel.local_bind_port,
        user=MYSQL_USERNAME, passwd=pa_password,
        db=MYSQL_DB_NAME, charset="utf8mb4",
    )

    print("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        get_service_account_key_path()
    )
    bucket = gcs_client.bucket(BUCKET)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT code, id FROM document_explorer_documenttypecatalog "
            "WHERE is_active = 1"
        )
        type_ids = dict(cur.fetchall())

        cur.execute("SELECT code, id FROM fleet_machineasset")
        machine_codes = {
            code.upper().replace("-", ""): mid
            for code, mid in cur.fetchall()
        }

        cur.execute(
            "SELECT id FROM django_content_type "
            "WHERE app_label = 'fleet' AND model = 'machineasset'"
        )
        machine_ct_id = cur.fetchone()[0]

        cur.execute(
            "SELECT id, name, parent_path FROM document_explorer_documentindexentry "
            "WHERE entry_kind = 'FILE' AND document_type_id IS NULL "
            "AND deleted_at IS NULL AND purged_at IS NULL "
            "AND bucket = %s AND parent_path LIKE %s",
            (BUCKET, MACHINE_ROOT + "/%"),
        )
        raw_rows = cur.fetchall()

    print("Candidatos brutos (antes de SCOPE/fotos): %d" % len(raw_rows))

    candidatos = []
    fotos = 0
    for entry_id, name, parent_path in raw_rows:
        if not _in_scope(parent_path):
            continue
        if _is_photo(name):
            fotos += 1
            continue
        candidatos.append((entry_id, name, parent_path))

    print("Dentro de alcance, sin fotos: %d (fotos excluidas: %d)"
          % (len(candidatos), fotos))

    if args.limit:
        candidatos = candidatos[:args.limit]
    print("Se van a procesar en esta ejecucion: %d\n" % len(candidatos))

    stats = {
        "tipo_resuelto": 0, "tipo_y_fecha": 0, "dominio_sin_resolver": 0,
        "sin_tipo": 0, "ambiguo": 0, "extension_no_soportada": 0,
        "error": 0,
    }

    for i, (entry_id, name, parent_path) in enumerate(candidatos, start=1):
        if i % 20 == 0:
            conn.ping(reconnect=True)  # evita el wait_timeout de MySQL

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT blob_name FROM document_explorer_documentindexentry "
                    "WHERE id = %s", (entry_id,),
                )
                blob_name = cur.fetchone()[0]
            data = bucket.blob(blob_name).download_as_bytes()
            text = extract_text(name, data)
        except Exception as exc:
            stats["error"] += 1
            print("ERROR [%s] %s -- %s" % (parent_path, name, exc))
            continue

        if text is None:
            stats["extension_no_soportada"] += 1
            continue

        text_upper = _strip_accents(text).upper()
        code, ambiguous = _match_content(text_upper)

        if ambiguous:
            stats["ambiguo"] += 1
            print("AMBIGUO (%s)  [%s] %s" % (sorted(ambiguous), parent_path, name))
            continue
        if not code:
            stats["sin_tipo"] += 1
            continue

        machine_id = _resolve_machine_code(parent_path, machine_codes)
        if not machine_id and ("/RAE" in parent_path or "/CE PLATAFORMAS" in parent_path):
            machine_id = _resolve_machine_by_filename(name, machine_codes)
        if not machine_id:
            stats["dominio_sin_resolver"] += 1
            print("TIPO OK, DOMINIO SIN RESOLVER  [%s] %s -> %s"
                  % (parent_path, name, code))
            continue

        doc_type_id = type_ids.get(code)
        expiry_date = issue_date = None
        # tracks_expiry se consulta al vuelo solo si hace falta
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tracks_expiry FROM document_explorer_documenttypecatalog "
                "WHERE id = %s", (doc_type_id,),
            )
            tracks_expiry = bool(cur.fetchone()[0])
        if tracks_expiry:
            expiry_date, issue_date, _other = classify_dates_in_text(text)

        if expiry_date or issue_date:
            stats["tipo_y_fecha"] += 1
            print("TIPO+FECHA POR OCR  [%s] %s -> %s (expiry=%s issue=%s)"
                  % (parent_path, name, code, expiry_date, issue_date))
        else:
            stats["tipo_resuelto"] += 1
            print("TIPO POR OCR  [%s] %s -> %s" % (parent_path, name, code))

        if args.apply:
            with conn.cursor() as cur:
                if expiry_date and issue_date:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry SET "
                        "document_type_id=%s, domain_content_type_id=%s, "
                        "domain_object_id=%s, expiry_date=%s, issue_date=%s "
                        "WHERE id=%s",
                        (doc_type_id, machine_ct_id, machine_id,
                         expiry_date, issue_date, entry_id),
                    )
                elif expiry_date:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry SET "
                        "document_type_id=%s, domain_content_type_id=%s, "
                        "domain_object_id=%s, expiry_date=%s "
                        "WHERE id=%s",
                        (doc_type_id, machine_ct_id, machine_id,
                         expiry_date, entry_id),
                    )
                elif issue_date:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry SET "
                        "document_type_id=%s, domain_content_type_id=%s, "
                        "domain_object_id=%s, issue_date=%s "
                        "WHERE id=%s",
                        (doc_type_id, machine_ct_id, machine_id,
                         issue_date, entry_id),
                    )
                else:
                    cur.execute(
                        "UPDATE document_explorer_documentindexentry SET "
                        "document_type_id=%s, domain_content_type_id=%s, "
                        "domain_object_id=%s WHERE id=%s",
                        (doc_type_id, machine_ct_id, machine_id, entry_id),
                    )
            conn.commit()

    print("\n=== RESUMEN (%s) ===" % ("APLICADO" if args.apply else "DRY-RUN"))
    for key, value in stats.items():
        print("    %s: %d" % (key, value))

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
