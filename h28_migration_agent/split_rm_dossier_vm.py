# C:\EnterpriseBot\h28_migration_agent\split_rm_dossier_vm.py
"""
H30 (S59). Version standalone (sin Django) de `split_rm_dossier`, para
correr en la VM Linux de OCR (mismo patron que `local_ocr_classify.py`
-- tunel SSH a MySQL de PythonAnywhere, GCS directo, `--shard-count`/
`--shard-index` para varios procesos en paralelo sin solape).

Reparto de responsabilidad, deliberado (nunca escribe una fila nueva
en `document_explorer_documentindexentry` directamente por SQL --
`blob_name_hash`/`parent_path_hash`/creacion de carpetas antecesoras/
propagacion de `total_size_bytes` viven en `index_writer.refresh_folder()`,
logica Django ya validada que este script no reimplementa):

1. AQUI (VM, todo el coste de OCR): descarga cada dosier, OCR de
   TODAS las paginas, extrae nombre/DNI/fecha/aptitud por regex,
   corrige la letra de control del DNI si el OCR la leyo como
   digito, resuelve `PersonIdentity` por DNI (lectura SQL de solo
   lectura), parte cada pagina en un PDF nuevo y lo SUBE a GCS ya en
   su ubicacion final. Nunca escribe en MySQL.
2. Escribe un manifiesto JSONL (`rm_split_manifest_shard{N}.jsonl`)
   con el resultado de cada blob subido y de cada dosier completo.
3. DESPUES (PythonAnywhere, sin OCR, barato): el comando de gestion
   Django `apply_rm_split_manifest` lee ese manifiesto, indexa cada
   blob nuevo con `refresh_folder()`, asigna document_type/dominio, y
   manda a papelera el dosier original cuando todas sus paginas ya
   se repartieron.

USO (una ventana de PowerShell por shard, `gcloud compute ssh` cada
vez -- ver SESSION_VARIABLES.md, "Ctrl+B D no funciona en esta
consola"):

    python3 split_rm_dossier_vm.py --shard-count 3 --shard-index 0
    python3 split_rm_dossier_vm.py --shard-count 3 --shard-index 1
    python3 split_rm_dossier_vm.py --shard-count 3 --shard-index 2

Pide credenciales de forma interactiva, igual que
`local_ocr_classify.py` -- nunca en texto plano.
"""
import argparse
import getpass
import io
import json
import re
import time
import unicodedata
from datetime import date, datetime

import pymysql
import pytesseract
import sshtunnel
from google.cloud import storage
from PIL import Image

import paramiko
if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from config import get_service_account_key_path

# ---------------------------------------------------------------
# CONFIGURACION -- identica a local_ocr_classify.py
# ---------------------------------------------------------------
PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"

BUCKET = "cgs_grupo_alvarez"
RM_ROOT = "DOC. PERSONAL/RECONOCIMIENTOS MEDICOS"
PENDING_REVIEW_FOLDER = "DOC. PERSONAL/DOCUMENTACION PENDIENTE DE REVISION"
RM_TYPE_CODE = "RECONOCIMIENTO_MEDICO"

_DNI_CHECK_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX_DIGIT = {"X": "0", "Y": "1", "Z": "2"}

RECORD_PATTERNS = [
    ("MEDIOS_PREVENCION_SUR", re.compile(
        r"trabajador\s+(?P<nombre>[A-ZÁÉÍÓÚÑ ,.]+?)\s+y\s+DNI\s+"
        r"(?P<dni>[0-9A-Za-z]{9})"
        r".{0,400}?d[ií]a\s+(?P<fecha>\d{1,2}\s+de\s+\w+\s+de\s+\d{4})"
        r".{0,800}?resulta\s+(?P<aptitud>NO\s+APTO|APTO)",
        re.IGNORECASE | re.DOTALL,
    )),
    ("FRATERNIDAD_MUPRESPA", re.compile(
        r"con\s+fecha\s+(?P<fecha>\d{1,2}/\d{1,2}/\d{4})"
        r".{0,60}?examen\s+de\s+salud\s+(?:periodico|inicial)\s+de\s+D\.\s+"
        r"(?P<nombre>[A-ZÁÉÍÓÚÑ ,.]+?)\s+con\s+N[.\s!|IL1]{1,6}F\.?\s+"
        r"(?P<dni>[0-9A-Za-z]{9})"
        r".{0,900}?(?P<aptitud>NO\s+APTO|APTO)\s+PARA\s+EL\s+DESEMPE.O"
        r"\s+DEL\s+PUESTO\s+DE\s+TRABAJO",
        re.IGNORECASE | re.DOTALL,
    )),
    ("FRATERNIDAD_NOTIFICACION_PENDIENTE", re.compile(
        r"se\s+ha\s+realizado\s+con\s+fecha\s+"
        r"(?P<fecha>\d{1,2}\s+de\s+\w+\s+de\s+\d{4})"
        # "D/Dña" tolerante a 0-2 caracteres de ruido OCR entre la D y
        # la "a" final (visto real: "D/Dfña") -- calibrado S61.
        r".{0,400}?al\s+trabajador\s+de\s+su\s+empresa\s+D\s*/\s*D.{0,2}a\s+"
        # Marcador D.N.I. tolerante a ruido OCR sobre la "I" final --
        # calibrado S61 contra 7 ejemplos reales ("D.N.l.", "D.N./.",
        # "D.N.!.", "D.N.1.", "D.N.]."), mismo criterio ya aplicado al
        # marcador N.I.F. del patron FRATERNIDAD_MUPRESPA.
        r"(?P<nombre>[A-ZÁÉÍÓÚÑ ,.\n]+?)\s+con\s+D\.?\s*N\.?\s*[IL1!/\]]\.?\s+"
        r"(?P<dni>[0-9A-Za-z]{9})",
        re.IGNORECASE | re.DOTALL,
    )),
    # Nuevo proveedor de prevencion distinto de Fraternidad-Muprespa,
    # calibrado S61 contra 4 ejemplos reales ("INFORME DE APTITUD
    # MEDICA", "SERVICIO DE PREVENCION AJENO", cabecera "GRUPO").
    # Aptitud captura literal (APTO / NO APTO / APTO EN OBSERVACION /
    # SIN APTITUD) en vez de limitarse a APTO|NO APTO como los otros
    # patrones -- visto real que este proveedor usa mas variantes.
    ("ANP_INFORME_APTITUD", re.compile(
        r"INFORME\s+DE\s+APTITUD\s+M.DICA"
        r".{0,50}?Sr\.?\s*"
        r"(?P<nombre>[A-ZÁÉÍÓÚÑ ,.]+?),\s*NIF:\s*"
        r"(?P<dni>[0-9]{7,9}\s?[0-9A-Za-z]?)"
        r".{0,300}?con\s+fecha\s+(?P<fecha>\d{1,2}/\d{1,2}/\d{4})"
        # Hueco tolerante a ruido OCR de maquetacion (numeros de
        # columna, simbolos sueltos) entre "considera :" y la
        # aptitud -- visto real ("considera :\n3\n> APTO...").
        r".{0,300}?considera\s*:.{0,20}?"
        r"(?P<aptitud>[A-ZÁÉÍÓÚÑ ]+?)\s+para\s+su\s+trabajo\s+habitual",
        re.IGNORECASE | re.DOTALL,
    )),
]


def _match_record(clean_text):
    for pattern_name, pattern in RECORD_PATTERNS:
        match = pattern.search(clean_text)
        if match:
            return pattern_name, match
    return None, None


_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _sanitize_token(value):
    """Copiado literal de naming_service._sanitize_token (S59) --
    este script no importa Django, no puede reutilizar el original."""
    ascii_only = _strip_accents(value or "")
    collapsed = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_")
    return collapsed.upper()


def _build_filename_personal(first_surname, second_surname, given_name,
                              type_code, exam_date):
    """Copiado literal de naming_service.build_filename_personal (S59)."""
    tokens = [
        _sanitize_token(part)
        for part in (first_surname, second_surname, given_name, type_code)
        if part
    ]
    tokens.append(exam_date.strftime("%Y%m%d"))
    return "_".join(tokens) + ".pdf"


def _correct_ocr_dni(raw):
    """Copiado literal de split_rm_dossier._correct_ocr_dni (S59)."""
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


def _parse_spanish_date(raw):
    raw = _strip_accents(raw).lower().strip()

    slash_match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if slash_match:
        day, month, year = (int(g) for g in slash_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    text_match = re.match(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", raw)
    if text_match:
        day, month_name, year = text_match.groups()
        month = _MESES.get(month_name)
        if not month:
            return None
        try:
            return date(int(year), month, int(day))
        except ValueError:
            return None

    return None


def _detect_rotation(img):
    """H30 (S60). Detecta con Tesseract OSD (Orientation and Script
    Detection) el angulo que hay que girar la pagina para que quede en
    orientacion normal de lectura. Origen real: DOC008.pdf escaneada
    boca abajo (180 grados), invisible para los RECORD_PATTERNS aunque
    el contenido fuera correcto -- "selva" real, no un caso raro.
    Nunca lanza: un scan de mala calidad puede hacer fallar el propio
    OSD, y en ese caso simplemente no se corrige nada (mismo
    comportamiento que antes de este fix)."""
    try:
        osd = pytesseract.image_to_osd(img)
        match = re.search(r"Rotate:\s*(\d+)", osd)
        return int(match.group(1)) if match else 0
    except Exception:
        return 0


def _ocr_all_pages(data):
    # H30 (S68) Punto 4 -- mismo fix real que local_ocr_classify.py:
    # DPI seguro calculado por pagina segun su tamano fisico, nunca
    # dpi=300 fijo (rompia con paginas grandes reales, caso Delgado
    # Hurtado -- 278M pixeles, por encima del limite real de Pillow,
    # 89.478.485 en produccion -- ver local_ocr_classify.py).
    SAFE_MAX_PIXELS = 80_000_000
    MIN_DPI = 100
    DPI_OBJETIVO = 300

    doc = fitz.open(stream=data, filetype="pdf")
    texts = []
    rotations = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        rect = page.rect
        dpi_pagina = DPI_OBJETIVO
        if rect.width > 0 and rect.height > 0:
            pixeles_estimados = (rect.width / 72 * DPI_OBJETIVO) * (rect.height / 72 * DPI_OBJETIVO)
            if pixeles_estimados > SAFE_MAX_PIXELS:
                dpi_pagina = int(72 * (SAFE_MAX_PIXELS / (rect.width * rect.height)) ** 0.5)
                dpi_pagina = max(dpi_pagina, MIN_DPI)
        pix = page.get_pixmap(dpi=dpi_pagina)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        angle = _detect_rotation(img)
        if angle:
            img = img.rotate(-angle, expand=True)
        rotations.append(angle)
        texts.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return texts, rotations


def _split_single_page(data, page_index, rotation=0):
    src = fitz.open(stream=data, filetype="pdf")
    new_doc = fitz.open()
    new_doc.insert_pdf(src, from_page=page_index, to_page=page_index)
    if rotation:
        # H30 (S60). El PDF final sube ya bien orientado -- no basta
        # con leerlo bien, tiene que quedar archivado legible.
        new_page = new_doc[0]
        new_page.set_rotation((new_page.rotation + rotation) % 360)
    out = new_doc.tobytes()
    new_doc.close()
    src.close()
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    if not (0 <= args.shard_index < max(args.shard_count, 1)):
        parser.error("--shard-index debe estar entre 0 y --shard-count - 1")

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, para el tunel SSH): "
    )
    mysql_password = getpass.getpass(
        "Contrasena de MySQL (panel PythonAnywhere, pestana 'Databases'): "
    )

    _log("Abriendo tunel SSH a %s ..." % SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOSTNAME,
        ssh_username=PYTHONANYWHERE_USERNAME,
        ssh_password=pa_password,
        remote_bind_address=(MYSQL_HOSTNAME, 3306),
        host_pkey_directories=[],
        allow_agent=False,
    )
    tunnel.start()
    _log("Tunel abierto, puerto local %d." % tunnel.local_bind_port)

    conn = pymysql.connect(
        host="127.0.0.1", port=tunnel.local_bind_port,
        user=MYSQL_USERNAME, passwd=mysql_password,
        db=MYSQL_DB_NAME, charset="utf8mb4",
    )

    _log("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        get_service_account_key_path()
    )
    bucket = gcs_client.bucket(BUCKET)

    with conn.cursor() as cur:
        shard_clause = ""
        params = (BUCKET, RM_ROOT, RM_ROOT + "/")
        if args.shard_count > 1:
            shard_clause = " AND id %% %s = %s"
            params = params + (args.shard_count, args.shard_index)
        cur.execute(
            "SELECT id, name, parent_path, blob_name "
            "FROM document_explorer_documentindexentry "
            "WHERE bucket = %s AND entry_kind = 'FILE' "
            "AND (parent_path = %s OR parent_path LIKE CONCAT(%s, '%%')) "
            "AND deleted_at IS NULL AND purged_at IS NULL "
            "AND LOWER(name) LIKE '%%.pdf'" + shard_clause,
            params,
        )
        candidatos = cur.fetchall()

    _log(
        "Shard %d de %d: %d PDFs candidatos."
        % (args.shard_index, args.shard_count, len(candidatos))
    )

    manifest_path = "rm_split_manifest_shard%d.jsonl" % args.shard_index
    manifest = open(manifest_path, "w", encoding="utf-8")

    for i, (entry_id, name, parent_path, blob_name) in enumerate(
        candidatos, start=1,
    ):
        if i % 20 == 0:
            conn.ping(reconnect=True)
        _log("[%d/%d] %s / %s" % (i, len(candidatos), parent_path, name))

        try:
            data = bucket.blob(blob_name).download_as_bytes()
            page_texts, page_rotations = _ocr_all_pages(data)
        except Exception as exc:
            _log("  ERROR descargando/OCR: %s" % exc)
            manifest.write(json.dumps({
                "dossier_entry_id": entry_id, "status": "ERROR",
                "error": str(exc),
            }) + "\n")
            manifest.flush()
            continue

        paginas = []
        for page_index, text in enumerate(page_texts):
            clean = _strip_accents(text).upper()
            pattern_name, match = _match_record(clean)
            if not match:
                paginas.append({
                    "page_index": page_index, "status": "SIN_PATRON",
                })
                continue

            dni = _correct_ocr_dni(match.group("dni"))
            fecha = _parse_spanish_date(match.group("fecha"))
            if fecha is None:
                paginas.append({
                    "page_index": page_index, "status": "FECHA_INVALIDA",
                })
                continue

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, given_name, first_surname, second_surname, "
                    "folder_path FROM document_explorer_personidentity "
                    "WHERE dni = %s", (dni,),
                )
                person_row = cur.fetchone()

            page_bytes = _split_single_page(
                data, page_index, page_rotations[page_index],
            )
            if person_row:
                person_id, given, first_s, second_s, folder_path = person_row
                filename = _build_filename_personal(
                    first_s, second_s, given, RM_TYPE_CODE, fecha,
                )
                target_folder = folder_path
            else:
                person_id = None
                filename = "%s_%s_%s.pdf" % (
                    _sanitize_token(match.group("nombre")), RM_TYPE_CODE,
                    fecha.strftime("%Y%m%d"),
                )
                target_folder = PENDING_REVIEW_FOLDER

            target_blob = "%s/%s" % (target_folder, filename)
            bucket.blob(target_blob).upload_from_string(
                page_bytes, content_type="application/pdf",
            )
            _log(
                "  pagina %d -> %s (%s)"
                % (
                    page_index + 1, target_blob,
                    ("PersonIdentity id=%s" % person_id) if person_id
                    else "PENDIENTE DE REVISION",
                )
            )
            paginas.append({
                "page_index": page_index, "status": "OK",
                "target_blob": target_blob,
                "target_folder": target_folder, "filename": filename,
                "person_id": person_id, "dni": dni,
                "nombre": match.group("nombre"),
            })

        todas_ok = all(p["status"] == "OK" for p in paginas)
        manifest.write(json.dumps({
            "dossier_entry_id": entry_id, "dossier_name": name,
            "dossier_parent_path": parent_path, "status": "PROCESADO",
            "todas_paginas_ok": todas_ok, "paginas": paginas,
        }) + "\n")
        manifest.flush()

    manifest.close()
    _log("Manifiesto escrito: %s" % manifest_path)
    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
