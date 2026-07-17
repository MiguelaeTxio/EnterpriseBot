# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/gcs_service.py
"""
Google Cloud Storage persistence -- sucesor de gdrive_service.py para
toda subida nueva (S022, H23 prioridad 0). Ver gdrive_service.py para
el histórico y el motivo de por qué Drive usaba OAuth delegado a un
usuario en vez de Service Account.

---

## Por qué aquí SÍ vale la Service Account (a diferencia de Drive)

Verificado en línea 2026-07-16 (Directriz 4.4/SINE QUA NON): el
problema real que forzó OAuth delegado en Drive era que un Service
Account no tiene cuota de almacenamiento propia fuera de una Shared
Drive de Google Workspace. Ese problema es específico de Drive -- no
existe en Google Cloud Storage. GCS factura el almacenamiento
directamente al proyecto de GCP (billing account "Grúas Álvarez",
`gen-lang-client-0961484137`, el mismo ya usado para Vertex AI), no a
ninguna cuota personal. Por tanto, la misma Service Account JSON que ya
autentica Vertex AI (`GCP_CREDENTIALS_PATH`, Directriz 4.1) es
directamente válida aquí, sin flujo OAuth ni autorización de un solo
uso -- solo hace falta que esa Service Account tenga el rol de IAM
adecuado sobre el proyecto (ver el bloque "Configuración manual
requerida" más abajo, instrucciones exactas entregadas a Miguel Ángel
en la sesión S022).

## Buckets privados + URL firmada bajo demanda (nunca acceso público)

Decisión explícita de Miguel Ángel (S022): el acceso a cualquier
documento se hace única y exclusivamente a través de la plataforma,
nunca por un enlace suelto. Por eso, a diferencia de Drive (que
compartía "cualquiera con el enlace puede ver"), aquí los buckets se
crean con acceso uniforme a nivel de bucket y SIN ningún IAM binding
público -- los objetos son privados por defecto. Cuando la plataforma
necesita mostrar/descargar un archivo, genera una URL firmada V4 al
vuelo (`generate_signed_url()`, ver más abajo) con una expiración
corta -- nunca se persiste esa URL en BD porque caducaría; lo que se
persiste es `gcs_blob_name` (la ruta del objeto dentro del bucket).

La firma V4 no necesita ningún permiso IAM adicional (ni
`iam.serviceAccounts.signBlob` ni "Service Account Token Creator"):
se calcula localmente con la clave privada que ya contiene el fichero
JSON de la Service Account (mismo fichero de `GCP_CREDENTIALS_PATH`),
sin llamada de red a Google para firmar.

## Organización de cada bucket -- "servidor de archivos", nunca carpetas
## que el usuario deba conocer (mismo principio ya aplicado en H23)

Un bucket de GCS es un espacio de nombres plano (no hay carpetas
reales, a diferencia de Drive) -- lo que en Drive era una jerarquía de
carpetas aquí es un prefijo dentro del nombre del objeto
(`gcs_blob_name`), construido siempre por este módulo a partir de
datos semánticos del objeto de negocio (fecha, código de máquina,
tipo de documento...), nunca elegido por quien sube el archivo:

- Fotos de tarea (`TASK_PHOTOS_BUCKET`): `{AAAA-MM}/{pk}_{máquina}_{nombre}`
- Albaranes (`DELIVERY_NOTES_BUCKET`): `{AAAA-MM}/{número_o_pk}_{nombre}`
- Documentación de centros de gasto (`MACHINE_DOCUMENTS_BUCKET`):
  `{código_máquina}/{tipo_documento} - {nombre_legible}{extensión}`
- Documentación de personal (`PERSONNEL_DOCUMENTS_BUCKET`): bucket
  creado y reservado desde S022, sin función de subida propia todavía
  -- H25 la construye cuando se retome ese hito (ver
  ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md).

---

## Configuración manual requerida (Miguel Ángel, consola de Google Cloud)

1. **IAM de la Service Account** (la misma de `GCP_CREDENTIALS_PATH`):
   rol `roles/storage.admin` sobre el proyecto `gen-lang-client-0961484137`
   -- necesario para crear los buckets (paso único) y para
   leer/escribir/borrar objetos en ellos (uso normal). Si se prefiere
   un alcance más estrecho tras la creación de los buckets, se puede
   bajar a `roles/storage.objectAdmin` acotado a los 4 buckets --
   decisión de Miguel Ángel, no asumida aquí.
2. **Los 4 buckets** se crean mediante el comando de gestión
   `create_gcs_buckets` (idempotente, ver ese comando) -- no hace
   falta crearlos a mano en la consola.

## Env vars requeridas (ya existentes por Directriz 4.1, reutilizadas
## tal cual -- ninguna variable nueva)

- `GCP_CREDENTIALS_PATH`: ruta al JSON de la Service Account.
- `GOOGLE_CLOUD_PROJECT`: id del proyecto GCP.
"""
import logging
import os
from datetime import timedelta

from google.cloud import storage

logger = logging.getLogger(__name__)

# Nombres de bucket -- únicos en todo Google Cloud, no solo en esta
# cuenta (a diferencia de una carpeta de Drive). Ver la sección
# "Organización de cada bucket" arriba para el prefijo semántico usado
# dentro de cada uno.
TASK_PHOTOS_BUCKET = 'enterprisebot-alvarez-task-photos'
DELIVERY_NOTES_BUCKET = 'enterprisebot-alvarez-delivery-notes'
MACHINE_DOCUMENTS_BUCKET = 'enterprisebot-alvarez-machine-documents'
PERSONNEL_DOCUMENTS_BUCKET = 'enterprisebot-alvarez-personnel-documents'

ALL_BUCKETS = (
    TASK_PHOTOS_BUCKET,
    DELIVERY_NOTES_BUCKET,
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
)

# Región del bucket. 'EU' (multi-región Europa) -- coherente con que
# Grupo Álvarez opera en España y con la ubicación ya usada por el
# resto de servicios de Google del proyecto (Vertex AI location
# 'global', sin restricción geográfica específica documentada que
# obligue a otra cosa). Si Miguel Ángel prefiere una región concreta
# (ej. 'europe-southwest1', Madrid) en vez de la multi-región 'EU',
# es un cambio de una sola constante aquí, sin impacto en el resto del
# módulo.
BUCKET_LOCATION = 'EU'

# Duración de las URLs firmadas servidas al navegador. Corta a
# propósito -- el acceso real de control es la autenticación del
# panel, la URL firmada es solo el mecanismo de entrega puntual de
# ese archivo concreto ya autorizado.
SIGNED_URL_EXPIRATION = timedelta(minutes=30)

_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


def sanitize_path_component(value) -> str:
    """
    Sustituye '/' por '-' en un componente de gcs_blob_name derivado
    de un dato de negocio (número de albarán, código de máquina...).

    GCS trata '/' como separador visual de "carpeta" dentro del
    nombre del objeto -- un dato real con '/' en medio (visto en
    producción, S022: números de albarán con formato 'BA/2606366')
    crearía una jerarquía anidada no intencionada en vez de un único
    segmento plano, exactamente el desorden que esta migración existe
    para eliminar (ver docstring del módulo, "servidor de archivos").
    Corregido en S022 tras detectarlo en los 10 primeros albaranes
    migrados de Drive.

    ---

    Replaces '/' with '-' in a gcs_blob_name component derived from a
    business value (delivery number, machine code...).

    GCS treats '/' as a visual "folder" separator within the object
    name -- a real value containing '/' (seen in production, S022:
    delivery numbers formatted like 'BA/2606366') would create an
    unintended nested hierarchy instead of a single flat segment,
    exactly the mess this migration exists to remove (see module
    docstring, "servidor de archivos"). Fixed in S022 after being
    detected in the first 10 delivery notes migrated from Drive.
    """
    return str(value).replace('/', '-')


class GCSNotConfigured(Exception):
    """
    Se lanza cuando faltan las variables de entorno necesarias para
    acceder a GCS -- distinto de un fallo real de la API, para que
    quien la llame (la tarea Celery) pueda distinguir en los logs "aún
    no configurado" de "Google devolvió un error". Mismo principio que
    GDriveNotConfigured en gdrive_service.py.
    """


def get_storage_client() -> storage.Client:
    """
    Devuelve un cliente storage.Client autenticado con la Service
    Account de GCP_CREDENTIALS_PATH -- mismo patrón que
    ai_services.gemini_client.get_gemini_client() (Directriz 4.1):
    fija GOOGLE_APPLICATION_CREDENTIALS a partir de GCP_CREDENTIALS_PATH
    si aún no está fijada, y deja que la librería la resuelva vía
    Application Default Credentials.
    """
    credentials_path = os.environ.get('GCP_CREDENTIALS_PATH', '')
    project = os.environ.get('GOOGLE_CLOUD_PROJECT')

    if not credentials_path or not project:
        raise GCSNotConfigured(
            'Faltan GCP_CREDENTIALS_PATH / GOOGLE_CLOUD_PROJECT en el '
            'entorno -- deberían existir ya (Directriz 4.1, mismas '
            'variables que usa Vertex AI). Revisar .env en el servidor.'
        )

    os.environ.setdefault('GOOGLE_APPLICATION_CREDENTIALS', credentials_path)
    return storage.Client(project=project)


def ensure_bucket(client: storage.Client, bucket_name: str) -> storage.Bucket:
    """
    Busca el bucket por nombre, creándolo si todavía no existe
    (idempotente -- seguro llamarlo siempre, mismo espíritu que
    ensure_root_folder() en gdrive_service.py). Creado con acceso
    uniforme a nivel de bucket y sin ningún IAM binding público --
    privado por defecto (ver docstring del módulo). Devuelve el
    objeto Bucket.
    """
    bucket = client.bucket(bucket_name)
    if bucket.exists():
        return bucket

    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    created = client.create_bucket(bucket, location=BUCKET_LOCATION)
    logger.info(
        '# [gcs_service] Bucket "%s" creado (location=%s, acceso '
        'uniforme, privado).',
        bucket_name, BUCKET_LOCATION,
    )
    return created


def upload_file(bucket_name: str, blob_name: str, file_path: str) -> str:
    """
    Sube el archivo local en file_path al bucket/blob_name indicados.
    No borra el archivo local -- eso es responsabilidad de quien
    llama, mismo principio que gdrive_service.py. Devuelve
    blob_name tal cual (para que el caller lo persista en BD).
    """
    extension = os.path.splitext(file_path)[1].lower()
    content_type = _MIME_TYPES.get(extension, 'application/octet-stream')

    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(file_path, content_type=content_type)

    logger.info(
        '# [gcs_service] Subido a gs://%s/%s.', bucket_name, blob_name,
    )
    return blob_name


def generate_signed_url(bucket_name: str, blob_name: str) -> str:
    """
    Genera una URL V4 firmada, válida durante SIGNED_URL_EXPIRATION,
    para leer (GET) el objeto indicado. Se genera al vuelo en cada
    petición -- nunca se persiste en BD (caducaría). Firma local con
    la clave privada de la Service Account, sin llamada de red extra
    a Google (ver docstring del módulo).
    """
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.generate_signed_url(
        version='v4', expiration=SIGNED_URL_EXPIRATION, method='GET',
    )


def delete_file(bucket_name: str, blob_name: str) -> None:
    """
    Borra el objeto indicado del bucket. Idempotente frente a un
    objeto ya inexistente (no lanza si no existe) -- mismo criterio
    de tolerancia que document_ingestion.management.commands.
    reset_documentation aplica sobre GCS.
    """
    from google.cloud.exceptions import NotFound

    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    try:
        blob.delete()
    except NotFound:
        pass


def download_bytes(bucket_name: str, blob_name: str) -> bytes:
    """
    Descarga y devuelve los bytes crudos de un objeto -- añadida S024
    para el "generar dossier" de document_management.pdf_merge_service
    (anexo H26 sección 2.2): el llamador (vista de panel) resuelve qué
    documentos combinar y usa esta función para bajar cada PDF antes
    de fusionarlos.
    """
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def upload_bytes(bucket_name: str, blob_name: str, data: bytes) -> str:
    """
    Sube bytes crudos directamente a un blob, sin pasar por un archivo
    local -- añadida S024 para dos casos que no tienen un
    FileField/ruta local disponible: (1) el reenrutado de documentos
    "sin asignar" (document_ingestion.tasks.retry_unassigned_routing),
    donde el blob ya se descargó en memoria y hay que subirlo de
    nuevo bajo la ruta correcta tras encontrar la entidad real; (2) el
    dossier temporal (panel/views_documentation.py,
    DossierGenerateView), que nunca toca disco local -- se genera en
    memoria (pdf_merge_service.merge_pdfs()) y se sube directamente.
    Devuelve el gcs_blob_name (idéntico a `blob_name`, por coherencia
    de firma con upload_file()).
    """
    client = get_storage_client()
    bucket = ensure_bucket(client, bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type="application/pdf")
    logger.info(
        "# [gcs_service] %d bytes subidos directamente a gs://%s/%s.",
        len(data), bucket_name, blob_name,
    )
    return blob_name


# ----------------------------------------------------------------------
# Funciones upload_* por modelo -- mismo patrón/firma que
# gdrive_service.py, para que work_order_processor/tasks.py,
# spare_parts/tasks.py y machine_documents/tasks.py cambien solo el
# import y el nombre de la función, no la lógica que las envuelve.
# ----------------------------------------------------------------------

def upload_task_photo_file(photo) -> str:
    """
    Sube la imagen de un TaskPhoto (work_order_processor) a
    TASK_PHOTOS_BUCKET, bajo el prefijo 'AAAA-MM' (según
    photo.created_at) -- mismo criterio de organización que tenía
    Drive. Devuelve el gcs_blob_name para que el caller lo persista.
    NO borra el archivo local ni toca el modelo -- responsabilidad del
    caller (work_order_processor/tasks.py).
    """
    if not photo.image:
        raise ValueError(
            f'TaskPhoto #{photo.pk} sin archivo asociado -- nada que subir.'
        )

    file_path = photo.image.path
    file_name = os.path.basename(file_path)
    year_month = photo.created_at.strftime('%Y-%m')
    machine_label = (
        photo.machine_asset.code if photo.machine_asset_id else 'sin-maquina'
    )
    blob_name = (
        f'{year_month}/{photo.pk}_{sanitize_path_component(machine_label)}'
        f'_{file_name}'
    )

    result = upload_file(TASK_PHOTOS_BUCKET, blob_name, file_path)
    logger.info(
        '# [gcs_service] TaskPhoto #%d subida a GCS (blob=%s).',
        photo.pk, result,
    )
    return result


def upload_delivery_note_file(delivery_note) -> str:
    """
    Sube el archivo origen (image o pdf_file) de un DeliveryNote a
    DELIVERY_NOTES_BUCKET, bajo el prefijo 'AAAA-MM' (según
    delivery_note.created_at) -- mismo criterio que tenía Drive.
    Devuelve el gcs_blob_name. NO borra el archivo local ni toca el
    modelo -- responsabilidad del caller (spare_parts/tasks.py).
    """
    file_field = delivery_note.image or delivery_note.pdf_file
    if not file_field:
        raise ValueError(
            f'Albarán #{delivery_note.pk} sin archivo asociado -- '
            f'nada que subir.'
        )

    file_path = file_field.path
    file_name = os.path.basename(file_path)
    year_month = delivery_note.created_at.strftime('%Y-%m')
    identifier = delivery_note.delivery_number or delivery_note.pk
    blob_name = f'{year_month}/{sanitize_path_component(identifier)}_{file_name}'

    result = upload_file(DELIVERY_NOTES_BUCKET, blob_name, file_path)
    logger.info(
        '# [gcs_service] Albarán #%d subido a GCS (blob=%s).',
        delivery_note.pk, result,
    )
    return result


def upload_machine_document_file(document) -> str:
    """
    Sube el source_file de un MachineDocument a
    MACHINE_DOCUMENTS_BUCKET, bajo el prefijo del código de máquina
    (document.machine_asset.code) -- mismo criterio que tenía Drive
    (documentación organizada por centro de gasto, no por mes). Si
    machine_asset es nulo (documento "sin asignar" de la ingesta
    automática de carpeta, S024 -- ver MachineDocument.Status.UNASSIGNED),
    usa la subcarpeta fija 'SIN_ASIGNAR' en su lugar, para no fallar ni
    bloquear la subida mientras nadie lo vincula a mano.
    Devuelve el gcs_blob_name. NO borra el archivo local ni toca el
    modelo -- responsabilidad del caller (machine_documents/tasks.py).
    """
    if not document.source_file:
        raise ValueError(
            f'MachineDocument #{document.pk} sin archivo asociado -- '
            f'nada que subir.'
        )

    file_path = document.source_file.path
    extension = os.path.splitext(file_path)[1].lower()
    machine_code = (
        document.machine_asset.code if document.machine_asset_id
        else 'SIN_ASIGNAR'
    )
    blob_name = (
        f'{machine_code}/{sanitize_path_component(document.document_type)} - '
        f'{sanitize_path_component(document.display_name)}{extension}'
    )

    result = upload_file(MACHINE_DOCUMENTS_BUCKET, blob_name, file_path)
    logger.info(
        '# [gcs_service] MachineDocument #%d subido a GCS (blob=%s, '
        'máquina %s).',
        document.pk, result, machine_code,
    )
    return result


def upload_personal_document_file(document) -> str:
    """
    Sube el source_file de un PersonalDocument a
    PERSONNEL_DOCUMENTS_BUCKET, bajo el prefijo del DNI del trabajador
    (document.company_user.dni) cuando hay trabajador enlazado, o la
    subcarpeta fija 'SIN_ASIGNAR' si company_user es nulo (documento
    "sin asignar" de la ingesta automática de carpeta, S024 -- ver
    PersonalDocument.Status.UNASSIGNED). Mismo criterio de
    organización que MachineDocument (por entidad, no por mes).
    Devuelve el gcs_blob_name. NO borra el archivo local ni toca el
    modelo -- responsabilidad del caller (personal_documents/tasks.py).
    """
    if not document.source_file:
        raise ValueError(
            f'PersonalDocument #{document.pk} sin archivo asociado -- '
            f'nada que subir.'
        )

    file_path = document.source_file.path
    extension = os.path.splitext(file_path)[1].lower()
    if document.company_user_id and document.company_user.dni:
        worker_label = document.company_user.dni
    else:
        worker_label = 'SIN_ASIGNAR'
    blob_name = (
        f'{sanitize_path_component(worker_label)}/'
        f'{sanitize_path_component(document.document_type)} - '
        f'{sanitize_path_component(document.display_name)}{extension}'
    )

    result = upload_file(PERSONNEL_DOCUMENTS_BUCKET, blob_name, file_path)
    logger.info(
        '# [gcs_service] PersonalDocument #%d subido a GCS (blob=%s, '
        'trabajador %s).',
        document.pk, result, worker_label,
    )
    return result
