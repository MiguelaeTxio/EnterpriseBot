# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/gcs_text_extract.py
"""
Script auxiliar de SOLO LECTURA para file_fetch.yml, modo gcs_text
(H30, S117).

Origen real: para cerrar la Fase 1 de MÁQUINAS el modelo necesita VER
qué son varios documentos sin tipo cuyo nombre no lo aclara, y Miguel
Ángel pidió que los mire él mismo ("es una cosa que tú puedes ver").
Traer el PDF entero a Drive no sirve: el conector de Drive del modelo
mete el archivo completo en su contexto y un escaneo de cientos de KB
no cabe. Este script baja cada blob en el propio servidor y extrae SOLO
su texto (dos primeras páginas) con el punto ÚNICO de extracción del
proyecto, document_explorer.cloud_vision_service.extract_text() --
texto incrustado de PDF primero, Cloud Vision después, nunca Tesseract
local (decisión S102). Escribe un único .txt con una cabecera por
archivo, que el workflow sube a Drive.

Nunca escribe en BD, nunca modifica GCS.

Uso: python3 gcs_text_extract.py <dest_txt> <max_chars> <targets_file>
(targets_file: un 'bucket/blob' por línea)
"""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from document_explorer.cloud_vision_service import extract_text  # noqa: E402
from spare_parts.gcs_service import get_storage_client  # noqa: E402

dest_path, max_chars = sys.argv[1], int(sys.argv[2])
with open(sys.argv[3], encoding="utf-8") as targets_file:
    targets = [line.strip() for line in targets_file if line.strip()]
client = get_storage_client()

with open(dest_path, "w", encoding="utf-8") as out:
    for index, target in enumerate(targets, start=1):
        bucket_name, blob_name = target.split("/", 1)
        out.write("=" * 78 + "\n")
        out.write("[%d/%d] %s\n" % (index, len(targets), blob_name))
        out.write("=" * 78 + "\n")
        try:
            data = client.bucket(bucket_name).blob(blob_name).download_as_bytes()
            text = extract_text(os.path.basename(blob_name), data) or ""
            text = " ".join(text.split())
            out.write((text[:max_chars] if text else "(sin texto legible)") + "\n\n")
        except Exception as exc:  # un archivo que falla no para el resto
            out.write("(ERROR: %s)\n\n" % exc)
        out.flush()
