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
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime

import pymysql
import pytesseract

# Correccion S50: evitar depender de escribir en C:\Program Files\
# (requiere administrador) para el paquete de idioma "spa" -- se usa
# una carpeta propia junto al script en su lugar. Coloca ahi
# spa.traineddata (ver instrucciones de instalacion mas abajo).
#
# S54, bug real detectado en vivo en la VM Linux: este workaround es
# especifico de Windows (permisos de Program Files). En Linux, `apt-
# get install tesseract-ocr-spa` ya instala el paquete de idioma en
# la ruta real del sistema -- forzar TESSDATA_PREFIX aqui tapaba esa
# ruta con una carpeta local vacia y rompia Tesseract por completo
# ("Tesseract couldn't load any languages!"). Igual que el bug de
# get_agent_data_dir() de esta misma sesion: un fix pensado para una
# plataforma, aplicado sin querer en la otra.
if os.name == "nt":
    _TESSDATA_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tessdata",
    )
    os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR

import sshtunnel
from google.cloud import storage
from PIL import Image

# Correccion S50: la version de paramiko instalada retiro DSSKey
# (claves DSA, obsoletas por seguridad), pero sshtunnel todavia
# construye un diccionario que lo referencia INCONDICIONALMENTE al
# arrancar, aunque no se use ninguna clave (solo contrasena). Se
# rellena el hueco con un valor de relleno -- nunca se ejecuta de
# verdad porque este script no usa autenticacion por clave.
import paramiko
if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

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
PERSONAL_ROOT = "DOC. PERSONAL"

# S54: ampliacion real de alcance. El SCOPE original (S50) SOLO cubria
# DOC. MAQUINAS, curado a mano por familia. DOC. PERSONAL nunca se
# habia tocado por esta via -- confirmado con datos reales que los
# "miles de archivos de mas" que parecian una regresion eran, en
# realidad, la poblacion real de DOC. PERSONAL, nunca medida hasta
# hoy (ver anexo H30 S54). Anadido como entrada "all_except" propia,
# sin restringir por familia (a diferencia de DOC. MAQUINAS, que si
# sigue acotado a las familias ya validadas). EPIS excluido aqui
# mismo: va por un pipeline de extraccion aparte hacia EpiDelivery,
# nunca por document_type.

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
    (PERSONAL_ROOT, "all_except", []),
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
        # Añadido S51 (muestreo real de 3 ejemplos, sample_type_patterns.py):
        # verificado 3/3, sin contaminación cruzada con ningún otro tipo.
        "CONSTE, A LOS EFECTOS",
    ],
    "OCA": ["OCA GLOBAL", "ACREDITADO POR ENAC"],
    "C_ADECUACION": [
        "CERTIFICADO DE ADECUACION",
        "CONDICIONES DE SEGURIDAD Y SALUD EN LAS MAQUINAS",
    ],
    "IPO_ITC": [
        "ACTA DE INSPECCION PERIODICA", "INSPECCION PERIODICA OFICIAL",
        "INSPECCION PERIODICA DE GRUAS MOVILES",
        # Añadido S51, mismo criterio que DECLARACION_HOMOLOGACION arriba.
        "INDICADA, SEGUN LAS COMPROBACIONES",
    ],
    # --- Añadidos S51: muestreo real de 3 ejemplos por cada uno de los
    # 77 tipos activos (sample_type_patterns.py), tras confirmar que
    # el barrido de 24h solo cubria 9 tipos de 77 (15,9% de acierto).
    # Cada frase verificada 2/3 o 3/3 en muestras propias Y sin
    # contaminacion cruzada con ningun otro tipo activo (las
    # contaminaciones contra MANDATO/DOC_BAJA_DEFINITIVA no cuentan --
    # son los tipos fusionados en la migracion 0033, ya inactivos).
    "CERTIFICADO_PODERES": [
        "DOCUMENTO DE REPRESENTACION DE PERSONAS JURIDICAS",
    ],
    "BAJA_DEFINITIVA": ["DATOS BAJA DEFINITIVA"],
    "BAJA_TEMPORAL": ["CLASES Y MOTIVOS DE LA BAJA"],
    "CERT_EXENCION_PERMISO": ["EXENTA DEL PERMISO DE CIRCULACION"],
    "CERT_NO_TARJ_TTES": ["NO POSEE TARJETA DE TRANSPORTES"],
    "ALTA": ["CON QUE SE RECONOCE"],
    "CSS": ["CERTIFICADO DE ESTAR AL CORRIENTE", "DEUDAS YA VENCIDAS"],
    "IDC": [
        "INFORME DE DATOS PARA LA COTIZACION", "CONTINGENCIAS PROFESIONALES:",
    ],
    "MOD_145": ["QUE, A EFECTOS DEL"],
    "EXCEDENCIA": ["EXCEDENCIA VOLUNTARIA"],
    "ENTREGA_INFORMACION": ["INFORMACION EN MATERIA PREVENTIVA"],
    "RECONOCIMIENTO_MEDICO": ["RECONOCIMIENTO MEDICO"],
    "CARTA_VERDE": ["CERTIFICADO INTERNACIONAL DE SEGURO", "GREEN CARD"],
    "RAE": ["DOCUMENTO ELECTRONICO EN LA"],
    "REVISION_ESLINGAS": ["REVISION DE ESLINGAS"],
    # --- Añadidos S54: lectura manual directa de sample0/1/2_output.txt
    # (185 muestras reales, S51/S53) tras descartar el enfoque de script
    # de frecuencia de lineas (demasiado ruido: nombres de persona,
    # fechas concretas, nombre de la propia empresa colandose como
    # "candidata" por coincidencia entre solo 2-3 muestras). Cada frase
    # leida y verificada a mano, sin contaminacion cruzada contra los
    # 24 tipos ya existentes arriba NI entre si -- incluida una
    # contaminacion real detectada y corregida en el momento:
    # DOC_VENTA/CONTRATO_COMPRAVENTA comparten la misma clausula de
    # "la parte compradora hace expresa mencion... a cuerpo cierto",
    # asi que DOC_VENTA se queda sin marcador por ahora, no se fuerza
    # uno que rompa la deteccion de CONTRATO_COMPRAVENTA. Varios tipos
    # mas quedan sin cubrir por OCR degradado en las muestras
    # (FICHA_TECNICA, ITV, CAMBIO_TITULARIDAD, DNI, DNI_COMPRADOR, CAP,
    # LIBRO_HISTORIAL) o por ser demasiado heterogeneos entre muestras
    # (CURSO, GARANTIA_FABRICANTE, PRESTAMO) -- no se fuerza una frase
    # de baja confianza solo por rellenar.
    "TACOGRAFO": ["TARJETA DE CONDUCTOR"],
    "CONTRATO_ARRENDAMIENTO": ["CONTRATO DE ARRENDAMIENTO DE MAQUINARIA"],
    "RECIBO_LEASING": ["RECIBO-FACTURA POR CUOTA"],
    "INFORME_INCIDENCIAS": ["INFORME DE INCIDENCIAS MAQUINA"],
    "SEG_SOCIAL": ["ASIGNACION DE NUMERO DE SEGURIDAD SOCIAL"],
    "CARNET_CONDUCIR": ["PERMISO DE CONDUCCION REINO DE ESPANA"],
    "VACACIONES": ["PARTE DE VACACIONES"],
    "NOMINA": ["DETERMINACION DE LAS BASES DE COTIZACION A LA SEGURIDAD SOCIAL"],
    "IVTM": ["IMPUESTO SOBRE VEHICULOS DE TRACCION MECANICA"],
    "PROVISION_FONDOS": ["AUTORIZACION PROVISION FONDOS"],
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


def _log(msg):
    """Imprime con hora real y sin buffer -- S54, peticion explicita
    de Miguel Angel: procesos de horas deben ser verbosos de verdad,
    para que conectarse en cualquier momento (desde el movil, desde
    otro PC) muestre actividad reciente real, nunca una pantalla
    muda sin saber si sigue vivo o se ha quedado colgado.
    ---
    Prints with real timestamp and no buffering -- S54, Miguel
    Angel's explicit request: hours-long processes must be genuinely
    verbose, so connecting at any point (from the phone, from
    another PC) shows real recent activity, never a silent screen
    with no way to tell if it is still alive or stuck.
    """
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


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


# Fecha al final del nombre de subcarpeta real, mismo patron que
# run_fase_a_sweep.py (S54): "15-3-17", "8-10-16".
_TRAILING_DATE_RE = re.compile(r"\s+\d{1,2}-\d{1,2}-\d{2,4}\s*$")


def _resolve_person_by_folder(parent_path, person_folders):
    """Mismo criterio que _resolve_person_by_folder() de
    run_fase_a_sweep.py: folder_path CONTENEDOR de la persona, nunca
    por parecido de nombre. person_folders: dict folder_path -> pk.
    """
    segments = parent_path.split("/")
    candidates = {
        person_folders[p]
        for i in range(1, len(segments) + 1)
        if (p := "/".join(segments[:i])) in person_folders
    }
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _resolve_person_by_name(parent_path, person_name_index):
    """Mismo criterio que _resolve_person_by_name() de
    run_fase_a_sweep.py (S54): SOLO coincidencia exacta y UNICA contra
    el nombre real de la subcarpeta inmediata, nunca ambigua.
    """
    last_segment = parent_path.rstrip("/").split("/")[-1]
    candidate = _TRAILING_DATE_RE.sub("", last_segment)
    candidate = _strip_accents(candidate).upper().strip()
    pks = person_name_index.get(candidate)
    if pks and len(pks) == 1:
        return next(iter(pks))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--shard-count", type=int, default=1,
        help=(
            "S51 (VM en la nube, procesos paralelos sin solape): total "
            "de procesos que se van a lanzar a la vez, p.ej. 3."
        ),
    )
    parser.add_argument(
        "--shard-index", type=int, default=0,
        help=(
            "Indice de este proceso dentro del reparto (0-based, "
            "0..shard-count-1). Cada entry_id va a exactamente un "
            "shard (entry_id %% shard_count == shard_index) -- sin "
            "solape posible entre procesos, cada fila la toca uno "
            "solo."
        ),
    )
    args = parser.parse_args()
    if not (0 <= args.shard_index < max(args.shard_count, 1)):
        parser.error("--shard-index debe estar entre 0 y --shard-count - 1")

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, para el tunel SSH): "
    )
    mysql_password = getpass.getpass(
        "Contrasena de MySQL (distinta de la anterior -- panel "
        "PythonAnywhere, pestana 'Databases'): "
    )
    # Diagnostico temporal S50: nunca imprime la contrasena en si,
    # solo su longitud -- para descartar un fallo de pegado en
    # PowerShell (caracteres perdidos/de mas al pegar en getpass).
    print("[diagnostico] contrasena de MySQL capturada: %d caracteres "
          "(compara tu mismo si coincide con lo que esperabas)"
          % len(mysql_password))

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
        user=MYSQL_USERNAME, passwd=mysql_password,
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
            "SELECT id, given_name, first_surname, second_surname, "
            "folder_path FROM document_explorer_personidentity"
        )
        person_folders = {}
        person_name_index = {}
        for pid, given, first, second, folder_path in cur.fetchall():
            person_folders[folder_path] = pid
            given_u = _strip_accents(given or "").upper().strip()
            first_u = _strip_accents(first or "").upper().strip()
            second_u = _strip_accents(second or "").upper().strip()
            if not given_u or not first_u:
                continue
            for key in (
                f"{given_u} {first_u}", f"{first_u} {given_u}",
                (f"{given_u} {first_u} {second_u}" if second_u else ""),
                (f"{first_u} {second_u} {given_u}" if second_u else ""),
            ):
                if key:
                    person_name_index.setdefault(key, set()).add(pid)

        cur.execute(
            "SELECT id FROM django_content_type "
            "WHERE app_label = 'fleet' AND model = 'machineasset'"
        )
        machine_ct_id = cur.fetchone()[0]

        cur.execute(
            "SELECT id FROM django_content_type "
            "WHERE app_label = 'document_explorer' AND model = 'personidentity'"
        )
        person_ct_id = cur.fetchone()[0]

        shard_clause = ""
        shard_params = (BUCKET, MACHINE_ROOT + "/%", PERSONAL_ROOT + "/%")
        if args.shard_count > 1:
            shard_clause = " AND id %% %s = %s"
            shard_params = shard_params + (args.shard_count, args.shard_index)

        cur.execute(
            "SELECT id, name, parent_path FROM document_explorer_documentindexentry "
            "WHERE entry_kind = 'FILE' AND document_type_id IS NULL "
            "AND deleted_at IS NULL AND purged_at IS NULL "
            "AND bucket = %s AND (parent_path LIKE %s OR parent_path LIKE %s) "
            "AND parent_path NOT LIKE '%%EPIS%%'" + shard_clause,
            shard_params,
        )
        raw_rows = cur.fetchall()

    if args.shard_count > 1:
        print("Reparto: shard %d de %d (entry_id %% %d == %d)"
              % (args.shard_index, args.shard_count, args.shard_count,
                 args.shard_index))
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
        "tipo_resuelto": 0, "tipo_y_fecha": 0, "tipo_ok_dominio_pendiente": 0,
        "sin_tipo": 0, "ambiguo": 0, "extension_no_soportada": 0,
        "error": 0,
    }

    _log("EMPEZANDO barrido real: %d candidatos a procesar (modo %s)"
         % (len(candidatos), "APLICADO" if args.apply else "DRY-RUN"))
    start_time = time.monotonic()
    HEARTBEAT_EVERY = 25

    for i, (entry_id, name, parent_path) in enumerate(candidatos, start=1):
        _log("[%d/%d] procesando: %s / %s"
             % (i, len(candidatos), parent_path, name))
        if i % 20 == 0:
            conn.ping(reconnect=True)  # evita el wait_timeout de MySQL

        if i % HEARTBEAT_EVERY == 0:
            elapsed = time.monotonic() - start_time
            ritmo = i / elapsed if elapsed > 0 else 0
            restantes = len(candidatos) - i
            eta_min = (restantes / ritmo / 60) if ritmo > 0 else 0
            _log(
                "--- LATIDO: %d/%d hechos (%.1f%%) | %.1f min transcurridos "
                "| ritmo %.1f docs/min | ETA restante ~%.0f min | "
                "tipo_resuelto=%d tipo_y_fecha=%d dominio_pendiente=%d "
                "sin_tipo=%d ambiguo=%d error=%d ---"
                % (
                    i, len(candidatos), 100.0 * i / len(candidatos),
                    elapsed / 60, ritmo * 60, eta_min,
                    stats["tipo_resuelto"], stats["tipo_y_fecha"],
                    stats["tipo_ok_dominio_pendiente"], stats["sin_tipo"],
                    stats["ambiguo"], stats["error"],
                )
            )

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

        domain_ct_id = domain_obj_id = None
        if parent_path.startswith(MACHINE_ROOT):
            if machine_id:
                domain_ct_id, domain_obj_id = machine_ct_id, machine_id
        else:
            person_id = _resolve_person_by_folder(parent_path, person_folders)
            if not person_id:
                person_id = _resolve_person_by_name(
                    parent_path, person_name_index,
                )
            if person_id:
                domain_ct_id, domain_obj_id = person_ct_id, person_id

        if not domain_obj_id:
            stats["tipo_ok_dominio_pendiente"] += 1
            print("TIPO OK, DOMINIO PENDIENTE -- tipo se guarda igual  [%s] %s -> %s"
                  % (parent_path, name, code))

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
                fields = ["document_type_id=%s"]
                values = [doc_type_id]
                if domain_obj_id:
                    fields += ["domain_content_type_id=%s", "domain_object_id=%s"]
                    values += [domain_ct_id, domain_obj_id]
                if expiry_date:
                    fields.append("expiry_date=%s")
                    values.append(expiry_date)
                if issue_date:
                    fields.append("issue_date=%s")
                    values.append(issue_date)
                values.append(entry_id)
                cur.execute(
                    "UPDATE document_explorer_documentindexentry SET "
                    + ", ".join(fields) + " WHERE id=%s",
                    tuple(values),
                )
            conn.commit()

    total_min = (time.monotonic() - start_time) / 60
    _log("TERMINADO -- %d candidatos procesados en %.1f minutos"
         % (len(candidatos), total_min))
    print("\n=== RESUMEN (%s) ===" % ("APLICADO" if args.apply else "DRY-RUN"))
    for key, value in stats.items():
        print("    %s: %d" % (key, value))

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
