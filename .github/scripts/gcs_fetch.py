# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/gcs_fetch.py
"""
Script auxiliar de solo lectura para file_fetch.yml (H31, S112).

Se ejecuta en el propio servidor de PythonAnywhere (vía SSH desde el
workflow, con el venv del proyecto activo y las variables del .env
cargadas por `python -m dotenv run`), usando la Service Account de GCS
YA configurada del proyecto (spare_parts.gcs_service.get_storage_client,
GCP_CREDENTIALS_PATH/GOOGLE_CLOUD_PROJECT) -- nunca una credencial
nueva. Descarga un único blob a la ruta indicada (SWAP/ del servidor,
temporal, borrado por el propio workflow tras subirlo).

H30 (S119), incidente real: el modelo tecleó a mano una ruta con un
espacio de menos ("9184FNK P16  FT-ITV.pdf" lleva dos) y el blob no
existía; el error se perdía y el Action salía en verde. Desde S119:
- `<bucket>` = "id" y `<blob_name>` = pk de DocumentIndexEntry: la ruta
  exacta se lee de la BD, nunca se teclea.
- Si la descarga falla, se escribe el error en `dest_path` (texto) para
  que llegue a Drive igualmente y se vea.

Uso: python3 gcs_fetch.py <bucket|id> <blob_name|pk> <dest_path>
"""
import sys
import traceback

bucket_name, blob_name, dest_path = sys.argv[1:4]
try:
    if bucket_name == "id":
        import os

        import django

        os.environ.setdefault(
            "DJANGO_SETTINGS_MODULE", "enterprise_core.settings",
        )
        django.setup()
        from document_explorer.models import DocumentIndexEntry

        entry = DocumentIndexEntry.objects.get(pk=int(blob_name))
        bucket_name, blob_name = entry.bucket, entry.blob_name

    from spare_parts.gcs_service import get_storage_client

    client = get_storage_client()
    client.bucket(bucket_name).blob(blob_name).download_to_filename(
        dest_path,
    )
except Exception:
    with open(dest_path, "w", encoding="utf-8") as out:
        out.write("ERROR gcs_fetch (%s / %s):\n" % (bucket_name, blob_name))
        out.write(traceback.format_exc())
