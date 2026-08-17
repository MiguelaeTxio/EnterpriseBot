# C:\EnterpriseBot\h28_migration_agent\report_ocr_gaps.py
"""
H30 (S51, reescrito S54). Informe de SOLO LECTURA para saber, con
datos reales y SIN gastar nada en ninguna VM, que porcentaje de los
candidatos reales resolveria hoy `local_ocr_classify.py` con los 37
tipos de `CONTENT_MARKERS` actuales -- antes de decidir si merece la
pena lanzar nada a gran escala.

Origen real de esta reescritura: tras ampliar CONTENT_MARKERS de 24 a
37 tipos (S54), Miguel Angel se nego explicitamente a lanzar otra VM
"para obtener el mismo resultado" sin verificarlo antes. Esta version
corre en CUALQUIER maquina normal (movil via Termux, PC) usando el
mismo tunel SSH que ya usa `local_ocr_classify.py` -- no crea ninguna
VM de Compute Engine, coste real: cero.

Reutiliza LITERALMENTE (import, no reimplementacion) la conexion,
SCOPE, CONTENT_MARKERS, `_in_scope`, `_is_photo`, `_match_content` de
`local_ocr_classify.py` -- para no divergir de la logica real que
correria de verdad en una VM.

Toma una MUESTRA ALEATORIA (por defecto 400, `--sample N` para
cambiarlo) en vez de los ~11.000 candidatos completos -- suficiente
para un porcentaje fiable, y se puede correr en el movil en pocos
minutos sin necesitar ninguna maquina en la nube.

NUNCA escribe nada -- ninguna sentencia UPDATE, sin flag --apply
siquiera.

USO: igual que local_ocr_classify.py, mismas contraseñas.

    python report_ocr_gaps.py
    python report_ocr_gaps.py --sample 800
"""
import argparse
import getpass

import local_ocr_classify as base

import sshtunnel
from google.cloud import storage
import pymysql


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=400)
    args = parser.parse_args()

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, para el tunel SSH): "
    )
    mysql_password = getpass.getpass(
        "Contrasena de MySQL (distinta de la anterior -- panel "
        "PythonAnywhere, pestana 'Databases'): "
    )

    print("Abriendo tunel SSH a %s ..." % base.SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        base.SSH_HOSTNAME,
        ssh_username=base.PYTHONANYWHERE_USERNAME,
        ssh_password=pa_password,
        remote_bind_address=(base.MYSQL_HOSTNAME, 3306),
        host_pkey_directories=[],
        allow_agent=False,
    )
    tunnel.start()
    print("Tunel abierto, puerto local %d." % tunnel.local_bind_port)

    conn = pymysql.connect(
        host="127.0.0.1", port=tunnel.local_bind_port,
        user=base.MYSQL_USERNAME, passwd=mysql_password,
        db=base.MYSQL_DB_NAME, charset="utf8mb4",
    )

    print("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        base.get_service_account_key_path()
    )
    bucket = gcs_client.bucket(base.BUCKET)

    with conn.cursor() as cur:
        # Muestra aleatoria real de MySQL (RAND(), no la primera N por
        # id) para que sea representativa de las dos carpetas, no solo
        # de lo que se subio primero.
        cur.execute(
            "SELECT id, name, parent_path FROM document_explorer_documentindexentry "
            "WHERE entry_kind = 'FILE' AND document_type_id IS NULL "
            "AND deleted_at IS NULL AND purged_at IS NULL "
            "AND bucket = %s AND (parent_path LIKE %s OR parent_path LIKE %s) "
            "AND parent_path NOT LIKE '%%EPIS%%' "
            "ORDER BY RAND() LIMIT %s",
            (
                base.BUCKET, base.MACHINE_ROOT + "/%",
                base.PERSONAL_ROOT + "/%", args.sample,
            ),
        )
        raw_rows = cur.fetchall()

    candidatos = []
    for entry_id, name, parent_path in raw_rows:
        if not base._in_scope(parent_path):
            continue
        if base._is_photo(name):
            continue
        candidatos.append((entry_id, name, parent_path))

    print("Muestra aleatoria real: %d candidatos (de %d pedidos)\n"
          % (len(candidatos), args.sample))

    # raiz ("DOC. MAQUINAS"/"DOC. PERSONAL") -> {categoria: cuenta}
    por_raiz = {}
    CATEGORIAS = [
        "tipo_resuelto", "sin_tipo", "ambiguo",
        "extension_no_soportada", "error",
    ]

    def raiz_de(parent_path):
        return (
            base.MACHINE_ROOT if parent_path.startswith(base.MACHINE_ROOT)
            else base.PERSONAL_ROOT
        )

    for i, (entry_id, name, parent_path) in enumerate(candidatos, start=1):
        if i % 25 == 0:
            print("  ... %d/%d" % (i, len(candidatos)))
            conn.ping(reconnect=True)

        raiz = raiz_de(parent_path)
        por_raiz.setdefault(raiz, {c: 0 for c in CATEGORIAS})

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT blob_name FROM document_explorer_documentindexentry "
                    "WHERE id = %s", (entry_id,),
                )
                blob_name = cur.fetchone()[0]
            data = bucket.blob(blob_name).download_as_bytes()
            text = base.extract_text(name, data)
        except Exception:
            por_raiz[raiz]["error"] += 1
            continue

        if text is None:
            por_raiz[raiz]["extension_no_soportada"] += 1
            continue

        text_upper = base._strip_accents(text).upper()
        code, ambiguous = base._match_content(text_upper)

        if ambiguous:
            por_raiz[raiz]["ambiguo"] += 1
        elif code:
            por_raiz[raiz]["tipo_resuelto"] += 1
        else:
            por_raiz[raiz]["sin_tipo"] += 1

    print("\n=== INFORME REAL DE COBERTURA (%d candidatos, muestra "
          "aleatoria) ===\n" % len(candidatos))
    total_general = {c: 0 for c in CATEGORIAS}
    for raiz in sorted(por_raiz):
        conteos = por_raiz[raiz]
        total = sum(conteos.values())
        pct = (100.0 * conteos["tipo_resuelto"] / total) if total else 0.0
        print("%s -- %d candidatos" % (raiz, total))
        for c in CATEGORIAS:
            print("    %-24s %6d" % (c, conteos[c]))
        print("    %-24s %5.1f%%" % ("% CON TIPO REAL", pct))
        print()
        for c in CATEGORIAS:
            total_general[c] += conteos[c]

    total_gen = sum(total_general.values())
    pct_gen = (
        100.0 * total_general["tipo_resuelto"] / total_gen
        if total_gen else 0.0
    )
    print("=== TOTAL GENERAL (%d candidatos) ===" % total_gen)
    for c in CATEGORIAS:
        print("    %-24s %6d" % (c, total_general[c]))
    print("    %-24s %5.1f%%" % ("% CON TIPO REAL", pct_gen))
    print(
        "\nEste %.1f%% es una estimacion real, sobre muestra aleatoria, "
        "de lo que resolveria una pasada completa con los 37 tipos "
        "actuales de CONTENT_MARKERS -- sin haber gastado nada en "
        "ninguna VM." % pct_gen
    )

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()

