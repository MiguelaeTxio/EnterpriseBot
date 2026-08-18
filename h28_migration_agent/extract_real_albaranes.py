# C:\EnterpriseBot\h28_migration_agent\extract_real_albaranes.py
"""
H30 (S55). Extraccion puntual, via OCR, de los albaranes REALES
detectados en la carpeta de primer nivel "2026-07" (21 archivos .jpg,
fotos tomadas con camara al recibir material -- "albaran-camara" en
el nombre), nunca clasificados porque esa carpeta vive fuera del
alcance de DOC. MAQUINAS/DOC. PERSONAL que cubre el resto del
pipeline.

Solo 21 archivos -- se ejecuta directamente en el PC de Miguel Angel,
sin necesidad de crear ninguna VM. Reutiliza extract_text/
get_service_account_key_path de local_ocr_classify.py, mismo criterio
de extraccion que el resto del proyecto.

NUNCA escribe en la base de datos -- solo lee y descarga de GCS,
escribe un JSONL local con tipo=ALBARAN_ENTREGA fijo (ya sabemos el
tipo por el propio nombre de archivo real, "albaran-camara" -- no hace
falta clasificacion, es extraccion dirigida de un tipo ya identificado
con certeza).

USO:
    python extract_real_albaranes.py --output real_albaranes.jsonl
"""
import argparse
import getpass
import json
from datetime import datetime

import local_ocr_classify as base

import sshtunnel
from google.cloud import storage
import pymysql


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="real_albaranes.jsonl")
    args = parser.parse_args()

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, para el tunel SSH): "
    )
    mysql_password = getpass.getpass(
        "Contrasena de MySQL (distinta de la anterior -- panel "
        "PythonAnywhere, pestana 'Databases'): "
    )

    _log("Abriendo tunel SSH a %s ..." % base.SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        base.SSH_HOSTNAME,
        ssh_username=base.PYTHONANYWHERE_USERNAME,
        ssh_password=pa_password,
        remote_bind_address=(base.MYSQL_HOSTNAME, 3306),
        host_pkey_directories=[],
        allow_agent=False,
    )
    tunnel.start()
    _log("Tunel abierto, puerto local %d." % tunnel.local_bind_port)

    conn = pymysql.connect(
        host="127.0.0.1", port=tunnel.local_bind_port,
        user=base.MYSQL_USERNAME, passwd=mysql_password,
        db=base.MYSQL_DB_NAME, charset="utf8mb4",
    )

    _log("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        base.get_service_account_key_path()
    )
    bucket = gcs_client.bucket(base.BUCKET)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.name, e.parent_path, e.blob_name "
            "FROM document_explorer_documentindexentry e "
            "WHERE e.entry_kind = 'FILE' AND e.deleted_at IS NULL "
            "AND e.purged_at IS NULL "
            "AND e.parent_path LIKE '2026-07%%' "
            "AND LOWER(e.name) LIKE '%%albaran%%'",
        )
        rows = cur.fetchall()

    _log("Albaranes reales encontrados: %d" % len(rows))

    stats = {"ok": 0, "sin_texto": 0, "error": 0}
    with open(args.output, "w", encoding="utf-8") as out:
        for entry_id, name, parent_path, blob_name in rows:
            try:
                data = bucket.blob(blob_name).download_as_bytes()
                text = base.extract_text(name, data)
            except Exception as error:
                stats["error"] += 1
                _log("ERROR [%s] %s -- %s" % (parent_path, name, error))
                continue

            if not text:
                stats["sin_texto"] += 1
                _log("SIN TEXTO (OCR vacio) [%s] %s" % (parent_path, name))
                continue

            out.write(json.dumps({
                "tipo": "ALBARAN_ENTREGA",
                "parent_path": parent_path,
                "name": name,
                "texto": text[:4000],
            }, ensure_ascii=False) + "\n")
            out.flush()
            stats["ok"] += 1
            _log("OK [%s] %s -- %d caracteres" % (parent_path, name, len(text)))

    _log(
        "TERMINADO -- ok=%d sin_texto=%d error=%d -- guardado en %s"
        % (stats["ok"], stats["sin_texto"], stats["error"], args.output)
    )

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
