# h28_migration_agent/backfill_reconocimiento_medico_ocr_text.py
"""
H30 (sesion tras S85). Reproceso puntual, NO el barrido general.

Objetivo unico: los ~60 RECONOCIMIENTO_MEDICO que ya tienen
issue_date (puesto en sesiones anteriores a que se empezara a cachear
ocr_text) pero no tienen ocr_text guardado, y por tanto no se pueden
clasificar entre "revision anual" (expiry = issue + 1 año) y
"certificado especifico de renovacion de carnet, caduca a los tres
meses" (expiry = issue + 3 meses). Este script NUNCA toca issue_date
(ya es correcta) -- solo baja el documento, saca texto, lo cachea, y
calcula/guarda expiry_date segun el mismo criterio ya aplicado al
resto (ver EnterpriseBot_015/016_GET.txt de la sesion: regex
"caduca a los tres meses" sobre el texto real).

Cascada de lectura identica a extract_personal_dates_bulk.py: PSM
automatico primero (rapido); si el texto sale sospechosamente corto
(<200 caracteres, señal de fallo de OCR), reintento con PSM 6; si
sigue corto, EasyOCR como ultimo recurso.

USO:
    python3 backfill_reconocimiento_medico_ocr_text.py            (dry-run)
    python3 backfill_reconocimiento_medico_ocr_text.py --apply
    python3 backfill_reconocimiento_medico_ocr_text.py --apply --limit 10
"""
import argparse
import getpass
import re

import pymysql
import sshtunnel
from dateutil.relativedelta import relativedelta
from google.cloud import storage

from config import get_service_account_key_path
from extract_personal_dates_bulk import extract_text, easyocr_extract_text

TRES_MESES_RE = re.compile(r"caduca\s+a\s+los\s+tres\s+meses", re.IGNORECASE)

# Mismo patron de tunel SSH que extract_personal_dates_bulk.py (clave
# ya registrada en PythonAnywhere -- sshtunnel la descubre igual que
# ssh normal, ver ese script para el detalle completo).
SSH_HOST = "ssh.pythonanywhere.com"
SSH_USER = "MiguelAeTxio"
DB_HOST = "MiguelAeTxio.mysql.pythonanywhere-services.com"
DB_NAME = "MiguelAeTxio$enterprisebot"
DB_USER = "MiguelAeTxio"
BUCKET = "cgs_grupo_alvarez"


def _log(msg):
    print(msg, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db_password = getpass.getpass(
        "Contrasena de MySQL (panel PythonAnywhere, pestana 'Databases'): "
    )

    _log("Abriendo tunel SSH a %s ..." % SSH_HOST)
    tunnel = sshtunnel.SSHTunnelForwarder(
        (SSH_HOST, 22),
        ssh_username=SSH_USER,
        remote_bind_address=(DB_HOST, 3306),
    )
    tunnel.start()

    conn = pymysql.connect(
        host="127.0.0.1",
        port=tunnel.local_bind_port,
        user=DB_USER,
        password=db_password,
        database=DB_NAME,
        charset="utf8mb4",
    )

    _log("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        get_service_account_key_path()
    )
    bucket = gcs_client.bucket(BUCKET)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.bucket, e.parent_path, e.name, e.issue_date
            FROM document_explorer_documentindexentry e
            JOIN document_explorer_documenttypecatalog t
                ON t.id = e.document_type_id
            WHERE t.code = 'RECONOCIMIENTO_MEDICO'
              AND e.entry_kind = 'FILE'
              AND e.deleted_at IS NULL
              AND e.purged_at IS NULL
              AND e.issue_date IS NOT NULL
              AND (e.ocr_text IS NULL OR e.ocr_text = '')
            ORDER BY e.id
            """
        )
        candidatos = cur.fetchall()

    if args.limit:
        candidatos = candidatos[: args.limit]

    _log("Candidatos: %d" % len(candidatos))

    stats = {"tres_meses": 0, "un_anio": 0, "sin_texto_ni_ahora": 0, "error": 0}

    for entry_id, bucket_name, parent_path, name, issue_date in candidatos:
        blob_name = "%s/%s" % (parent_path, name)
        _log("[%d] %s" % (entry_id, name))
        try:
            data = bucket.blob(blob_name).download_as_bytes()
        except Exception as exc:
            _log("  ERROR descargando: %s" % exc)
            stats["error"] += 1
            continue

        text = extract_text(name, data)
        if not text or len(text.strip()) < 200:
            _log("  texto corto (%d caracteres), reintento PSM 6 ..."
                 % len(text or ""))
            text_retry = extract_text(name, data, psm=6)
            if text_retry and len(text_retry.strip()) > len(text or ""):
                text = text_retry
        if not text or len(text.strip()) < 200:
            _log("  sigue corto, probando EasyOCR (ultimo recurso) ...")
            text_easy = easyocr_extract_text(name, data)
            if text_easy and len(text_easy.strip()) > len(text or ""):
                text = text_easy

        if not text:
            _log("  SIN TEXTO tras los tres intentos -- se deja para revision manual")
            stats["sin_texto_ni_ahora"] += 1
            continue

        if TRES_MESES_RE.search(text):
            expiry_date = issue_date + relativedelta(months=3)
            stats["tres_meses"] += 1
            etiqueta = "TRES MESES"
        else:
            expiry_date = issue_date + relativedelta(years=1)
            stats["un_anio"] += 1
            etiqueta = "UN AÑO"

        _log("  %s -> expiry=%s" % (etiqueta, expiry_date.isoformat()))

        if args.apply:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE document_explorer_documentindexentry "
                    "SET ocr_text=%s, expiry_date=%s WHERE id=%s",
                    (text, expiry_date, entry_id),
                )
            conn.commit()

    _log("=== RESUMEN (%s) ===" % ("APLICADO" if args.apply else "DRY-RUN"))
    for k, v in stats.items():
        _log("    %s: %d" % (k, v))

    tunnel.stop()


if __name__ == "__main__":
    main()
