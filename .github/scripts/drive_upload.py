# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/drive_upload.py
"""
Sube un archivo local a la carpeta de intercambio de solo lectura con
el modelo en Drive ("EnterpriseBot - Intercambio Claude"), reutilizando
la credencial OAuth ya configurada del proyecto
(spare_parts.gdrive_service.get_drive_service()) -- com-actions-relay.

A diferencia de upload_machine_document_file/upload_delivery_note_file
de gdrive_service.py, este script NUNCA comparte el archivo como
"cualquiera con el enlace puede ver" -- el archivo queda privado,
visible solo para la cuenta de Google propietaria (la misma que usa
el conector de Drive del modelo, com-actions-relay sección 2). Nunca
añadir aquí una llamada a permissions().create().

Uso: python3 drive_upload.py <ruta_local> <nombre_en_drive> <folder_id>
Imprime el id del archivo subido.
"""
import io
import os
import sys

from googleapiclient.http import MediaIoBaseUpload

from spare_parts.gdrive_service import get_drive_service

# Extiende el mapa de gdrive_service._MIME_TYPES (que no cubre texto)
# con los tipos reales que produce este relevo -- fallback a
# octet-stream para cualquier otra extensión, mismo criterio que el
# resto del módulo.
_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.md': 'text/markdown',
    '.txt': 'text/plain',
    '.log': 'text/plain',
    '.csv': 'text/csv',
    '.json': 'application/json',
}

local_path, drive_name, folder_id = sys.argv[1:4]
extension = os.path.splitext(drive_name)[1].lower()
mime_type = _MIME_TYPES.get(extension, 'application/octet-stream')

service = get_drive_service()
with open(local_path, 'rb') as f:
    media = MediaIoBaseUpload(
        io.BytesIO(f.read()), mimetype=mime_type, resumable=False,
    )

uploaded = service.files().create(
    body={'name': drive_name, 'parents': [folder_id]},
    media_body=media,
    fields='id',
).execute()

print(uploaded['id'])
