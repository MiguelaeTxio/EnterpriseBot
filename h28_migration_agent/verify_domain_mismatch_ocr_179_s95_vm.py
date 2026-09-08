# C:\EnterpriseBot\h28_migration_agent\verify_domain_mismatch_ocr_179_s95_vm.py
"""
H31 (S95). Verificacion de CONTENIDO REAL para 179 DocumentIndexEntry
con document_type sospechoso de estar mal asignado, detectados en el
Punto 4 (auditoria domain vs. uso real) de H31:

- 122 tipados BAJA_PERSONAL pero vinculados a fleet.MachineAsset
  (deberian ser tipos reales de maquinaria: CERT_MANTENIMIENTO,
  CERT_EXENCION_PERMISO, MANUAL_USO, BAJA_DEFINITIVA/TEMPORAL, etc.).
- 57 tipados RAE pero vinculados a document_explorer.PersonIdentity
  (deberian ser CARNET_GRUISTA, AUTORIZACION_USO_MAQUINARIA,
  SOLICITUD_ADMINISTRATIVA, CURSO, etc.).

Incidente real de la propia sesion S95, antes de escribir esto: un
primer intento de reclasificar estos 179 por heuristica de nombre de
archivo/carpeta se aplico sobre BD real (111 de 122 + 56 de 57), y
tuvo que revertirse por completo -- Miguel Angel señalo que es
exactamente el mismo riesgo ya confirmado en H30/S78 (identidad falsa
por nombre de carpeta: una carpeta de una persona que no existe con
documentos reales de otra persona dentro). Verificado con este mismo
script que ninguno de los 179 tenia ocr_text cacheado -- nunca
pasaron por ningun barrido de H30 (los de maquina quedaron fuera por
estar vinculados a MachineAsset y no PersonIdentity; los de persona
quedaron fuera porque RAE tiene domain=MACHINE declarado, así que
ninguna consulta de H30 filtrada por domain=PERSONAL los vio nunca,
pese a estar vinculados a trabajadores activos reales).

Este script SOLO extrae y cachea ocr_text -- NUNCA escribe
document_type. Decidir el tipo correcto a partir del texto real
extraido aqui es un paso posterior, manual, sobre el resultado de
este barrido (nunca automatico sobre coincidencia de nombre).

Mismo patron standalone que extract_personal_dates_bulk.py / cd
extract_epis_deliveries_vm.py: tunel SSH por clave ya registrada +
pymysql directo + GCS via service account, sin Django (la VM no lo
tiene). Reutiliza extract_text() de extract_personal_dates_bulk.py
(debe vivir en el mismo directorio de la VM).

Sharding: --shard-count N --shard-index I sobre la lista FIJA de 179
ids (nunca sobre una query abierta) -- 3 shards en la misma VM, tres
ventanas SSH, mismo criterio que el resto de barridos de H30/H28.

USO (ejemplo, shard 0 de 3):
    python3 verify_domain_mismatch_ocr_179_s95_vm.py --shard-count 3 --shard-index 0
"""
import argparse
import datetime
import getpass

import pymysql
import sshtunnel
from google.cloud import storage

from config import get_service_account_key_path
from extract_personal_dates_bulk import extract_text

# Patron obligatorio desde S81 (ver extract_epis_deliveries_vm.py,
# commit a6be28c): la sesion SSH desde Termux se desconecta por
# inactividad en barridos largos (S86), y sin log propio a fichero
# con flush() explicito, Python deja el stdout redirigido con buffer
# de bloque -- una desconexion a medias puede dejar el archivo vacio,
# sin ningun rastro de por donde iba el barrido. Corregido en la
# propia sesion S95 tras usar la version anterior (solo print() +
# redireccion de shell) para el shard 0 real.
_LOG_FH = None


def _log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    if _LOG_FH is not None:
        _LOG_FH.write(line + "\n")
        _LOG_FH.flush()

PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"

# Lista fija, extraida literalmente del volcado real de la sesion
# (EnterpriseBot_006_GET.txt) -- nunca reconstruida de memoria.
BAJA_PERSONAL_IDS = [
    12139, 12143, 12144, 12145, 12148, 12149, 12150, 12151, 12152,
    12153, 12154, 12155, 12175, 12176, 12189, 12202, 12203, 12231,
    12233, 12234, 12236, 12204, 12205, 12206, 12207, 12229, 12238,
    12274, 12283, 12284, 12285, 12286, 12287, 12288, 12280, 12281,
    12282, 12271, 12272, 12239, 12273, 12291, 12296, 12300, 12301,
    12302, 12299, 12307, 12308, 12310, 12311, 12312, 12338, 12347,
    12350, 12351, 12352, 12355, 12371, 12378, 12426, 12407, 12408,
    12409, 12417, 12397, 12400, 12433, 12442, 12462, 12463, 12481,
    12483, 12478, 12479, 12480, 12491, 12492, 12498, 12517, 12537,
    12538, 12539, 12589, 12597, 12530, 12531, 12532, 12533, 12534,
    12535, 12540, 12541, 12559, 12599, 12609, 12633, 12640, 12610,
    12627, 12628, 12642, 12656, 12678, 12681, 12643, 12652, 12657,
    12661, 12695, 12696, 12705, 12722, 12712, 12713, 12714, 12724,
    12732, 12737, 12739, 12740, 12759,
]
RAE_IDS = [
    24617, 24618, 27481, 27485, 27487, 27492, 27721, 27804, 27855,
    27900, 27965, 28021, 28045, 34091, 34092, 34274, 34170, 34184,
    34185, 34675, 34680, 34683, 34932, 35273, 35274, 35345, 35380,
    35556, 35557, 35626, 35627, 35628, 35629, 35805, 36290, 36291,
    36355, 36356, 36357, 36358, 36490, 36499, 36628, 36957, 36958,
    37090, 37110, 37289, 37193, 37194, 37195, 37196, 37652, 37653,
    37654, 37950, 40894,
]
ALL_IDS = BAJA_PERSONAL_IDS + RAE_IDS
assert len(BAJA_PERSONAL_IDS) == 122
assert len(RAE_IDS) == 57
assert len(ALL_IDS) == 179


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    if not (0 <= args.shard_index < max(args.shard_count, 1)):
        parser.error("--shard-index debe estar entre 0 y --shard-count - 1")

    global _LOG_FH
    log_path = "verify_domain_mismatch_shard%d.log" % args.shard_index
    _LOG_FH = open(log_path, "a", encoding="utf-8")

    if args.shard_count > 1:
        ids_this_shard = [
            entry_id for entry_id in ALL_IDS
            if entry_id % args.shard_count == args.shard_index
        ]
    else:
        ids_this_shard = ALL_IDS

    mysql_password = getpass.getpass(
        "Contrasena de MySQL (panel PythonAnywhere, pestana 'Databases'): "
    )
    _log("Abriendo tunel SSH a %s (autenticando por clave ya registrada) ..." % SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOSTNAME,
        ssh_username=PYTHONANYWHERE_USERNAME,
        remote_bind_address=(MYSQL_HOSTNAME, 3306),
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

    placeholders = ", ".join(["%s"] * len(ids_this_shard))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.name, e.parent_path, e.bucket, e.blob_name, t.code "
            "FROM document_explorer_documentindexentry e "
            "JOIN document_explorer_documenttypecatalog t "
            "  ON e.document_type_id = t.id "
            "WHERE e.id IN (%s) ORDER BY e.id" % placeholders,
            tuple(ids_this_shard),
        )
        rows = cur.fetchall()

    if args.shard_count > 1:
        _log("Reparto: shard %d de %d (entry_id %% %d == %d)"
             % (args.shard_index, args.shard_count,
                args.shard_count, args.shard_index))
    _log("Documentos a procesar en este shard: %d" % len(rows))

    ok = 0
    sin_extractor = 0
    error = 0
    total = len(rows)

    for i, (entry_id, name, parent_path, bucket_name, blob_name, code) in enumerate(rows, start=1):
        if i % 20 == 0:
            conn.ping(reconnect=True)
        _log("[%d/%d] id=%d (tipo actual=%s) %s/%s"
             % (i, total, entry_id, code, parent_path, name))

        try:
            bucket = gcs_client.bucket(bucket_name)
            data = bucket.blob(blob_name).download_as_bytes()
            text = extract_text(name, data)
        except Exception as exc:
            error += 1
            _log("  ERROR -- %s" % exc)
            continue

        if text is None:
            sin_extractor += 1
            _log("  SIN EXTRACTOR (extension no soportada)")
            continue

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE document_explorer_documentindexentry "
                "SET ocr_text=%s WHERE id=%s",
                (text, entry_id),
            )
        conn.commit()
        ok += 1
        preview = " ".join(text.split())[:200]
        _log("  OCR CACHEADO (%d caracteres). Preview: %s" % (len(text), preview))

        # Heartbeat de progreso (com-standards, seccion "Heartbeat
        # periodico obligatorio"): cada 20 elementos o el 5% del
        # total, lo que sea menor, ademas de la linea por documento
        # de arriba -- redundante a proposito para lotes grandes.
        heartbeat_every = min(20, max(1, total // 20))
        if i % heartbeat_every == 0 or i == total:
            pct = round(100 * i / total, 1) if total else 100
            _log("  Progreso: %d/%d (%s%%) -- ok=%d sin_extractor=%d "
                 "error=%d" % (i, total, pct, ok, sin_extractor, error))

    _log("=== RESUMEN shard %d/%d ===" % (args.shard_index, args.shard_count))
    _log("ocr_text cacheado correctamente: %d" % ok)
    _log("Sin extractor (extension no soportada): %d" % sin_extractor)
    _log("Error de descarga/OCR: %d" % error)

    tunnel.close()
    _LOG_FH.close()


if __name__ == "__main__":
    main()
