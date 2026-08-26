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
from django.template.defaultfilters import filesizeformat


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
        help_text=(
            "Uso ampliado desde H30 (S045): además del espejo 1:1 "
            "original (`TaskPhoto`/`DeliveryNote`, un cubo = un "
            "modelo, `DOMAIN_MODEL_BY_BUCKET`), este mismo campo "
            "sirve para vincular un documento del cubo histórico "
            "(`cgs_grupo_alvarez`) con su sujeto real -- "
            "`fleet.MachineAsset` o `document_explorer.PersonIdentity` "
            "-- durante la clasificación H29. Mismo mecanismo, dos "
            "usos: 1:1 (esta fila ES el objeto) o N:1 (esta fila "
            "PERTENECE al objeto). Nunca se resuelve para el segundo "
            "uso vía `link_domain_objects()` (que sigue acotado a "
            "`DOMAIN_MODEL_BY_BUCKET`) -- lo rellena directamente el "
            "servicio de clasificación al resolver la máquina/persona "
            "del documento."
        ),
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
    document_type = models.ForeignKey(
        "DocumentTypeCatalog",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entries",
        verbose_name="Tipo documental",
        help_text=(
            "H30 (S045). Copia estructurada y consultable del "
            "`document_type_code` que hoy solo vive incrustado en el "
            "nombre de archivo (ver `naming_service`) -- necesaria "
            "para poder preguntar '¿qué otros documentos de este "
            "mismo tipo tiene ya este sujeto?' sin tener que parsear "
            "nombres. Genérico a propósito: un tipo documental nuevo "
            "(p. ej. DECA) es una fila nueva en `DocumentTypeCatalog`, "
            "nunca una migración de este modelo."
        ),
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de caducidad",
        help_text=(
            "H30 (S045). Genérico para cualquier tipo documental con "
            "fecha de caducidad clara (ITV, seguro, OCA...) -- "
            "extraído por Gemini durante la clasificación, nunca de "
            "metadatos de archivo. Vacío para tipos sin caducidad "
            "(usar `issue_date`) o sin fecha aplicable (manuales)."
        ),
    )
    issue_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de emisión",
        help_text=(
            "H30 (S045). Para tipos sin caducidad propia (ficha "
            "técnica, declaración CE...) donde el más reciente del "
            "mismo tipo es el vigente -- mismo criterio ya usado por "
            "`document_management.vigencia_service`."
        ),
    )
    is_obsolete = models.BooleanField(
        default=False,
        verbose_name="Obsoleto",
        help_text=(
            "H30 (S48). Marcador persistido de trazabilidad: True "
            "cuando un documento más reciente del mismo tipo y mismo "
            "sujeto lo ha sustituido "
            "(vigencia_service.evaluate_substitution()). Nunca se "
            "mueve ni se borra el archivo real (4.12) -- solo cambia "
            "este campo, para conservar el histórico completo (libro "
            "de revisiones/reparaciones). Miguel Ángel, verbatim: "
            "\"marcandola como obsoleta... para que siempre haya una "
            "trazabilidad y un registro histórico\"."
        ),
    )
    curator_note = models.TextField(
        blank=True,
        verbose_name="Anotación del supervisor (No Conformes)",
        help_text=(
            "Escrita a mano por un administrador o supervisor con "
            "permiso sobre la carpeta NO CONFORMES para desambiguar "
            "el archivo en el próximo reencolado a cuarentena -- p. "
            "ej. 'DNI 74633524I -> 74633524L'. Gemini la recibe como "
            "parte del prompt en la siguiente clasificación."
        ),
    )
    curator_note_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="curator_annotated_index_entries",
        verbose_name="Anotado por",
    )
    curator_note_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de la anotación",
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

    @property
    def is_folder(self) -> bool:
        """
        Whether this row is a folder.

        ---

        Si esta fila es una carpeta.
        """
        return self.entry_kind == self.KIND_FOLDER

    @property
    def display_size(self) -> str:
        """
        Human-readable size: the object's own, or a folder's total.

        Both are already stored, so this never triggers a query. A
        folder's total was accumulated at indexing time precisely to
        avoid asking the database for a recursive sum here.

        ---

        Tamaño legible: el propio del objeto, o el acumulado de la
        carpeta.

        Los dos están ya guardados, así que esto no dispara ninguna
        consulta. El acumulado de una carpeta se calculó al indexar
        justamente para no pedirle aquí a la base de datos una suma
        recursiva.
        """
        value = (
            self.total_size_bytes if self.is_folder else self.size_bytes
        )
        if not value:
            return "—"
        return filesizeformat(value)


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


class DocumentTypeCatalog(models.Model):
    """
    Closed catalog of document types for the H29 renaming engine.

    Deliberately independent from
    `document_ingestion.LearnedDocumentTypeKeyword` (H23/H25, open
    per-company categories learned from whatever Gemini proposes) --
    Miguel Angel decided in S040 to build H29 fully isolated from
    H17-H25, since that infrastructure was abandoned mid-way. Gemini
    only ever *suggests* a `code` from this fixed catalog; the actual
    filename is always built by `naming_service`, never taken from
    Gemini's own wording.

    ---

    Catálogo cerrado de tipos documentales para el motor de renombrado
    de H29.

    Deliberadamente independiente de
    `document_ingestion.LearnedDocumentTypeKeyword` (H23/H25,
    categorías libres por empresa aprendidas de lo que proponga
    Gemini) -- Miguel Ángel decidió en S040 construir H29 totalmente
    aislado de H17-H25, por ser infraestructura abandonada a medias.
    Gemini únicamente *sugiere* un `code` de este catálogo fijo; el
    nombre de archivo final siempre lo construye `naming_service`,
    nunca se toma tal cual de lo que devuelva Gemini.
    """

    DOMAIN_MACHINE = "MACHINE"
    DOMAIN_PERSONAL = "PERSONAL"
    DOMAIN_BOTH = "BOTH"
    DOMAIN_COMPANY = "COMPANY"
    DOMAIN_CHOICES = [
        (DOMAIN_MACHINE, "Maquinaria"),
        (DOMAIN_PERSONAL, "Personal"),
        (DOMAIN_BOTH, "Ambos"),
        (
            DOMAIN_COMPANY,
            "Empresa y obra (CompanyWorksite, H30 S58)",
        ),
    ]

    FAMILY_CIRCULACION = "CIRCULACION"
    FAMILY_TECNICA_SEGURIDAD = "TECNICA_SEGURIDAD"
    FAMILY_SEGUROS = "SEGUROS"
    FAMILY_FINANCIERO = "FINANCIERO"
    FAMILY_BAJAS_MAQUINA = "BAJAS_MAQUINA"
    FAMILY_ADMINISTRATIVO = "ADMINISTRATIVO"
    FAMILY_IDENTIDAD_PERSONAL = "IDENTIDAD_PERSONAL"
    FAMILY_LABORAL = "LABORAL"
    FAMILY_SALUD_BAJAS_PERSONA = "SALUD_BAJAS_PERSONA"
    FAMILY_PRL_FORMACION = "PRL_FORMACION"
    FAMILY_OTROS_DOCUMENTOS = "OTROS_DOCUMENTOS"
    FAMILY_MEDIA = "MEDIA"
    FAMILY_CHOICES = [
        (FAMILY_CIRCULACION, "Circulación"),
        (FAMILY_TECNICA_SEGURIDAD, "Técnica y seguridad"),
        (FAMILY_SEGUROS, "Seguros"),
        (FAMILY_FINANCIERO, "Financiero y compraventa"),
        (FAMILY_BAJAS_MAQUINA, "Bajas de máquina"),
        (FAMILY_ADMINISTRATIVO, "Administrativo"),
        (FAMILY_IDENTIDAD_PERSONAL, "Identidad y personal (base)"),
        (FAMILY_LABORAL, "Laboral"),
        (FAMILY_SALUD_BAJAS_PERSONA, "Salud y bajas de persona"),
        (FAMILY_PRL_FORMACION, "PRL y formación"),
        (FAMILY_OTROS_DOCUMENTOS, "Otros documentos"),
        (
            FAMILY_MEDIA,
            "Media (imagen, vídeo, audio) — H30 S67",
        ),
    ]

    code = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Código",
        help_text=(
            "Código corto usado literalmente en el nombre de archivo "
            "generado por naming_service (mayúsculas, sin espacios ni "
            "acentos, p. ej. 'ITV', 'RECONOCIMIENTO_MEDICO')."
        ),
    )
    label = models.CharField(
        max_length=150,
        verbose_name="Nombre visible",
        help_text="Nombre legible mostrado en la interfaz del explorador.",
    )
    domain = models.CharField(
        max_length=8,
        choices=DOMAIN_CHOICES,
        default=DOMAIN_BOTH,
        verbose_name="Dominio",
        help_text="A qué tipo de entidad aplica este tipo documental.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text=(
            "Desactivar en vez de borrar conserva el histórico de "
            "archivos ya renombrados con este código."
        ),
    )
    family = models.CharField(
        max_length=32,
        choices=FAMILY_CHOICES,
        blank=True,
        verbose_name="Familia de documento",
        help_text=(
            "H30 (S49). Agrupación del acordeón de la ficha (en vez "
            "de solo Vigentes/Histórico) y base de la búsqueda "
            "granular ('ver el seguro de esta máquina'). Lista fija "
            "de choices en código (a diferencia de tracks_expiry/"
            "ocr_unreliable) porque las familias son un puñado "
            "estable de categorías, no crecen sesión a sesión como "
            "los tipos documentales -- decisión explícita de Miguel "
            "Ángel (S49). Distinta de la familia normativa de "
            "máquina (A/B/Z/H/MK/P/T/V/S de fleet.MachineAsset): "
            "esta agrupa TIPOS DOCUMENTALES para la interfaz, esa "
            "otra dice qué documentos son obligatorios por tipo de "
            "máquina. S51: se añade 'Otros documentos' como familia "
            "catch-all fija número 11 -- Miguel Ángel confirmó que la "
            "lista sigue cerrada por código (no editable en caliente "
            "desde el panel), pero si aparece un tipo nuevo que no "
            "encaje en ninguna de las 10 originales, entra aquí en "
            "vez de bloquear el alta; revisar periódicamente el "
            "volumen de esta familia -- una acumulación real de un "
            "mismo tipo dentro de 'Otros documentos' es la señal para "
            "decidir en sesión, explícitamente, una familia nueva de "
            "verdad (nunca creación libre por un supervisor)."
        ),
    )
    tracks_expiry = models.BooleanField(
        default=False,
        verbose_name="Participa en fechas/sustitución",
        help_text=(
            "H30 (S045). Qué tipos documentales tienen fecha real "
            "que extraer (caducidad o emisión) y participan en la "
            "sustitución automática (`vigencia_service."
            "evaluate_substitution()`) vive AQUÍ, como dato -- nunca "
            "como lista fija en código. Decisión explícita de Miguel "
            "Ángel (S045): un tipo documental nuevo (p. ej. DECA) se "
            "da de alta con esta casilla activada desde el propio "
            "catálogo, sin tocar ningún script. Manuales y "
            "documentos sin fecha real se quedan siempre en False."
        ),
    )
    ocr_unreliable = models.BooleanField(
        default=False,
        verbose_name="OCR poco fiable",
        help_text=(
            "H30 (S48). Cuando la lectura OCR de este tipo es "
            "estructuralmente poco fiable (verificado con datos "
            "reales -- p. ej. tarjetas ITV manuscritas con fondo de "
            "seguridad que domina la lectura de Tesseract), la "
            "contrastación de la fecha introducida por el supervisor "
            "en el panel pasa por Gemini en vez de por OCR local. "
            "Activar desde aquí, sin tocar código, cuando aparezca "
            "otro tipo con el mismo problema."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de alta",
    )
    current_template = models.ForeignKey(
        "DocumentIndexEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_template_for_types",
        verbose_name="Plantilla vigente",
        help_text=(
            "H30 (S69). Plantilla en blanco real de este tipo "
            "documental (un DocumentIndexEntry más, nunca un archivo "
            "aparte fuera del sistema). Decisión explícita de Miguel "
            "Ángel: plantilla y anotación separadas -- la entrega a "
            "una persona nunca es un documento nuevo, es una fila de "
            "DocumentAcknowledgment que apunta a este tipo. Cambiar "
            "la plantilla (nueva ley, cambio de domicilio...) es "
            "reapuntar este campo a un DocumentIndexEntry distinto; "
            "el histórico de entregas no se toca ni sabe con qué "
            "versión se hizo cada una salvo que "
            "DocumentAcknowledgment.source_entry lo guarde explícito."
        ),
    )

    class Meta:
        verbose_name = "Tipo documental"
        verbose_name_plural = "Catálogo de tipos documentales"
        ordering = ["label"]

    def __str__(self):
        return f"{self.code} ({self.label})"


class DataOperationLog(models.Model):
    """
    Audit record for a bulk, database-only operation over the index
    (H29, S040) -- Miguel Angel: "tenemos que dejar un informe (...)
    un historial de qué hemos hecho." First consumer is duplicate
    resolution (`keep-one-per-group, rest to trash`), but the model is
    generic on purpose (`operation_type`) for future bulk operations
    (batch classification, the future quarantine consumer) to log
    themselves the same way instead of each inventing its own report.

    Deliberately snapshots numbers at the moment of the operation
    (`groups_count`, `kept_count`, `trashed_count`, `bytes_recovered`)
    rather than only linking rows and recomputing on demand -- a
    later purge or restore must never silently change what a past
    report says happened.

    ---

    Registro de auditoría de una operación masiva, solo de base de
    datos, sobre el índice (H29, S040) -- Miguel Ángel: "tenemos que
    dejar un informe (...) un historial de qué hemos hecho." Primer
    consumidor es la resolución de duplicados ("quedarnos con una
    copia por grupo, el resto a la papelera"), pero el modelo es
    genérico a propósito (`operation_type`) para que futuras
    operaciones masivas (clasificación por lote, el futuro consumidor
    de la cuarentena) registren de la misma forma en vez de que cada
    una se invente su propio informe.

    Deliberadamente fotografía los números en el momento de la
    operación (`groups_count`, `kept_count`, `trashed_count`,
    `bytes_recovered`) en vez de solo enlazar filas y recalcular bajo
    demanda -- un vaciado o una restauración posteriores nunca deben
    cambiar en silencio lo que dice un informe ya pasado.
    """

    OPERATION_DUPLICATE_RESOLUTION = "DUPLICATE_RESOLUTION"
    OPERATION_BATCH_CLASSIFICATION = "BATCH_CLASSIFICATION"
    OPERATION_QUARANTINE_CONSUME = "QUARANTINE_CONSUME"
    OPERATION_REQUEUE_NO_CONFORMES = "REQUEUE_NO_CONFORMES"
    OPERATION_TRASH = "TRASH"
    OPERATION_MERGE_FOLDERS = "MERGE_FOLDERS"
    OPERATION_CHOICES = [
        (OPERATION_DUPLICATE_RESOLUTION, "Resolución de duplicados"),
        (OPERATION_BATCH_CLASSIFICATION, "Clasificación por lote"),
        (OPERATION_QUARANTINE_CONSUME, "Consumo automático de cuarentena"),
        (
            OPERATION_REQUEUE_NO_CONFORMES,
            "Reencolado manual de No Conformes",
        ),
        (OPERATION_TRASH, "Borrado en bloque a la papelera"),
        (OPERATION_MERGE_FOLDERS, "Fusión de carpetas duplicadas"),
    ]

    operation_type = models.CharField(
        max_length=40,
        choices=OPERATION_CHOICES,
        verbose_name="Tipo de operación",
    )
    STATUS_RUNNING = "RUNNING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "En curso"),
        (STATUS_COMPLETED, "Completada"),
        (STATUS_FAILED, "Interrumpida"),
    ]
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_COMPLETED,
        verbose_name="Estado",
        help_text=(
            "RUNNING para operaciones en segundo plano (Celery) "
            "mientras se procesan -- ver H29 3.28: un lote síncrono "
            "de clasificación agotó el balanceador de PythonAnywhere "
            "(504) y el registro solo se escribía al final, dejando "
            "renombrados reales sin ningún rastro en el historial. "
            "Las operaciones síncronas (resolución de duplicados) "
            "siguen creando la fila ya en COMPLETED de una vez."
        ),
    )
    performed_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="data_operation_logs",
        verbose_name="Ejecutada por",
    )
    performed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y hora",
    )
    bucket = models.CharField(
        max_length=63,
        verbose_name="Cubo",
    )
    path_prefix = models.TextField(
        blank=True,
        verbose_name="Prefijo de carpeta acotado",
        help_text="Cadena vacía si se ejecutó sobre el cubo entero.",
    )
    groups_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Grupos/archivos afectados",
        help_text=(
            "Grupos de duplicados en una resolución; archivos "
            "procesados en una clasificación por lote."
        ),
    )
    kept_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Conservadas / clasificadas con éxito",
    )
    trashed_count = models.PositiveIntegerField(
        default=0,
        verbose_name="A papelera / sin poder aplicar",
    )
    dossier_trashed_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Eliminados por ser dossier (varios documentos)",
        help_text=(
            "Solo QUARANTINE_CONSUME -- archivos con "
            "document_type_code=DESCONOCIDO que Gemini identificó "
            "con certeza como composición de varios documentos "
            "catalogados distintos (H29, S041, Miguel Ángel: "
            "\"cuando tenemos la seguridad de que es un dossier, eso "
            "hay que eliminarlo directamente\"). Distinto de "
            "trashed_count (que en esta operación significa "
            "\"clasificado, pendiente de revisión humana\") -- este "
            "campo cuenta un borrado real a la papelera del "
            "administrador, no una duda. Queda en 0 para otros tipos "
            "de operación."
        ),
    )
    bytes_recovered = models.BigIntegerField(
        default=0,
        verbose_name="Bytes recuperables",
        help_text=(
            "Solo tiene sentido en una resolución de duplicados -- "
            "tamaño total de las copias enviadas a papelera, "
            "recuperable de verdad solo cuando el administrador vacíe "
            "esas papeleras (ver DocumentIndexEntry.purged_at). Queda "
            "en 0 para otros tipos de operación."
        ),
    )

    class Meta:
        verbose_name = "Registro de operación masiva"
        verbose_name_plural = "Registros de operaciones masivas"
        ordering = ["-performed_at"]

    def __str__(self):
        return (
            f"{self.get_operation_type_display()} -- "
            f"{self.performed_at:%Y-%m-%d %H:%M}"
        )

    @property
    def bytes_recovered_display(self) -> str:
        if not self.bytes_recovered:
            return "—"
        return filesizeformat(self.bytes_recovered)

    @property
    def primary_count_label(self) -> str:
        if self.operation_type == self.OPERATION_QUARANTINE_CONSUME:
            return "Reubicadas fuera de cuarentena"
        if self.operation_type == self.OPERATION_BATCH_CLASSIFICATION:
            return "Clasificadas con éxito"
        if self.operation_type == self.OPERATION_REQUEUE_NO_CONFORMES:
            return "Reencoladas a cuarentena"
        if self.operation_type == self.OPERATION_TRASH:
            return "Enviadas a la papelera"
        return "Copias conservadas"

    @property
    def secondary_count_label(self) -> str:
        if self.operation_type == self.OPERATION_QUARANTINE_CONSUME:
            return "Enviadas a No Conformes (sin poder clasificar)"
        if self.operation_type == self.OPERATION_BATCH_CLASSIFICATION:
            return "Sin poder aplicar"
        if self.operation_type == self.OPERATION_REQUEUE_NO_CONFORMES:
            return "Sin poder reencolar"
        if self.operation_type == self.OPERATION_TRASH:
            return "Omitidas sin permiso de borrado"
        return "Copias enviadas a papelera"

    @property
    def tertiary_count_label(self) -> str | None:
        if self.operation_type == self.OPERATION_QUARANTINE_CONSUME:
            return "Eliminados por ser dossier"
        return None

    @property
    def intro_note(self) -> str:
        if self.operation_type == self.OPERATION_QUARANTINE_CONSUME:
            return (
                "Cada tarjeta es un archivo de cuarentena procesado: "
                "dominio, tipo y pistas detectadas por Gemini, y si "
                "se reubicó fuera de cuarentena o salió hacia No "
                "Conformes por no poder clasificarse en esta pasada."
            )
        if self.operation_type == self.OPERATION_BATCH_CLASSIFICATION:
            return (
                "Cada tarjeta es un archivo clasificado: dominio, "
                "tipo y pistas detectadas por Gemini."
            )
        if self.operation_type == self.OPERATION_REQUEUE_NO_CONFORMES:
            return (
                "Cada tarjeta es un archivo de No Conformes reencolado "
                "a mano de vuelta a cuarentena -- si llevaba una "
                "anotación del supervisor, queda anotado aquí."
            )
        if self.operation_type == self.OPERATION_TRASH:
            return (
                "Cada tarjeta es un archivo movido a la papelera del "
                "propio usuario que actuó -- borrado lógico, nunca "
                "definitivo, se puede restaurar desde Mi Papelera."
            )
        return (
            "Cada tarjeta es un grupo: arriba la copia que se "
            "conservó, debajo las que se enviaron a la papelera -- "
            "todas comparten el mismo tamaño y CRC32C, así se puede "
            "comprobar que de verdad son el mismo archivo."
        )


class DataOperationLogEntry(models.Model):
    """
    One line of a `DataOperationLog` -- one file, one action taken on
    it. Snapshots `bucket`/`blob_name`/`name`/`parent_path`/
    `size_bytes` at the moment of the operation rather than only
    pointing at the live `DocumentIndexEntry`, so the audit trail
    reads correctly even if the row it refers to is later purged
    (`index_entry` goes null on that path, per `on_delete=SET_NULL`)
    or its virtual name/location changes afterwards for an unrelated
    reason.

    ---

    Una línea de un `DataOperationLog` -- un archivo, una acción
    tomada sobre él. Fotografía `bucket`/`blob_name`/`name`/
    `parent_path`/`size_bytes` en el momento de la operación en vez de
    solo apuntar a la `DocumentIndexEntry` viva, así el rastro de
    auditoría se lee correctamente incluso si la fila a la que se
    refiere se vacía después (`index_entry` queda a null por ese
    camino, según `on_delete=SET_NULL`) o su ubicación/nombre virtual
    cambia después por un motivo no relacionado.
    """

    ACTION_KEPT = "KEPT"
    ACTION_TRASHED = "TRASHED"
    ACTION_CLASSIFIED = "CLASSIFIED"
    ACTION_NOT_CLASSIFIED = "NOT_CLASSIFIED"
    ACTION_RELOCATED = "RELOCATED"
    ACTION_SENT_TO_NO_CONFORMES = "SENT_NO_CONFORMES"
    ACTION_MERGED = "MERGED"
    ACTION_FOLDER_REMOVED = "FOLDER_REMOVED"
    ACTION_CHOICES = [
        (ACTION_KEPT, "Conservada"),
        (ACTION_TRASHED, "Enviada a papelera"),
        (ACTION_CLASSIFIED, "Clasificada y renombrada"),
        (ACTION_NOT_CLASSIFIED, "No se pudo aplicar"),
        (ACTION_RELOCATED, "Reubicada fuera de cuarentena"),
        (ACTION_SENT_TO_NO_CONFORMES, "Enviada a No Conformes"),
        (ACTION_MERGED, "Fusionada a carpeta destino"),
        (ACTION_FOLDER_REMOVED, "Fila de carpeta huérfana eliminada del índice"),
    ]

    log = models.ForeignKey(
        DataOperationLog,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="Operación",
    )
    group_number = models.PositiveIntegerField(
        default=0,
        verbose_name="Número de grupo",
        help_text=(
            "Correlativo dentro de esta operación (1, 2, 3...) -- las "
            "líneas que comparten número de grupo son EL MISMO grupo "
            "de duplicados: una o más 'Conservada' + cero o más "
            "'Enviada a papelera'. Sin esto, una lista plana no "
            "permite saber qué se conservó de cuál grupo (incidente "
            "real S040: Miguel Ángel no pudo correlacionar el "
            "historial con el propio Alejandro)."
        ),
    )
    action = models.CharField(
        max_length=18,
        choices=ACTION_CHOICES,
        verbose_name="Acción",
    )
    index_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operation_log_entries",
        verbose_name="Fila del índice",
    )
    bucket = models.CharField(max_length=63, verbose_name="Cubo")
    blob_name = models.TextField(verbose_name="Ruta real en el cubo")
    name = models.CharField(max_length=512, verbose_name="Nombre (virtual)")
    previous_name = models.CharField(
        max_length=512,
        blank=True,
        verbose_name="Nombre anterior (virtual)",
        help_text=(
            "Solo relevante en clasificación -- nombre virtual antes "
            "de aplicar. Vacío en resolución de duplicados (el nombre "
            "no cambia, solo la ubicación en papelera)."
        ),
    )
    parent_path = models.TextField(
        blank=True, verbose_name="Carpeta contenedora (virtual)",
    )
    size_bytes = models.BigIntegerField(
        null=True, blank=True, verbose_name="Tamaño en bytes",
    )
    crc32c = models.CharField(
        max_length=16,
        blank=True,
        verbose_name="CRC32C",
        help_text=(
            "Copiado del objeto real en el momento de la operación -- "
            "permite comprobar a simple vista que todas las líneas de "
            "un mismo grupo comparten hash y tamaño, sin tener que "
            "fiarse solo del agrupado."
        ),
    )
    detail = models.TextField(
        blank=True,
        verbose_name="Detalle",
        help_text=(
            "Texto libre según el tipo de operación -- en "
            "clasificación, tipo/dominio/confianza/razonamiento "
            "sugeridos por Gemini."
        ),
    )

    class Meta:
        verbose_name = "Línea de operación masiva"
        verbose_name_plural = "Líneas de operación masiva"
        ordering = ["group_number", "action"]
        indexes = [
            models.Index(fields=["log", "action"], name="dxoplog_log_action"),
            models.Index(
                fields=["log", "group_number"], name="dxoplog_log_group",
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()}: {self.bucket}/{self.blob_name}"


class PersonIdentity(models.Model):
    """
    DNI -> real DOC. PERSONAL folder mapping (H29, S040) -- the
    personal-domain equivalent of `fleet.MachineAsset` for machines.
    Miguel Angel, real evidence checked before designing anything:
    18 real documents of one employee, all but one carried the
    person's name and/or DNI inside the content itself -- confirming
    DNI is a safe, reliable identifier to build this on, unlike the
    filename (Hallazgo 5 of the H28 annex: the same operator's name
    spelled eight different ways).

    Seeded by classifying the `DNI`-type documents already sitting
    inside `DOC. PERSONAL` (a management command, same pattern as
    `audit_document_names`) -- never guessed, never hand-typed.

    A DNI is treated as a hard identifier, unlike a name: an exact
    match here is high-confidence enough to relocate a quarantine
    file automatically. No match (or more than one candidate) means
    "cannot resolve" -- callers must fall back to flagging for human
    review, never guess a folder from a fuzzy name match.

    ---

    Mapeo DNI -> carpeta real de DOC. PERSONAL (H29, S040) -- el
    equivalente de dominio personal a `fleet.MachineAsset` para
    máquina. Miguel Ángel, evidencia real comprobada antes de diseñar
    nada: 18 documentos reales de un mismo trabajador, todos menos
    uno llevaban el nombre y/o DNI de la persona dentro del propio
    contenido -- confirma que el DNI es un identificador fiable sobre
    el que construir esto, a diferencia del nombre de archivo
    (Hallazgo 5 del anexo H28: el nombre del mismo operario escrito de
    ocho formas distintas).

    Sembrado clasificando los documentos de tipo `DNI` que ya viven
    dentro de `DOC. PERSONAL` (un comando de gestión, mismo patrón que
    `audit_document_names`) -- nunca adivinado, nunca escrito a mano.

    Un DNI se trata como identificador duro, a diferencia de un
    nombre: una coincidencia exacta aquí es suficientemente fiable
    para reubicar un archivo de cuarentena de forma automática. Sin
    coincidencia (o más de un candidato) significa "no se puede
    resolver" -- quien llama debe caer en marcar para revisión humana,
    nunca adivinar una carpeta por parecido de nombre.
    """

    dni = models.CharField(
        max_length=16,
        unique=True,
        verbose_name="DNI/NIE",
        help_text="Normalizado: mayúsculas, sin espacios ni guiones.",
    )
    first_surname = models.CharField(
        max_length=100, verbose_name="Primer apellido",
    )
    second_surname = models.CharField(
        max_length=100, blank=True, verbose_name="Segundo apellido",
    )
    given_name = models.CharField(max_length=100, verbose_name="Nombre")
    folder_path = models.TextField(
        verbose_name="Carpeta real (virtual) dentro de DOC. PERSONAL",
    )
    source_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="DNI de origen usado para sembrar esta identidad",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de alta",
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Última actualización",
    )

    # ------------------------------------------------------------------
    # H30 (S54). Datos reales de plantilla, importados desde el Excel
    # de administración (import_worker_machine_excel). is_active_employee
    # es nullable a proposito: None significa "todavia sin cruzar contra
    # el Excel", nunca se confunde con un False real. Cierra el
    # pendiente abierto desde S043 (cruce puntual sin persistir).
    # ------------------------------------------------------------------
    is_active_employee = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Empleado activo (Excel de plantilla)",
        help_text=(
            "None = todavia no cruzado contra el Excel real de "
            "plantilla. True/False = resultado real del ultimo "
            "import_worker_machine_excel por DNI."
        ),
    )
    employer_company = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Empresa (Excel)",
        help_text=(
            "Columna EMPRESA del Excel real (p.ej. GRUAS ADOLFO "
            "ALVAREZ SL, TRANSGRUAL SL) -- que hoja/empresa real lo "
            "recoge, no una etiqueta calculada."
        ),
    )
    dni_expiry_date = models.DateField(
        null=True, blank=True, verbose_name="Caducidad DNI/NIE (Excel)",
    )
    driving_license_expiry_date = models.DateField(
        null=True, blank=True,
        verbose_name="Caducidad carnet de conducir (Excel)",
    )
    crane_operator_card_expiry_date = models.DateField(
        null=True, blank=True,
        verbose_name="Caducidad carnet de gruista (Excel)",
    )
    driver_qualification_card_expiry_date = models.DateField(
        null=True, blank=True,
        verbose_name="Caducidad tarjeta cualificación de conductor -- CAP (Excel)",
    )
    tachograph_card_expiry_date = models.DateField(
        null=True, blank=True,
        verbose_name="Caducidad tarjeta de tacógrafo (Excel)",
    )
    medical_exam_date = models.DateField(
        null=True, blank=True,
        verbose_name="Reconocimiento médico -- RM (Excel)",
    )
    ss_affiliation_number = models.CharField(
        max_length=30, blank=True,
        verbose_name="Número de afiliación SS (Excel)",
    )
    phone = models.CharField(
        max_length=30, blank=True, verbose_name="Teléfono (Excel)",
    )
    email = models.EmailField(
        max_length=150, blank=True, verbose_name="Correo electrónico (Excel)",
    )
    excel_imported_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Última importación real del Excel",
    )

    class Meta:
        verbose_name = "Identidad de personal"
        verbose_name_plural = "Identidades de personal"
        ordering = ["first_surname", "second_surname", "given_name"]

    def __str__(self):
        return (
            f"{self.dni} -- {self.first_surname} "
            f"{self.second_surname} {self.given_name}"
        )


class CompanyWorksite(models.Model):
    """
    Tercer tipo de dominio para `DocumentIndexEntry` (H30, S58), junto
    a `fleet.MachineAsset` y `PersonIdentity`. Nace de PAGO_CORRIENTE
    (declaraciones de estar al corriente de pago a la Seguridad
    Social, enviadas a la plataforma/obra) -- Miguel Angel, verbatim
    (S58): *"estos pagos al corriente van por empresa [...] es muy,
    muy, muy raro que vengan para un solo trabajador [...] van a ir de
    varias [personas] [...] esto sera algo habitual tener este tipo de
    documentacion"* -- de ahi que sea un modelo de dominio nuevo y
    generico, reutilizable por cualquier tipo documental futuro
    organizado por empresa+obra, no una tabla exclusiva de
    PAGO_CORRIENTE.

    `company`/`worksite` se guardan tal cual aparece el segmento real
    de carpeta (S58, verbatim: *"como vengan organizados, tal y como
    vengan organizados"") -- nunca normalizados a una lista cerrada de
    empresas, a diferencia de `PersonIdentity.employer_company` (esa
    si viene de una columna fija de Excel). `worksite` puede quedar en
    blanco: el propio arbol real tiene documentos de PAGO_CORRIENTE
    que viven dentro de una carpeta de empresa pero fuera de cualquier
    subcarpeta de obra (102 de 1.762 en el recuento real de S58) --
    Miguel Angel confirmo dejarlos asi, sin forzar una obra que no
    tienen.

    Un documento se vincula aqui exactamente igual que a
    `MachineAsset`/`PersonIdentity`: via
    `DocumentIndexEntry.domain_content_type`/`domain_object_id`
    (GenericForeignKey generico, sin cambios de esquema). Varios
    documentos comparten la misma fila `CompanyWorksite` cuando son de
    la misma empresa+obra -- catalogo de identidad, igual que
    `PersonIdentity` para una persona o `MachineAsset` para una
    maquina, nunca una fila por documento.
    """

    company = models.CharField(
        max_length=100,
        verbose_name="Empresa propia",
        help_text=(
            "Segmento real de carpeta tal cual aparece hoy (p. ej. "
            "'GRUAS', 'TRANSGRUAL') -- nunca normalizado a una lista "
            "cerrada."
        ),
    )
    worksite = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Obra/cliente",
        help_text=(
            "Segmento real de carpeta tal cual aparece hoy (p. ej. "
            "'OBRALIA', 'DRAGADOS'). En blanco cuando el documento "
            "real no vive dentro de ninguna subcarpeta de obra."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de alta",
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Última actualización",
    )

    class Meta:
        verbose_name = "Empresa y obra"
        verbose_name_plural = "Empresas y obras"
        ordering = ["company", "worksite"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "worksite"],
                name="unique_company_worksite",
            ),
        ]

    def __str__(self):
        return f"{self.company} -- {self.worksite}" if self.worksite else self.company


class SubjectDocumentReference(models.Model):
    """
    Referencia viva de un sujeto (`MachineAsset` o `PersonIdentity`) al
    documento vigente de un tipo dado (H30, S045). Genéricamente
    vinculada al sujeto (mismo patrón `GenericForeignKey` ya usado en
    `document_management.DocumentAlert`/`DocumentSubstitutionLog`,
    H26) -- este modelo, igual que aquellos, nunca importa `fleet` ni
    `document_explorer` importa modelos de dominio de máquina/persona
    en sentido inverso más allá de lo ya existente.

    `current_entry` es una FK directa a `DocumentIndexEntry` (por PK,
    no por ruta de texto) -- decisión explícita de H30 (hoja de ruta
    punto 4): un "mover"/"renombrar" virtual (4.12, solo
    `parent_path`/`name`) no rompe esta referencia, no hace falta
    ningún hook en `move_service`. `on_delete=SET_NULL`: un vaciado
    real de papelera por el administrador dejaría la referencia
    apuntando a nada de forma detectable (`current_entry=None`), nunca
    borrando en cascada esta fila -- la ausencia de documento vigente
    es un estado real que hay que poder consultar, no un motivo para
    que desaparezca el propio registro del tipo documental del
    sujeto.

    Sustituciones (ITV nueva reemplaza a la anterior, etc.) se
    calculan con `document_management.vigencia_service.
    evaluate_substitution()` (agnóstico, sin cambios) y se registran
    en `document_management.DocumentSubstitutionLog` (también sin
    cambios de esquema: ya es genérico, admite apuntar a filas de
    `DocumentIndexEntry` en vez de `MachineDocument` sin migración
    propia) -- quien actualiza `current_entry` aquí es el único que
    cambia con H30.

    ---

    Live reference from a subject (`MachineAsset` or `PersonIdentity`)
    to its current document of a given type (H30, S045). See Spanish
    docstring above for full design rationale.
    """

    subject_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Tipo de sujeto",
    )
    subject_object_id = models.PositiveBigIntegerField(
        verbose_name="ID del sujeto",
    )
    subject = GenericForeignKey("subject_content_type", "subject_object_id")

    document_type = models.ForeignKey(
        DocumentTypeCatalog,
        on_delete=models.PROTECT,
        related_name="subject_references",
        verbose_name="Tipo documental",
    )
    current_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subject_references",
        verbose_name="Documento vigente",
        help_text=(
            "FK directa por PK -- un mover/renombrar virtual del "
            "documento no rompe esta referencia. Nulo cuando el "
            "documento vigente se vació de papelera por el "
            "administrador, sin que eso borre esta fila."
        ),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última actualización",
    )

    class Meta:
        verbose_name = "Referencia documental de sujeto"
        verbose_name_plural = "Referencias documentales de sujetos"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "subject_content_type", "subject_object_id",
                    "document_type",
                ],
                name="unique_current_document_per_subject_and_type",
            ),
        ]
        indexes = [
            models.Index(
                fields=["subject_content_type", "subject_object_id"],
                name="sdr_subject_idx",
            ),
        ]

    def __str__(self):
        return f"{self.subject} -- {self.document_type.code}"


# ---------------------------------------------------------------------------
# EPIs -- Equipos de Proteccion Individual (H30, S047)
# ---------------------------------------------------------------------------

class EpiItemCatalog(models.Model):
    """
    Closed catalog of PPE (Personal Protective Equipment) items,
    grouped by family, mirroring the `DocumentTypeCatalog` pattern
    (S046 decision). A "new EPI" option is always reachable from the
    delivery form's own dropdown -- never requires leaving the form to
    register a new item.

    ---

    Catálogo cerrado de EPIs (Equipos de Protección Individual),
    agrupado por familia, replicando el mismo patrón de
    `DocumentTypeCatalog` (decisión S046). La opción "nuevo EPI"
    siempre es accesible desde el propio desplegable del formulario de
    entrega -- nunca hay que salir del formulario para darlo de alta.
    """

    family = models.CharField(
        max_length=100,
        verbose_name="Familia",
        help_text=(
            "Familia del EPI (p. ej. 'Protección de cabeza', "
            "'Guantes', 'Arneses y elementos de amarre')."
        ),
    )
    code = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Código",
        help_text="Código corto único del EPI en el catálogo.",
    )
    label = models.CharField(
        max_length=150,
        verbose_name="Nombre visible",
        help_text="Nombre legible mostrado en la interfaz.",
    )
    requires_periodic_review = models.BooleanField(
        default=False,
        verbose_name="Requiere revisión periódica",
        help_text=(
            "S046: EPIs con vida útil (arneses, elementos de amarre) "
            "que necesitan historial de revisiones "
            "(OPTIMAL/DETERIORATED/EXPIRED), a diferencia de los de "
            "entrega puntual."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text=(
            "Desactivar en vez de borrar conserva el histórico de "
            "entregas ya registradas con este EPI."
        ),
    )
    replacement_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coste de reposición",
        help_text=(
            "Importe de reposición del EPI, en euros. Nulo hasta tener "
            "dato real confirmado (S71/S72)."
        ),
    )
    une_en_standard = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Norma UNE-EN",
        help_text=(
            "Norma UNE-EN aplicable al EPI (p. ej. 'UNE-EN 397'). Nulo "
            "hasta tener dato real confirmado (S71/S72, motivado por "
            "ENTREGA_EPIS_GRUISTA_2026.docx)."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de alta",
    )

    class Meta:
        verbose_name = "EPI del catálogo"
        verbose_name_plural = "Catálogo de EPIs"
        ordering = ["family", "label"]

    def __str__(self):
        return f"{self.code} ({self.label})"


class EpiDelivery(models.Model):
    """
    A single PPE delivery record: which person received which EPI,
    when, and from what source (a real work-order document, or a
    direct entry through the documentation panel).

    ---

    Registro de una entrega de EPI: qué persona recibió qué EPI,
    cuándo, y de qué fuente (un parte de trabajo real, o una entrada
    directa a través del panel de documentación).
    """

    METHOD_MANUAL = "MANUAL"
    METHOD_HEURISTIC = "HEURISTIC"
    METHOD_OCR = "OCR"
    METHOD_GEMINI = "GEMINI"
    METHOD_CHOICES = [
        (METHOD_MANUAL, "Manual (panel)"),
        (METHOD_HEURISTIC, "Heurística de nombre"),
        (METHOD_OCR, "OCR"),
        (METHOD_GEMINI, "Gemini"),
    ]

    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="epi_deliveries",
        verbose_name="Persona",
    )
    epi = models.ForeignKey(
        EpiItemCatalog,
        on_delete=models.PROTECT,
        related_name="deliveries",
        verbose_name="EPI",
    )
    delivery_date = models.DateField(
        verbose_name="Fecha de entrega",
    )
    source_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="epi_deliveries",
        verbose_name="Documento de origen",
        help_text=(
            "Nulo cuando la entrega se registra directamente desde el "
            "panel, sin documento de origen (parte de trabajo)."
        ),
    )
    extraction_method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        default=METHOD_MANUAL,
        verbose_name="Método de extracción",
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Confianza",
        help_text=(
            "Nulo salvo cuando el método es OCR/Gemini o una entrada "
            "manual desde el panel que no requiere confianza."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Entrega de EPI"
        verbose_name_plural = "Entregas de EPIs"
        ordering = ["-delivery_date"]
        indexes = [
            models.Index(
                fields=["person", "epi"],
                name="epi_delivery_person_epi_idx",
            ),
        ]

    def __str__(self):
        return f"{self.person} -- {self.epi.code} ({self.delivery_date})"


class DocumentAcknowledgment(models.Model):
    """
    A single acknowledgment/delivery record: which person received or
    signed which document type (a template-based document -- a
    nomination, an authorization, an informational circular...), when,
    and from what source. Deliberately separate from `EpiDelivery`
    (H30 S69, explicit decision by Miguel Ángel): EPIs are a catalog
    of physical objects queried mostly for current possession; this
    covers document/nomination types (`DocumentTypeCatalog`) queried
    mostly by historical timeline with real gaps (delivered in 2026,
    nothing in 2027-2030, delivered again in 2031 because the person
    became site manager again) -- different catalog, different
    question shape, `EpiDelivery.requires_periodic_review` doesn't
    mean anything for a nomination. Sharing one model would blur both.

    Same underlying principle as EPIs: one canonical template per
    type (`DocumentTypeCatalog.current_template`), never a duplicated
    filled copy stored per person -- see that field's help_text.

    ---

    Registro de un reconocimiento/entrega: qué persona recibió o firmó
    qué tipo documental (un documento basado en plantilla --
    nombramiento, autorización, circular informativa...), cuándo, y de
    qué fuente. Deliberadamente separado de `EpiDelivery` (H30 S69,
    decisión explícita de Miguel Ángel): los EPIs son un catálogo de
    objetos físicos que se consulta sobre todo por posesión actual;
    esto cubre tipos documentales/nombramientos (`DocumentTypeCatalog`)
    que se consultan sobre todo por línea temporal con huecos reales
    (entregado en 2026, nada en 2027-2030, vuelve a entregarse en 2031
    porque la persona vuelve a ser jefe de obra) -- catálogo distinto,
    forma de pregunta distinta, `EpiDelivery.requires_periodic_review`
    no significa nada para un nombramiento. Meterlos en el mismo
    modelo difuminaría los dos.

    Mismo principio de fondo que los EPIs: una plantilla única y
    canónica por tipo (`DocumentTypeCatalog.current_template`), nunca
    una copia rellenada duplicada guardada por persona -- ver el
    help_text de ese campo.
    """

    METHOD_MANUAL = "MANUAL"
    METHOD_HEURISTIC = "HEURISTIC"
    METHOD_OCR = "OCR"
    METHOD_GEMINI = "GEMINI"
    METHOD_CHOICES = [
        (METHOD_MANUAL, "Manual (panel)"),
        (METHOD_HEURISTIC, "Heurística de nombre"),
        (METHOD_OCR, "OCR"),
        (METHOD_GEMINI, "Gemini"),
    ]

    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="document_acknowledgments",
        verbose_name="Persona",
    )
    document_type = models.ForeignKey(
        DocumentTypeCatalog,
        on_delete=models.PROTECT,
        related_name="acknowledgments",
        verbose_name="Tipo documental",
    )
    delivery_date = models.DateField(
        verbose_name="Fecha de entrega/firma",
    )
    source_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_acknowledgments",
        verbose_name="Documento de origen",
        help_text=(
            "Nulo por defecto -- el histórico normal no guarda copia "
            "individual (mismo principio que EPIs). Se rellena solo "
            "cuando un tipo concreto exige conservar la versión "
            "firmada exacta (p. ej. prueba legal de firma), decisión "
            "caso por caso, nunca por defecto para todos los tipos."
        ),
    )
    extraction_method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        default=METHOD_MANUAL,
        verbose_name="Método de extracción",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Reconocimiento/entrega de documento"
        verbose_name_plural = "Reconocimientos/entregas de documentos"
        ordering = ["-delivery_date"]
        indexes = [
            models.Index(
                fields=["person", "document_type"],
                name="doc_ack_person_type_idx",
            ),
        ]

    def __str__(self):
        return f"{self.person} -- {self.document_type.code} ({self.delivery_date})"


class EpiReview(models.Model):
    """
    A single periodic review of a PPE delivery that requires ongoing
    tracking of physical condition (harnesses, lanyards). Only
    meaningful for deliveries whose `epi.requires_periodic_review` is
    True.

    ---

    Una revisión periódica de una entrega de EPI que requiere
    seguimiento continuo de su estado físico (arneses, eslingas de
    amarre). Solo tiene sentido para entregas cuyo
    `epi.requires_periodic_review` sea True.
    """

    STATUS_OPTIMAL = "OPTIMAL"
    STATUS_DETERIORATED = "DETERIORATED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_OPTIMAL, "Óptimo"),
        (STATUS_DETERIORATED, "Deteriorado"),
        (STATUS_EXPIRED, "Caducado"),
    ]

    delivery = models.ForeignKey(
        EpiDelivery,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Entrega",
    )
    review_date = models.DateField(
        verbose_name="Fecha de revisión",
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        verbose_name="Estado",
    )
    source_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="epi_reviews",
        verbose_name="Documento de origen",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Revisión de EPI"
        verbose_name_plural = "Revisiones de EPIs"
        ordering = ["-review_date"]

    def __str__(self):
        return f"{self.delivery} -- {self.status} ({self.review_date})"
