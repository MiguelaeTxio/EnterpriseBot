# C:\EnterpriseBot\h28_migration_agent\inspect_sin_patron_pages.py
"""
H30 (S60). Herramienta puntual de calibracion, hermana de
`split_rm_dossier_vm.py`: nunca escribe nada (ni en MySQL ni en GCS),
solo lee.

Reabre los manifiestos JSONL ya escritos en S59
(`rm_split_manifest_shard{0,1,2}.jsonl`, en el directorio actual),
localiza paginas marcadas "SIN_PATRON", vuelve a descargar el dosier
original de GCS (todavia no se ha movido -- SIN_PATRON nunca se sube
a ningun sitio, ver split_rm_dossier_vm.py linea ~302), extrae solo
esa pagina concreta y la vuelve a pasar por OCR para volcar el texto
en crudo por pantalla.

Objetivo: leer el texto real de 2-3 paginas SIN_PATRON para calibrar
un patron regex nuevo (tercera mutua o variante de
Fraternidad-Muprespa) antes de relanzar los 3 shards -- mismo
criterio de calibracion que S59 (ver un ejemplo real, extraer regex,
verificar contra 3+ casos antes de desplegar).

USO (una sola ventana SSH, no hace falta paralelo -- es lectura
puntual, no un barrido):

    python3 inspect_sin_patron_pages.py --limit 3

Pide credenciales de forma interactiva, igual que
`split_rm_dossier_vm.py` -- nunca en texto plano.
"""
import argparse
import getpass
import glob
import io
import json

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
# CONFIGURACION -- identica a split_rm_dossier_vm.py
# ---------------------------------------------------------------
PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"

BUCKET = "cgs_grupo_alvarez"


def _log(msg):
    print(msg, flush=True)


def _find_sin_patron_pages(limit):
    """Recorre todos los rm_split_manifest_shard*.jsonl del directorio
    actual y devuelve hasta `limit` tuplas
    (dossier_entry_id, dossier_name, dossier_parent_path, page_index)
    de paginas marcadas SIN_PATRON, en el orden en que aparecen."""
    found = []
    for path in sorted(glob.glob("rm_split_manifest_shard*.jsonl")):
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("status") != "PROCESADO":
                    continue
                for pagina in row.get("paginas", []):
                    if pagina.get("status") != "SIN_PATRON":
                        continue
                    found.append((
                        row["dossier_entry_id"], row["dossier_name"],
                        row["dossier_parent_path"], pagina["page_index"],
                    ))
                    if len(found) >= limit:
                        return found
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    targets = _find_sin_patron_pages(args.limit)
    if not targets:
        _log(
            "No se ha encontrado ninguna pagina SIN_PATRON en los "
            "rm_split_manifest_shard*.jsonl del directorio actual."
        )
        return
    _log("%d pagina(s) SIN_PATRON localizada(s) en el/los manifiesto(s):"
         % len(targets))
    for entry_id, name, parent_path, page_index in targets:
        _log("  - id=%s  %s/%s  pagina %d"
             % (entry_id, parent_path, name, page_index + 1))

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

    for entry_id, name, parent_path, page_index in targets:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT blob_name FROM document_explorer_documentindexentry "
                "WHERE id = %s", (entry_id,),
            )
            row = cur.fetchone()
        if not row:
            _log(
                "\n=== id=%s %s/%s pagina %d: sin fila viva en "
                "document_explorer_documentindexentry (borrado/movido "
                "desde S59) -- saltando ==="
                % (entry_id, parent_path, name, page_index + 1)
            )
            continue
        blob_name = row[0]

        try:
            data = bucket.blob(blob_name).download_as_bytes()
            doc = fitz.open(stream=data, filetype="pdf")
            page = doc.load_page(page_index)
            # H30 (S68) Punto 4: DPI seguro por pagina, mismo fix real
            # que local_ocr_classify.py/split_rm_dossier*.py (caso
            # Delgado Hurtado, 278M pixeles por encima del limite real
            # de Pillow, 178.956.970).
            rect = page.rect
            dpi_pagina = 300
            if rect.width > 0 and rect.height > 0:
                pixeles_estimados = (rect.width / 72 * 300) * (rect.height / 72 * 300)
                if pixeles_estimados > 150_000_000:
                    dpi_pagina = max(int(72 * (150_000_000 / (rect.width * rect.height)) ** 0.5), 100)
            pix = page.get_pixmap(dpi=dpi_pagina)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang="spa")
            doc.close()
        except Exception as exc:
            _log(
                "\n=== id=%s %s/%s pagina %d: ERROR %s ==="
                % (entry_id, parent_path, name, page_index + 1, exc)
            )
            continue

        _log(
            "\n=== id=%s %s/%s pagina %d ===\n%s"
            % (entry_id, parent_path, name, page_index + 1, text)
        )

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
