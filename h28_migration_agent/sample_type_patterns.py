# C:\EnterpriseBot\h28_migration_agent\sample_type_patterns.py
"""
H30 (S51). Muestreo de SOLO LECTURA de documentos YA clasificados
correctamente (`document_type_id` ya asignado, dato real, no
conjetura) -- hasta 3 ejemplos por cada uno de los 77 tipos activos
del catálogo, para construir `CONTENT_MARKERS` a partir de contenido
real visto de verdad, en vez de adivinar frases de memoria.

Origen real: tras confirmar que `CONTENT_MARKERS` solo cubre 9 de 77
tipos (barrido de maquinaria S51: 74,8% "sin_tipo"), Miguel Ángel,
verbatim: "Que te descargues una copia de cada uno de esos 77 tipos
[...] tres copias diferentes de diferentes documentos, para tener una
muestra de tres tipos diferentes de documentos del mismo tipo de
documento y poder realizar un patrón para detectar el tipo de
documento [...] no olvides que tenemos que extraer datos en la misma
pasada [...] sacar las fechas de caducidad si las tienen."

NUNCA escribe nada -- solo SELECT, solo lee de GCS. Reutiliza
LITERALMENTE (import) `extract_text`/`classify_dates_in_text` de
`local_ocr_classify.py`, misma lógica ya validada, sin reimplementar.

Por lotes, tal como pidió Miguel Ángel ("si va a ser muy grande,
primero 35, luego otros 35"):

    python sample_type_patterns.py --start 0 --count 35
    python sample_type_patterns.py --start 35 --count 35
    python sample_type_patterns.py --start 70 --count 35

Sin argumentos, hace los 77 de una vez. `--samples` cambia cuántos
ejemplos por tipo (por defecto 3). El texto de cada muestra se corta a
`--max-chars` caracteres (por defecto 4000) para no disparar el
volumen de salida -- las fechas y frases identificativas casi siempre
están en las primeras líneas/párrafos reales, nunca al final de un
documento de varias páginas de contenido irrelevante.
"""
import argparse
import getpass

import local_ocr_classify as base

import sshtunnel
from google.cloud import storage
import pymysql


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--max-chars", type=int, default=4000)
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
        cur.execute(
            "SELECT id, code, label, tracks_expiry, family "
            "FROM document_explorer_documenttypecatalog "
            "WHERE is_active = 1 ORDER BY family, code"
        )
        tipos = cur.fetchall()

    if args.count:
        tipos = tipos[args.start:args.start + args.count]
    else:
        tipos = tipos[args.start:]

    print("Tipos en este lote: %d (de %d..%d)\n"
          % (len(tipos), args.start, args.start + len(tipos) - 1))

    for type_id, code, label, tracks_expiry, family in tipos:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, parent_path, blob_name "
                "FROM document_explorer_documentindexentry "
                "WHERE document_type_id = %s AND entry_kind = 'FILE' "
                "AND deleted_at IS NULL AND purged_at IS NULL "
                "ORDER BY id DESC LIMIT %s",
                (type_id, args.samples),
            )
            muestras = cur.fetchall()

        print("=" * 78)
        print("TIPO: %s -- %s  (familia=%s, tracks_expiry=%s)"
              % (code, label, family, tracks_expiry))
        print("Muestras encontradas ya clasificadas: %d de %d pedidas"
              % (len(muestras), args.samples))
        print("=" * 78)

        if not muestras:
            print("  (sin ningun ejemplo real todavia en el catalogo)\n")
            continue

        for entry_id, name, parent_path, blob_name in muestras:
            print("\n--- Muestra: %s ---" % name)
            print("    Ruta: %s" % parent_path)
            try:
                data = bucket.blob(blob_name).download_as_bytes()
                text = base.extract_text(name, data)
            except Exception as exc:
                print("    ERROR descargando/leyendo: %s" % exc)
                continue
            if text is None:
                print("    (extension no soportada por extract_text)")
                continue

            expiry_date, issue_date, other_dates = \
                base.classify_dates_in_text(text)
            print("    Fecha caducidad detectada (ya con la logica "
                  "actual): %s" % expiry_date)
            print("    Fecha expedicion detectada: %s" % issue_date)
            if other_dates:
                print("    Otras fechas sueltas en el texto: %s"
                      % other_dates[:5])

            recortado = text[:args.max_chars]
            print("    Texto (%d caracteres, recortado a %d):"
                  % (len(text), len(recortado)))
            print("    " + "-" * 70)
            for linea in recortado.splitlines():
                print("    | " + linea)
            print("    " + "-" * 70)
        print()

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
