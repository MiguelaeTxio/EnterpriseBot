# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/models.py
"""
Models for the panel file explorer over Google Cloud Storage (H29).

Design constraints these models exist to satisfy, all decided by
Miguel Angel in S037 and recorded verbatim in the H29 annex:

- Browsing, listing and searching hit the database only. Google Cloud
  Storage is touched exclusively when a document's content is opened.
- A local deletion in the Microsoft 365 folders is NEVER mirrored as a
  cloud deletion. The only thing taken from the local file system is
  the `exists_in_local` flag.
- Deletion has two tiers: a section supervisor deletes logically into
  their OWN trash (invisible to everyone else from that moment), and
  only the administrator purges, which removes the GCS object while
  keeping the row as an audit record.
- Permissions live here, not in Google Cloud IAM, and are recursive
  from any folder prefix.

Performance notes, because this table is expected to hold tens of
thousands of rows and to be browsed constantly:

- Navigation is an indexed equality lookup on `parent_path_hash`,
  never a LIKE over `parent_path`. MySQL cannot index a full-length
  blob path (up to 1024 UTF-8 bytes) inside utf8mb4 without blowing
  InnoDB's key limit, so the readable text is stored unindexed and a
  SHA-256 hex digest carries the index.
- Folders are rows too, with precomputed counters, so listing a folder
  never issues one COUNT per child.
- `domain_object` must NOT be dereferenced while browsing: doing so
  per row is an N+1. It is resolved only when a single document is
  opened.

---

Modelos del explorador de archivos del panel sobre Google Cloud
Storage (H29).

Restricciones de diseño que estos modelos existen para cumplir, todas
decididas por Miguel Ángel en S037 y registradas verbatim en el anexo:

- Navegar, listar y buscar consultan solo la base de datos. A Google
  Cloud Storage se accede únicamente al abrir el contenido de un
  documento.
- Un borrado en local en las carpetas de Microsoft 365 NUNCA se
  refleja como borrado en la nube. Lo único que se toma del sistema de
  archivos local es la bandera `exists_in_local`.
- El borrado tiene dos niveles: el supervisor de sección borra de
  forma lógica a SU propia papelera (invisible para todos los demás
  desde ese instante), y solo el administrador vacía, lo que elimina
  el objeto en GCS conservando la fila como registro de auditoría.
- Los permisos viven aquí, no en el IAM de Google Cloud, y son
  recursivos desde cualquier prefijo de carpeta.

Notas de rendimiento, porque esta tabla va a tener decenas de miles de
filas y se va a navegar constantemente:

- Navegar es una búsqueda por igualdad indexada sobre
  `parent_path_hash`, nunca un LIKE sobre `parent_path`. MySQL no
  puede indexar una ruta de blob completa (hasta 1024 bytes UTF-8) en
  utf8mb4 sin superar el límite de clave de InnoDB, así que el texto
  legible se guarda sin indexar y el índice lo lleva un resumen
  SHA-256 en hexadecimal.
- Las carpetas también son filas, con contadores precalculados, de
  modo que listar una carpeta jamás lanza un COUNT por cada hijo.
- `domain_object` NO debe resolverse al navegar: hacerlo por fila es
  un N+1. Se resuelve solo al abrir un documento concreto.
"""
import hashlib

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


def path_digest(value: str) -> str:
    """
    Return the SHA-256 hex digest used to index a blob or folder path.

    Normalised to NFC first: the S036 inventory of the dirty bucket
    found 15 names carrying DECOMPOSED accents (a plain letter plus a
    combining mark). Those look identical on screen but are different
    bytes, so without normalising, the same folder would produce two
    different digests and appear twice in the tree.

    ---

    Devuelve el resumen SHA-256 en hexadecimal con el que se indexa la
    ruta de un blob o de una carpeta.

    Se normaliza antes a NFC: el inventario del cubo sucio de S036
    encontró 15 nombres con acentos DESCOMPUESTOS (una letra normal
    más una marca combinante). En pantalla son idénticos a los
    normales pero son bytes distintos, así que sin normalizar la misma
    carpeta produciría dos resúmenes diferentes y aparecería dos veces
    en el árbol.
    """
    import unicodedata

    normalised = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class DocumentIndexEntry(models.Model):
    """
    One row per object or folder in any indexed bucket.

    ---

    Una fila por cada objeto o carpeta de cualquier cubo indexado.
    """

    KIND_FILE = "FILE"
    KIND_FOLDER = "FOLDER"
    KIND_CHOICES = [
        (KIND_FILE, "Archivo"),
        (KIND_FOLDER, "Carpeta"),
    ]

    bucket = models.CharField(
        max_length=63,
        verbose_name="Cubo",
        help_text="Nombre del cubo de Google Cloud Storage.",
    )
    entry_kind = models.CharField(
        max_length=6,
        choices=KIND_CHOICES,
        default=KIND_FILE,
        verbose_name="Tipo de entrada",
    )
    blob_name = models.TextField(
        blank=True,
        verbose_name="Ruta completa en el cubo",
        help_text=(
            "Ruta completa del objeto dentro del cubo. Sin indexar: "
            "el índice lo lleva blob_name_hash."
        ),
    )
    blob_name_hash = models.CharField(
        max_length=64,
        verbose_name="Resumen de la ruta completa",
    )
    parent_path = models.TextField(
        blank=True,
        verbose_name="Carpeta contenedora",
        help_text="Cadena vacía para las entradas de la raíz del cubo.",
    )
    parent_path_hash = models.CharField(
        max_length=64,
        verbose_name="Resumen de la carpeta contenedora",
    )
    name = models.CharField(
        max_length=512,
        verbose_name="Nombre",
        help_text="Último segmento de la ruta.",
    )
    size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Tamaño en bytes",
    )
    content_type = models.CharField(
        max_length=127,
        blank=True,
        verbose_name="Tipo de contenido",
    )
    crc32c = models.CharField(
        max_length=16,
        blank=True,
        verbose_name="CRC32C",
        help_text=(
            "Hash autoritativo: Google Cloud Storage lo garantiza en "
            "todos los objetos."
        ),
    )
    md5_hash = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="MD5",
        help_text=(
            "Opcional. Google Cloud Storage no lo expone en objetos "
            "compuestos ni en subidas multipart de la API XML."
        ),
    )
    generation = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Generación",
        help_text=(
            "Cambia en cada sobrescritura del objeto: permite detectar "
            "un reemplazo sin comparar hashes."
        ),
    )
    gcs_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Última modificación en el cubo",
    )
    child_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Número de hijos",
        help_text=(
            "Precalculado, solo para carpetas. Evita un COUNT por "
            "carpeta al pintar un listado."
        ),
    )
    total_size_bytes = models.BigIntegerField(
        default=0,
        verbose_name="Tamaño acumulado en bytes",
        help_text="Precalculado, solo para carpetas.",
    )
    exists_in_local = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Sigue existiendo en local",
        help_text=(
            "Nulo en los cubos que no tienen espejo local. Es el único "
            "reflejo que se toma de las carpetas de Microsoft 365: un "
            "borrado en local jamás borra nada en la nube."
        ),
    )
    local_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Última comprobación del espejo local",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de borrado virtual",
    )
    deleted_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deleted_index_entries",
        verbose_name="Dueño de la papelera",
        help_text=(
            "Quien lo borró. Solo esa persona ve la entrada mientras "
            "siga en su papelera."
        ),
    )
    purged_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de vaciado",
        help_text=(
            "El objeto ya no existe en el cubo. La fila se conserva "
            "como registro histórico para auditorías."
        ),
    )
    purged_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purged_index_entries",
        verbose_name="Vaciado por",
    )
    domain_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_index_entries",
        verbose_name="Modelo de dominio vinculado",
    )
    domain_object_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Identificador en el modelo de dominio",
    )
    domain_object = GenericForeignKey(
        "domain_content_type",
        "domain_object_id",
    )
    indexed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de alta en el índice",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última actualización de la fila",
    )

    class Meta:
        verbose_name = "Entrada del índice documental"
        verbose_name_plural = "Entradas del índice documental"
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(purged_at__isnull=True),
                fields=("bucket", "blob_name_hash"),
                name="unique_live_blob_per_bucket",
            ),
        ]
        indexes = [
            models.Index(
                fields=["bucket", "parent_path_hash", "deleted_at"],
                name="docidx_navigation",
            ),
            models.Index(
                fields=["bucket", "exists_in_local"],
                name="docidx_local_flag",
            ),
            models.Index(
                fields=["deleted_by", "deleted_at"],
                name="docidx_trash_owner",
            ),
        ]

    def __str__(self):
        return f"{self.bucket}/{self.blob_name}"


class DocumentFolderGrant(models.Model):
    """
    Recursive read/delete permission over a folder prefix of a bucket.

    An empty `path_prefix` grants over the whole bucket. Grants are
    resolved once per request into a set of prefixes and applied as a
    single condition in the navigation query -- never as a per-row
    check in Python.

    ADMIN users are exempt in code and need no rows here.

    ---

    Permiso recursivo de lectura/borrado sobre un prefijo de carpeta de
    un cubo.

    Un `path_prefix` vacio concede sobre el cubo entero. Las
    concesiones se resuelven una sola vez por petición en un conjunto
    de prefijos y se aplican como una única condición en la consulta de
    navegación, nunca como una comprobación por fila en Python.

    Los usuarios ADMIN quedan exentos por código y no necesitan filas
    aquí.
    """

    user = models.ForeignKey(
        "ivr_config.CompanyUser",
        on_delete=models.CASCADE,
        related_name="document_folder_grants",
        verbose_name="Usuario",
    )
    bucket = models.CharField(
        max_length=63,
        verbose_name="Cubo",
    )
    path_prefix = models.TextField(
        blank=True,
        verbose_name="Prefijo de carpeta",
        help_text="Cadena vacía para conceder sobre el cubo entero.",
    )
    path_prefix_hash = models.CharField(
        max_length=64,
        verbose_name="Resumen del prefijo",
    )
    can_read = models.BooleanField(
        default=True,
        verbose_name="Puede consultar",
    )
    can_delete = models.BooleanField(
        default=False,
        verbose_name="Puede borrar a su papelera",
    )
    granted_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_folder_grants_given",
        verbose_name="Concedido por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de concesión",
    )

    class Meta:
        verbose_name = "Concesión sobre carpeta documental"
        verbose_name_plural = "Concesiones sobre carpetas documentales"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "bucket", "path_prefix_hash"),
                name="unique_grant_per_user_and_prefix",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "bucket"],
                name="docgrant_user_bucket",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.bucket}/{self.path_prefix}"
