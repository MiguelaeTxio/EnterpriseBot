# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/drive_folder_test.py
"""
Script de prueba de una sola vez (H31, S112). Crea (o localiza si ya
existe) una carpeta de Drive con la credencial OAuth drive.file ya
configurada del servidor, para verificar si es visible desde el
conector de Google Drive del modelo (misma cuenta de Google, scope
distinto). Imprime el id de la carpeta.
"""
from spare_parts.gdrive_service import get_drive_service, ensure_root_folder

service = get_drive_service()
folder_id = ensure_root_folder(
    service,
    folder_name='EnterpriseBot - Intercambio Claude (prueba S112)',
)
print(folder_id)
