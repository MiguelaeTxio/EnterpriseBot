# C:\EnterpriseBot\h28_migration_agent\report_ocr_gaps.py
"""
H30 (S51). Informe de SOLO LECTURA sobre dónde se concentran los
"sin_tipo" (y el resto de categorías que `local_ocr_classify.py` no
guarda) tras el barrido real de S51 -- 2.399 candidatos procesados,
382 guardados (15,9%), muy por debajo de la estimación de Miguel
Ángel (~30%). Origen real de la pregunta: Miguel Ángel, verbatim,
"Hay que ver dónde se encuentran esos 1794".

Reutiliza LITERALMENTE (import, no reimplementación) la conexión,
SCOPE, CONTENT_MARKERS, `_in_scope`, `_is_photo`, `_match_content` y
`_resolve_machine_code` de `local_ocr_classify.py` -- para no divergir
de la lógica real ya corrida. La consulta de candidatos es la MISMA
(`document_type_id IS NULL`), así que automáticamente excluye los 382
ya guardados y solo mira lo que de verdad sigue pendiente.

NUNCA escribe nada -- ninguna sentencia UPDATE, sin flag --apply
siquiera. Agrupa por familia de máquina (primer segmento bajo
`DOC. MAQUINAS/`, tal cual aparece en `SCOPE`) y por categoría
(sin_tipo / ambiguo / dominio_sin_resolver / extension_no_soportada /
error), para ver si el problema real es cobertura de
`CONTENT_MARKERS` (solo 9 tipos reconocidos por contenido, frente a
57+ tipos reales del catálogo) o algo concentrado en familias
concretas.

USO: igual que local_ocr_classify.py, mismas contraseñas, sin --apply
porque no hace falta -- no escribe nunca.

    python report_ocr_gaps.py
"""
import getpass

import local_ocr_classify as base

import sshtunnel
from google.cloud import storage
import pymysql


def main():
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
        cur.execute("SELECT code, id FROM fleet_machineasset")
        machine_codes = {
            code.upper().replace("-", ""): mid
            for code, mid in cur.fetchall()
        }
        cur.execute(
            "SELECT id, name, parent_path FROM document_explorer_documentindexentry "
            "WHERE entry_kind = 'FILE' AND document_type_id IS NULL "
            "AND deleted_at IS NULL AND purged_at IS NULL "
            "AND bucket = %s AND parent_path LIKE %s",
            (base.BUCKET, base.MACHINE_ROOT + "/%"),
        )
        raw_rows = cur.fetchall()

    candidatos = []
    for entry_id, name, parent_path in raw_rows:
        if not base._in_scope(parent_path):
            continue
        if base._is_photo(name):
            continue
        candidatos.append((entry_id, name, parent_path))

    print("Candidatos pendientes reales (mismo criterio que "
          "local_ocr_classify.py): %d\n" % len(candidatos))

    # familia -> {categoria: cuenta}
    por_familia = {}
    CATEGORIAS = [
        "sin_tipo", "ambiguo", "dominio_sin_resolver",
        "extension_no_soportada", "error",
    ]

    def familia_de(parent_path):
        # Primer segmento bajo DOC. MAQUINAS/, tal cual lo define
        # SCOPE (p.ej. "GRUAS MOVILES (A)", "CAMIONES BRAZO (B)").
        resto = parent_path[len(base.MACHINE_ROOT) + 1:]
        return resto.split("/", 1)[0] if resto else "(raiz)"

    for i, (entry_id, name, parent_path) in enumerate(candidatos, start=1):
        if i % 50 == 0:
            print("  ... %d/%d" % (i, len(candidatos)))
            conn.ping(reconnect=True)

        familia = familia_de(parent_path)
        por_familia.setdefault(
            familia, {c: 0 for c in CATEGORIAS},
        )

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
            por_familia[familia]["error"] += 1
            continue

        if text is None:
            por_familia[familia]["extension_no_soportada"] += 1
            continue

        text_upper = base._strip_accents(text).upper()
        code, ambiguous = base._match_content(text_upper)

        if ambiguous:
            por_familia[familia]["ambiguo"] += 1
            continue
        if not code:
            por_familia[familia]["sin_tipo"] += 1
            continue

        machine_id = base._resolve_machine_code(parent_path, machine_codes)
        if not machine_id and (
            "/RAE" in parent_path or "/CE PLATAFORMAS" in parent_path
        ):
            machine_id = base._resolve_machine_by_filename(
                name, machine_codes,
            )
        if not machine_id:
            por_familia[familia]["dominio_sin_resolver"] += 1
            continue
        # Si llega aqui, en una pasada CON --apply se habria guardado
        # -- no deberia pasar mucho, ya que la consulta ya excluye lo
        # guardado en S51, pero puede pasar si Miguel Angel corre esto
        # despues de anadir mas CONTENT_MARKERS sin re-aplicar todavia.

    print("\n=== INFORME POR FAMILIA (%d candidatos pendientes) ===\n"
          % len(candidatos))
    ancho_familia = max((len(f) for f in por_familia), default=10)
    cabecera = "%-*s  %8s  %8s  %8s  %8s  %8s  %8s" % (
        ancho_familia, "Familia", "TOTAL", "sin_tipo", "ambiguo",
        "dom_sin_res", "ext_no_sop", "error",
    )
    print(cabecera)
    print("-" * len(cabecera))
    for familia in sorted(
        por_familia,
        key=lambda f: sum(por_familia[f].values()), reverse=True,
    ):
        conteos = por_familia[familia]
        total = sum(conteos.values())
        print("%-*s  %8d  %8d  %8d  %8d  %8d  %8d" % (
            ancho_familia, familia, total, conteos["sin_tipo"],
            conteos["ambiguo"], conteos["dominio_sin_resolver"],
            conteos["extension_no_soportada"], conteos["error"],
        ))

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
