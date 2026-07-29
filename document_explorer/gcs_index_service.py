# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/gcs_index_service.py
"""
Reading GCS structure for the document index (H29).

Two ways of discovering folders, deliberately kept side by side because
Google recommends a different one for each job:

- Full sweep of a bucket -- `iter_all_folders()`, backed by the Storage
  Control API. One paginated sequence returns every folder, EMPTY ONES
  INCLUDED. The object listing API never returns them.
- Refreshing a single folder -- `list_folder_children()`, backed by the
  object listing API with a delimiter. The official documentation warns
  that listing a whole hierarchical-namespace bucket is expensive
  because it has to walk every folder, and that listing within a
  specific prefix is the efficient path. That makes this the mechanism
  for routine refreshes, and the full sweep the exception.

Empty folders only exist at all in buckets with hierarchical namespace
enabled. In a flat bucket a "folder" is nothing but the prefix of an
existing object, so an empty one is not missing from the index -- it
cannot exist. Callers must not warn about it there.

---

Lectura de la estructura de GCS para el índice documental (H29).

Dos formas de descubrir carpetas, mantenidas a propósito una junto a
otra porque Google recomienda una distinta para cada tarea:

- Barrido completo de un cubo -- `iter_all_folders()`, sobre la API de
  Storage Control. Una secuencia paginada devuelve todas las carpetas,
  INCLUIDAS LAS VACÍAS. La API de listado de objetos no las devuelve
  nunca.
- Refresco de una carpeta concreta -- `list_folder_children()`, sobre
  la API de listado de objetos con delimitador. La documentación
  oficial advierte de que listar un cubo entero con Namespace
  Jerárquico es costoso porque obliga a recorrer todas las carpetas, y
  de que listar dentro de un prefijo concreto es el camino eficiente.
  Eso convierte a este en el mecanismo del refresco rutinario, y al
  barrido completo en la excepción.

Las carpetas vacías solo existen en cubos con Namespace Jerárquico
activado. En un cubo plano una "carpeta" no es más que el prefijo de un
objeto existente, así que una carpeta vacía no falta del índice: no
puede existir. Quien llame a esto no debe avisar de nada allí.
"""
import os

from google.cloud import storage_control_v2

from spare_parts.gcs_service import GCSNotConfigured

# Proyecto "_" en el nombre de recurso: identifica un cubo de alcance
# global, que es como la API de Storage Control referencia cualquier
# cubo sin necesidad del id de proyecto.
_GLOBAL_PROJECT = "_"


def get_storage_control_client():
    """
    Return an authenticated Storage Control client.

    Mirrors the credential contract of
    spare_parts.gcs_service.get_storage_client() -- same service
    account, same environment variables -- but cannot reuse it: that
    one builds a storage.Client, and folder operations live on a
    different client class entirely.

    ---

    Devuelve un cliente autenticado de Storage Control.

    Replica el contrato de credenciales de
    spare_parts.gcs_service.get_storage_client() -- misma cuenta de
    servicio, mismas variables de entorno -- pero no puede reutilizarlo:
    aquel construye un storage.Client, y las operaciones sobre carpetas
    viven en una clase de cliente completamente distinta.
    """
    credentials_path = os.environ.get("GCP_CREDENTIALS_PATH", "")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if not credentials_path or not project:
        raise GCSNotConfigured(
            "Faltan GCP_CREDENTIALS_PATH / GOOGLE_CLOUD_PROJECT en el "
            "entorno -- mismas variables que usa el resto de la "
            "plataforma para GCS y Vertex AI (Directriz 4.1)."
        )

    os.environ.setdefault(
        "GOOGLE_APPLICATION_CREDENTIALS", credentials_path,
    )
    return storage_control_v2.StorageControlClient()


def has_hierarchical_namespace(client, bucket_name) -> bool:
    """
    Whether the bucket was created with hierarchical namespace.

    The setting cannot be changed after bucket creation, so the answer
    is stable for the life of the bucket.

    ---

    Si el cubo se creó con Namespace Jerárquico.

    El ajuste no se puede cambiar después de crear el cubo, así que la
    respuesta es estable durante toda su vida.
    """
    bucket = client.get_bucket(bucket_name)
    return bool(bucket.hierarchical_namespace_enabled)


def iter_all_folders(bucket_name, prefix=""):
    """
    Yield every folder path in a bucket, empty ones included.

    Only valid on hierarchical-namespace buckets. Paths come back
    without the trailing slash the API uses, to match how the index
    stores them.

    ---

    Devuelve todas las rutas de carpeta de un cubo, incluidas las
    vacías.

    Solo válido en cubos con Namespace Jerárquico. Las rutas salen sin
    la barra final que usa la API, para coincidir con la forma en que
    las guarda el índice.
    """
    control = get_storage_control_client()
    request = storage_control_v2.ListFoldersRequest(
        parent=control.bucket_path(_GLOBAL_PROJECT, bucket_name),
        prefix=prefix,
    )
    for folder in control.list_folders(request=request):
        parsed = control.parse_folder_path(folder.name)
        path = parsed["folder"].rstrip("/")
        if path:
            yield path, folder.update_time


def list_folder_children(client, bucket_name, folder_path):
    """
    Direct children of one folder: its files and its subfolders.

    Returns (blobs, subfolder_paths). Prefixes are collected page by
    page rather than from the iterator afterwards: the attribute is
    only populated as pages are consumed, and reading it too early is a
    long-standing source of silently empty results.

    ---

    Hijos directos de una carpeta: sus archivos y sus subcarpetas.

    Devuelve (blobs, rutas_de_subcarpeta). Los prefijos se recogen
    página a página en vez de leerlos del iterador al final: el
    atributo solo se rellena a medida que se consumen las páginas, y
    leerlo antes de tiempo es una fuente conocida de resultados vacíos
    sin ningún error.
    """
    prefix = f"{folder_path}/" if folder_path else ""
    iterator = client.list_blobs(
        bucket_name,
        prefix=prefix,
        delimiter="/",
        include_folders_as_prefixes=True,
    )

    blobs = []
    subfolders = set()
    for page in iterator.pages:
        for blob in page:
            # El propio objeto-carpeta del prefijo pedido aparece en
            # los items; no es un hijo.
            if blob.name.endswith("/"):
                continue
            blobs.append(blob)
        subfolders.update(page.prefixes or ())

    paths = sorted(p.rstrip("/") for p in subfolders if p.rstrip("/"))
    return blobs, paths
