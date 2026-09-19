# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/gcs_fetch.py
"""
Script auxiliar de solo lectura para file_fetch.yml (H31, S112).

Se ejecuta en el propio servidor de PythonAnywhere (vía SSH desde el
workflow, con el venv del proyecto activo y las variables del .env
cargadas por `python -m dotenv run`), usando la Service Account de GCS
YA configurada del proyecto (spare_parts.gcs_service.get_storage_client,
GCP_CREDENTIALS_PATH/GOOGLE_CLOUD_PROJECT) -- nunca una credencial
nueva. Descarga un único blob a la ruta indicada (SWAP/ del servidor,
temporal, borrado por el propio workflow tras codificarlo).

Uso: python3 gcs_fetch.py <bucket> <blob_name> <dest_path>
"""
import sys

from spare_parts.gcs_service import get_storage_client

bucket_name, blob_name, dest_path = sys.argv[1:4]
client = get_storage_client()
client.bucket(bucket_name).blob(blob_name).download_to_filename(dest_path)
