# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/db_backup_fetch.py
"""
Script auxiliar de db_backup_restore_test.yml (H24, S146).

Se ejecuta en el servidor (SSH desde el workflow, venv activo y .env
cargado con `python -m dotenv run`). Dos modos:

- `meta [archivo]`: imprime en JSON los datos de la copia (nombre,
  SHA-256, filas de control); sin archivo, la última copia lista o ya
  en OneDrive.
- `stream <archivo>`: escribe el contenido de la copia en stdout,
  leído del cubo por trozos. Nada pasa por el disco del servidor.

Uso: python3 db_backup_fetch.py meta|stream [archivo]
"""
import json
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from document_explorer.db_backup_service import (  # noqa: E402
    CHUNK_BYTES, open_blob,
)
from document_explorer.models import DatabaseBackup  # noqa: E402

mode = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else ""
copies = DatabaseBackup.objects.filter(
    status__in=(DatabaseBackup.STATUS_READY,
                DatabaseBackup.STATUS_DOWNLOADED),
    removed_from_bucket_at__isnull=True,
)
backup = (copies.get(file_name=name) if name
          else copies.order_by("-started_at").first())
if mode == "meta":
    print(json.dumps({
        "file_name": backup.file_name, "sha256": backup.sha256,
        "status": backup.status, "row_counts": backup.row_counts,
    }))
else:
    handle = open_blob(backup)
    out = sys.stdout.buffer
    while True:
        chunk = handle.read(CHUNK_BYTES)
        if not chunk:
            break
        out.write(chunk)
    out.flush()
