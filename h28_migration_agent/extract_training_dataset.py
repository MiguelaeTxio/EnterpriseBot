# C:\EnterpriseBot\h28_migration_agent\extract_training_dataset.py
"""
H30 (S54). Extrae el CONJUNTO DE ENTRENAMIENTO real para un modelo de
clasificacion de documentos: hasta N ejemplos (por defecto 150) por
cada tipo documental YA clasificado (`document_type_id` no nulo),
repartidos entre `DOC. MAQUINAS` y `DOC. PERSONAL`, con su texto real
extraido por OCR/PDF, su ruta de carpeta y su nombre de archivo.

Origen real de esta pieza: tras el fallo de S54 intentando sacar
`CONTENT_MARKERS` (frases fijas) de solo 2-3 muestras por tipo,
Miguel Angel propuso ir por el camino real -- un modelo entrenado
sobre los datos que YA tenemos clasificados (miles de documentos,
verdad conocida), no sobre un puñado de ejemplos leidos a mano. Este
script es el primer paso: construir ese conjunto de entrenamiento de
verdad, en bruto, para luego (en un paso aparte, `train_document_
classifier.py`) entrenar y VALIDAR el modelo contra un conjunto de
prueba real antes de aplicarlo a nada desconocido.

Reutiliza LITERALMENTE (import) la conexion, `extract_text`,
`_strip_accents`, `_is_photo` de `local_ocr_classify.py` -- mismo
criterio de extraccion de texto que el resto del proyecto.

NUNCA escribe nada en la base de datos -- solo lee y descarga de GCS,
y escribe un archivo JSONL local (una linea por documento: tipo,
ruta, nombre, texto). Igual que `sample0/1/2_output.txt` de S51/S53,
este archivo hay que copiarlo fuera de la VM (gcloud compute scp)
ANTES de borrarla -- nunca se pierde el trabajo real de OCR.

Reparto en paralelo con --shard-count/--shard-index, mismo patron que
local_ocr_classify.py, para correr en varias VMs a la vez.

USO:
    python extract_training_dataset.py --shard-count 9 --shard-index 0
    python extract_training_dataset.py --max-per-type 150 --output dataset0.jsonl
"""
import argparse
import getpass
import json
import random
import time
from datetime import datetime

import local_ocr_classify as base

import sshtunnel
from google.cloud import storage
import pymysql


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-type", type=int, default=150)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--output", default="training_dataset.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not (0 <= args.shard_index < max(args.shard_count, 1)):
        raise SystemExit("--shard-index debe estar entre 0 y --shard-count - 1")

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
            "SELECT e.id, e.name, e.parent_path, e.blob_name, t.code "
            "FROM document_explorer_documentindexentry e "
            "JOIN document_explorer_documenttypecatalog t "
            "  ON t.id = e.document_type_id "
            "WHERE e.entry_kind = 'FILE' AND e.document_type_id IS NOT NULL "
            "AND e.deleted_at IS NULL AND e.purged_at IS NULL "
            "AND (e.parent_path LIKE %s OR e.parent_path LIKE %s)",
            (base.MACHINE_ROOT + "/%", base.PERSONAL_ROOT + "/%"),
        )
        raw_rows = cur.fetchall()

    _log("Documentos ya clasificados en total: %d" % len(raw_rows))

    # Agrupar por tipo, barajar cada grupo (semilla fija para que los
    # 9 shards vean SIEMPRE el mismo recorte de 150, no uno distinto
    # cada vez que se relanza) y recortar a --max-per-type.
    por_tipo = {}
    for entry_id, name, parent_path, blob_name, code in raw_rows:
        if base._is_photo(name):
            continue
        por_tipo.setdefault(code, []).append(
            (entry_id, name, parent_path, blob_name),
        )

    rng = random.Random(args.seed)
    candidatos = []
    for code, filas in por_tipo.items():
        rng.shuffle(filas)
        for entry_id, name, parent_path, blob_name in filas[:args.max_per_type]:
            candidatos.append((entry_id, name, parent_path, blob_name, code))

    # Reparto en shards, mismo criterio que local_ocr_classify.py.
    if args.shard_count > 1:
        candidatos = [
            c for c in candidatos if c[0] % args.shard_count == args.shard_index
        ]

    _log(
        "Candidatos de entrenamiento en este shard: %d (de %d tipos, "
        "tope %d por tipo)" % (len(candidatos), len(por_tipo), args.max_per_type)
    )

    stats = {"ok": 0, "sin_texto": 0, "error": 0}
    start_time = time.monotonic()

    with open(args.output, "w", encoding="utf-8") as out:
        for i, (entry_id, name, parent_path, blob_name, code) in enumerate(
            candidatos, start=1,
        ):
            if i % 20 == 0:
                conn.ping(reconnect=True)

            if i % 25 == 0:
                elapsed = time.monotonic() - start_time
                ritmo = i / elapsed if elapsed > 0 else 0
                restantes = len(candidatos) - i
                eta_min = (restantes / ritmo / 60) if ritmo > 0 else 0
                _log(
                    "--- LATIDO: %d/%d (%.1f%%) | %.1f min transcurridos | "
                    "ritmo %.1f docs/min | ETA ~%.0f min | ok=%d sin_texto=%d "
                    "error=%d ---"
                    % (
                        i, len(candidatos), 100.0 * i / len(candidatos),
                        elapsed / 60, ritmo * 60, eta_min,
                        stats["ok"], stats["sin_texto"], stats["error"],
                    )
                )

            try:
                data = bucket.blob(blob_name).download_as_bytes()
                text = base.extract_text(name, data)
            except Exception as error:
                stats["error"] += 1
                _log("ERROR [%s] %s -- %s" % (parent_path, name, error))
                continue

            if not text:
                stats["sin_texto"] += 1
                continue

            out.write(json.dumps({
                "tipo": code,
                "parent_path": parent_path,
                "name": name,
                "texto": text[:4000],
            }, ensure_ascii=False) + "\n")
            out.flush()
            stats["ok"] += 1

    total_min = (time.monotonic() - start_time) / 60
    _log(
        "TERMINADO -- %d candidatos procesados en %.1f minutos. "
        "ok=%d sin_texto=%d error=%d -- guardado en %s"
        % (
            len(candidatos), total_min, stats["ok"], stats["sin_texto"],
            stats["error"], args.output,
        )
    )

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
