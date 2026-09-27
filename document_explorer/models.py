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
import calendar
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
    prorroga_de = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prorrogas",
        verbose_name="Prórroga del contrato",
        help_text=(
            "H31 (S111). Solo para la familia CONTRATO/"
            "COMUNICACION_CONTRATO: enlaza una prórroga (o una "
            "transformación a indefinido) con el contrato -- u otra "
            "prórroga -- que extiende, formando una cadena. La "
            "antigüedad real de la persona (`PersonIdentity.hire_date`) "
            "se calcula recorriendo esta cadena hasta la raíz (el "
            "contrato sin `prorroga_de`), nunca duplicada en un campo "
            "propio, para no tener dos fuentes de verdad "
            "desincronizables. Origen real: Martín González Jesús "
            "(alta real 01/11/2006, transformación a indefinido "
            "30/04/2007 -- dos fechas reales de un mismo contrato que "
            "`issue_date` por sí solo no podía distinguir)."
        ),
    )
    period_start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Inicio del periodo (prórroga)",
        help_text=(
            "H31 (S111). El 'desde' real de la prórroga que este "
            "documento comunica (\"acuerdan una prórroga... desde el "
            "X hasta el Y\") -- distinto de `issue_date`, que sigue "
            "siendo la fecha de firma/registro del propio papel, no "
            "el periodo que cubre."
        ),
    )
    period_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fin del periodo (prórroga)",
        help_text=(
            "H31 (S111). El 'hasta' real de la prórroga que este "
            "documento comunica -- ver `period_start_date`."
        ),
    )
    ocr_text = models.TextField(
        blank=True,
        verbose_name="Texto OCR cacheado",
        help_text=(
            "H30 (S78). Texto plano ya extraído por OCR/lectura "
            "nativa (Tesseract para PDF/imagen, python-docx para "
            "docx), guardado la primera vez que se procesa el "
            "documento -- para que cualquier extracción futura de "
            "campos nuevos (número de DNI, categorías de permiso, "
            "número de tarjeta...) se haga contra este texto ya "
            "guardado, sin volver a descargar de GCS ni repetir OCR. "
            "Vacío para documentos todavía no procesados por ningún "
            "barrido OCR."
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
    DOMAIN_EPI = "EPI"
    DOMAIN_CHOICES = [
        (DOMAIN_MACHINE, "Maquinaria"),
        (DOMAIN_PERSONAL, "Personal"),
        (DOMAIN_BOTH, "Ambos"),
        (DOMAIN_COMPANY, "Empresa y obra"),
        (DOMAIN_EPI, "EPI"),
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
            "Media (imagen, vídeo, audio)",
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
    skip_light_ocr_engines = models.BooleanField(
        default=False,
        verbose_name="Saltar motores OCR locales (H35, S106)",
        help_text=(
            "H35 (S106). Distinto de 'OCR poco fiable': este campo NO "
            "implica que el tipo necesite razonamiento de Gemini "
            "Vision ni descarta la fecha resuelta -- únicamente "
            "indica que una muestra real ya demostró que los motores "
            "locales (Tesseract, EasyOCR) nunca resuelven nada para "
            "este tipo, así que el barrido de "
            "extract_personal_dates_bulk_fast.py va directo a Cloud "
            "Vision, ahorrando el tiempo de los intentos locales que "
            "la evidencia real ya descartó. Activar solo tras "
            "confirmar el patrón con un dry-run real, nunca por "
            "suposición."
        ),
    )
    DATING_SCOPE_CURRENT_ONLY = "SOLO_VIGENTE"
    DATING_SCOPE_ALL_INSTANCES = "TODAS"
    DATING_SCOPE_CHOICES = [
        (
            DATING_SCOPE_CURRENT_ONLY,
            "Solo el vigente (el resto queda histórico, su fecha no importa)",
        ),
        (
            DATING_SCOPE_ALL_INSTANCES,
            "Todas las instancias (cada una es un hecho legal propio)",
        ),
    ]
    dating_scope = models.CharField(
        max_length=16,
        choices=DATING_SCOPE_CHOICES,
        default=DATING_SCOPE_ALL_INSTANCES,
        verbose_name="Alcance de fechado",
        help_text=(
            "H31 (S96). Solo relevante cuando tracks_expiry=True. "
            "Decide si, de varios documentos del mismo tipo de una "
            "misma persona, solo hace falta extraer fecha del vigente "
            "-- el resto queda histórico sin más, p. ej. DNI -- o si "
            "cada instancia es un hecho legal propio que necesita su "
            "propia fecha, p. ej. reconocimiento médico o TC2. "
            "Decisión explícita de Miguel Ángel (S96), contrastada "
            "contra normativa real donde aplicaba (LPRL art. 22 para "
            "RECONOCIMIENTO_MEDICO; RD 284/2021 para CAP/"
            "TARJETA_CUALIF_CONDUCTOR) y contra el propio código "
            "(mapeo heurístico real para CSS = Certificado de estar "
            "al corriente con la Seguridad Social, no una hoja de "
            "estilos). Antes de esta sesión esta distinción no vivía "
            "en ningún sitio del código, solo en la cabeza de Miguel "
            "Ángel -- origen de confusiones repetidas entre sesiones "
            "sobre el alcance real del fechado (ver anexo H31, "
            "registro de sesión S96, para la clasificación completa "
            "tipo a tipo)."
        ),
    )
    is_cumulative = models.BooleanField(
        default=False,
        verbose_name="Acumulable (varios vigentes a la vez)",
        help_text=(
            "H35 (S107). Distinto de dating_scope (esa decide si hace "
            "falta fecha en cada instancia; esta decide si varias "
            "instancias del mismo tipo pueden ser vigentes A LA VEZ, "
            "sin que una sustituya a la otra). False (defecto): tipo "
            "'de identidad/renovable' -- DNI, CARNET_CONDUCIR, "
            "CONTRATO, RECONOCIMIENTO_MEDICO... -- solo puede haber "
            "un documento vigente por persona, evaluate_substitution() "
            "marca el resto is_obsolete. True: tipo 'de evento "
            "repetible' -- FORMACION, ENTREGA_INFORMACION, EPIS... -- "
            "una persona puede tener varios documentos reales y "
            "vigentes a la vez (cursos distintos, entregas distintas); "
            "el backfill/sustitución automática NUNCA debe agrupar "
            "estos solo por tipo+persona sin más. Dentro de un tipo "
            "acumulable, dos instancias SÍ compiten entre sí cuando "
            "son literalmente el mismo curso/evento repetido (p. ej. "
            "una recertificación que sustituye a la anterior) -- ese "
            "emparejamiento por curso/evento concreto queda pendiente "
            "de construir (no hay campo estructurado de 'curso' todavía "
            "en DocumentIndexEntry), por eso el backfill de S107 excluye "
            "los tipos acumulables por completo en vez de adivinar. "
            "Decisión explícita de Miguel Ángel (S107): mismo campo "
            "reutilizable para las subplantillas de dosier (H31) -- "
            "una plantilla como 'Sacyr' podrá tener una subplantilla "
            "de formación donde se marquen varios tipos de curso a "
            "incluir, precisamente porque son acumulables."
        ),
    )
    parent_type = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subtypes",
        verbose_name="Tipo padre (subtipo de)",
        help_text=(
            "H30 (S120). Si se rellena, este tipo es un SUBTIPO del "
            "padre: un documento auxiliar que pertenece a él (p. ej. la "
            "autorización temporal de la DGT pertenece al permiso de "
            "conducción). En la ficha, sus documentos se pintan DENTRO "
            "de la fila del documento vigente del padre, nunca como "
            "fila propia; y como es un tipo distinto, nunca cuenta para "
            "los avisos de falta/caducidad del padre. Vacío (defecto): "
            "tipo normal. Decisión de Miguel Ángel (S120, opción 2): "
            "concepto general, reutilizable para cualquier documento "
            "auxiliar de otro tipo."
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

    content_html = models.TextField(
        blank=True,
        default="",
        verbose_name="Contenido enriquecido (circular/notificación)",
        help_text=(
            "H31 (S74). Cuerpo real de texto enriquecido (HTML básico "
            "-- color, negrita, listas) para tipos documentales que "
            "son circulares/notificaciones (p. ej. CIRCULAR_INFORMATIVA, "
            "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD). Campo NUEVO en BD, "
            "decisión explícita de Miguel Ángel (S73): mantener "
            "`current_template` (plantilla legacy en archivo) en "
            "paralelo, no sustituirlo de golpe. Vacío por defecto -- "
            "solo se rellena para los tipos que de verdad usan el "
            "CRUD de circulares de H31; el resto del catálogo (tipos "
            "físicos/documentales sin cuerpo de texto) lo deja en "
            "blanco sin más. Mismo patrón que `current_template`: "
            "campo directo en este modelo, no un modelo aparte -- no "
            "hay necesidad de versionado histórico por ahora."
        ),
    )

    is_notification_template = models.BooleanField(
        default=False,
        verbose_name="Plantilla de comunicación (circular/notificación)",
        help_text=(
            "H31 (S114). Corrección real: el CRUD de circulares "
            "(panel:circulars_list) y el selector de envío de "
            "notificación filtraban antes por `domain` "
            "(PERSONAL/BOTH/COMPANY) -- eso mostraba el catálogo "
            "ENTERO de documentos de persona (DNI, nóminas, "
            "reconocimientos médicos...), no una lista de plantillas "
            "de comunicación reutilizables. Miguel Ángel, verbatim, al "
            "ver la pantalla real: \"eso es un galimatías [...] ahí "
            "están prácticamente todos los documentos habidos y por "
            "haber. No es eso lo que queremos hacer [...] aquí vamos "
            "a tener unas 10, 15, 20 plantillas como mucho\". Este "
            "campo, no `domain`, es ahora el único criterio real: "
            "solo los tipos marcados aquí aparecen en el CRUD de "
            "circulares y en el selector de envío. Falso por defecto "
            "-- un tipo documental de persona (DNI, nómina...) nunca "
            "lo lleva a True solo por vivir en el mismo dominio que "
            "una circular real."
        ),
    )

    tags = models.ManyToManyField(
        "DocumentTag",
        blank=True,
        related_name="document_types",
        verbose_name="Etiquetas de búsqueda",
        help_text=(
            "H31 (S98). Vocabulario de búsqueda amplio y curado para "
            "este tipo -- pensado para la futura pestaña de "
            "documentación del explorador, donde un supervisor busca "
            "por concepto ('carné', 'permiso') en vez de por nombre "
            "de archivo original (que desaparece con el renombrado "
            "canónico) ni por el nombre exacto del tipo. Un mismo "
            "tipo puede llevar varias etiquetas a la vez. Vacío por "
            "defecto -- se puebla en un paso aparte, revisado por "
            "Miguel Ángel antes de aplicar, nunca en esta misma "
            "migración (ver DocumentTag para el detalle)."
        ),
    )

    class Meta:
        verbose_name = "Tipo documental"
        verbose_name_plural = "Catálogo de tipos documentales"
        ordering = ["label"]

    def __str__(self):
        return f"{self.code} ({self.label})"


class DocumentTag(models.Model):
    """
    Curated search tag for document types (H31, S98) -- deliberately
    NOT the same thing as `document_ingestion.LearnedDocumentTypeKeyword`
    (per-company vocabulary learned automatically from whatever Gemini
    proposes during classification). This is a small, hand-curated,
    project-wide taxonomy attached directly to `DocumentTypeCatalog`
    via the `tags` M2M above -- meant for the future documentation
    tab of the file explorer, where a supervisor searches by broad
    concept ("carné", "permiso") rather than by exact type name or by
    a filename that is about to disappear under the canonical rename.

    Miguel Angel's own example (S98): the same real DNI document has
    been named "DNI", "documento nacional de identidad" and "carné"
    by different people on different days -- searching by exact type
    name only ever returns one of those mental models. A tag search
    is meant to widen the net on purpose: one tag can span several
    `DocumentTypeCatalog` codes (e.g. a "PERMISO" tag covering
    `CARNET_CONDUCIR`, `PERMISO_CIRCULACION` and
    `TARJETA_CUALIF_CONDUCTOR` at once) -- the exact opposite of
    searching by type, which only ever returns that one type.

    ---

    Etiqueta de búsqueda curada para tipos documentales (H31, S98) --
    deliberadamente NO es lo mismo que
    `document_ingestion.LearnedDocumentTypeKeyword` (vocabulario por
    empresa aprendido automáticamente de lo que proponga Gemini
    durante la clasificación). Esta es una taxonomía pequeña, curada
    a mano, de todo el proyecto, colgada directamente de
    `DocumentTypeCatalog` vía el M2M `tags` de arriba -- pensada para
    la futura pestaña de documentación del explorador de archivos,
    donde un supervisor busca por concepto amplio ("carné", "permiso")
    en vez de por el nombre exacto del tipo o por un nombre de archivo
    que está a punto de desaparecer bajo el renombrado canónico.

    Ejemplo propio de Miguel Ángel (S98): un mismo DNI real ha sido
    nombrado "DNI", "documento nacional de identidad" y "carné" por
    distintas personas en distintos días -- buscar por el nombre
    exacto del tipo solo devuelve uno de esos modelos mentales. Una
    búsqueda por etiqueta está pensada para ampliar la red a
    propósito: una etiqueta puede abarcar varios códigos de
    `DocumentTypeCatalog` a la vez (p. ej. una etiqueta "PERMISO" que
    cubra `CARNET_CONDUCIR`, `PERMISO_CIRCULACION` y
    `TARJETA_CUALIF_CONDUCTOR` a la vez) -- justo lo contrario de
    buscar por tipo, que solo devuelve ese tipo concreto.
    """

    code = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Código",
        help_text=(
            "Identificador corto en mayúsculas, sin espacios ni "
            "acentos (p. ej. 'PERMISO', 'CARNET') -- mismo estilo que "
            "DocumentTypeCatalog.code, pero en un espacio de nombres "
            "propio: una etiqueta nunca coincide con un code de tipo."
        ),
    )
    label = models.CharField(
        max_length=100,
        verbose_name="Nombre visible",
        help_text="Nombre legible mostrado en el buscador del panel.",
    )

    class Meta:
        verbose_name = "Etiqueta de búsqueda"
        verbose_name_plural = "Etiquetas de búsqueda"
        ordering = ["label"]

    def __str__(self):
        return self.label


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
        (
            ACTION_FOLDER_REMOVED,
            "Fila de carpeta huérfana eliminada del índice",
        ),
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
    # ------------------------------------------------------------------
    # H30 (S82). Fecha de nacimiento -- Miguel Angel, verbatim, al dar
    # de alta a un trabajador nuevo (Estevao Veloso Sampaio): "habra
    # que anadir fecha de nacimiento en los datos, y extraerla de los
    # DNIs para el resto". Nullable a proposito: los ~79 activos ya
    # existentes no la tienen todavia -- se rellena de forma
    # incremental (alta nueva directa, o extraccion futura contra el
    # ocr_text ya cacheado de los documentos DNI, mismo patron que el
    # resto de fechas de H30) nunca retroactiva de golpe sin datos
    # reales que la respalden.
    # ------------------------------------------------------------------
    birth_date = models.DateField(
        null=True, blank=True, verbose_name="Fecha de nacimiento",
    )
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
        verbose_name=(
            "Caducidad tarjeta cualificación de conductor -- CAP (Excel)"
        ),
    )
    tachograph_card_expiry_date = models.DateField(
        null=True, blank=True,
        verbose_name="Caducidad tarjeta de tacógrafo (Excel)",
    )
    medical_exam_date = models.DateField(
        null=True, blank=True,
        verbose_name="Reconocimiento médico -- RM (Excel)",
    )
    # ------------------------------------------------------------------
    # H31 (S100, corregido S113). Número de afiliación a la Seguridad
    # Social -- Miguel Ángel, verbatim (S100): "hay datos que sí son
    # necesarios para la empresa, para el supervisor y sin embargo no
    # los ponemos ahí [...] el número de afiliación a la Seguridad
    # Social [...] lo extraemos al principio". Aparece impreso en el
    # ALTA y en el IDC ("número de afiliación"/"NSS"), y también lo
    # trae el Excel de plantilla (columna NUMERO AFILIACION SS,
    # `import_worker_machine_excel`) -- ambas fuentes escriben este
    # mismo campo, nunca dos campos separados: Miguel Ángel (S113),
    # el único dato realmente inmutable de la ficha es el DNI, así que
    # este SÍ debe quedar editable a mano sin importar de dónde vino
    # el valor la última vez ("da igual cuál coger"). Existió
    # brevemente como dos campos duplicados con el mismo nombre en el
    # cuerpo de la clase (S100 y S54) -- Python se quedaba solo con el
    # segundo (`max_length=30`, el que de verdad llegó a la BD real);
    # unificado aquí en uno solo (S113).
    # ------------------------------------------------------------------
    ss_affiliation_number = models.CharField(
        max_length=30, blank=True,
        verbose_name="Número de afiliación a la Seguridad Social",
    )
    phone = models.CharField(
        max_length=30, blank=True, verbose_name="Teléfono (Excel)",
    )
    # ------------------------------------------------------------------
    # H31 (S113). Segundo teléfono -- Miguel Ángel: "habría que añadir
    # un segundo campo para el teléfono, por si tiene teléfono en el
    # trabajo y teléfono personal." Campo de texto libre sin distinguir
    # a nivel de esquema cuál es cuál (igual que `phone`) -- quien lo
    # rellena decide qué va en cada uno.
    # ------------------------------------------------------------------
    phone_secondary = models.CharField(
        max_length=30, blank=True, verbose_name="Segundo teléfono",
    )
    email = models.EmailField(
        max_length=150, blank=True, verbose_name="Correo electrónico (Excel)",
    )
    # ------------------------------------------------------------------
    # H31 (S113). Categoría profesional -- Miguel Ángel detectó que la
    # categoría profesional que trae algún documento no siempre
    # coincide con la del contrato. Campo único de referencia de la
    # ficha, rellenado a mano -- nunca extraído automáticamente de
    # ningún documento (a diferencia de los campos "(Excel)" de
    # arriba), precisamente porque las fuentes reales discrepan entre
    # sí y decidir cuál vale es un juicio humano, no una extracción.
    # ------------------------------------------------------------------
    professional_category = models.CharField(
        max_length=150, blank=True, verbose_name="Categoría profesional",
    )
    # ------------------------------------------------------------------
    # H31 (S76). Dirección postal y fechas de alta/baja en la empresa --
    # Miguel Ángel, verbatim: "echo en falta la dirección [...] no
    # tenemos dirección, población, código postal, provincia [...] fecha
    # de alta, fecha de baja." A diferencia de los campos "(Excel)" de
    # arriba, estos NO vienen del Excel de plantilla (no existe esa
    # columna hoy) -- son editables directamente desde el panel, mismo
    # mecanismo que given_name/first_surname/second_surname/phone/email
    # (ver PersonalUpdateView.EDITABLE_FIELDS). `hire_date`/
    # `termination_date` quedan en blanco para el histórico ya
    # existente -- nunca se inventa una fecha retroactiva; se rellenan
    # a partir de ahora, tanto para altas nuevas como para bajas
    # reales que ocurran desde este punto en adelante.
    # ------------------------------------------------------------------
    address_street = models.CharField(
        max_length=200, blank=True, verbose_name="Dirección",
    )
    postal_code = models.CharField(
        max_length=10, blank=True, verbose_name="Código postal",
    )
    city = models.CharField(
        max_length=100, blank=True, verbose_name="Población",
    )
    province = models.CharField(
        max_length=100, blank=True, verbose_name="Provincia",
    )
    hire_date = models.DateField(
        null=True, blank=True, verbose_name="Fecha de alta en la empresa",
    )
    termination_date = models.DateField(
        null=True, blank=True, verbose_name="Fecha de baja en la empresa",
    )
    # ------------------------------------------------------------------
    # H31 (S109). Puesto de trabajo -- gobierna qué tipos documentales
    # se marcan como FALTANTES en la ficha (ver JobPosition arriba).
    # Nullable a propósito: sin puesto asignado, ningún tipo se marca
    # como faltante -- nunca se asume un conjunto por defecto. El
    # aviso de documento CADUCADO es independiente y no depende de
    # este campo.
    # ------------------------------------------------------------------
    job_position = models.ForeignKey(
        "document_explorer.JobPosition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="people",
        verbose_name="Requisitos de documentación",
    )
    excel_imported_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Última importación real del Excel",
    )
    company = models.ForeignKey(
        "ivr_config.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="personnel",
        verbose_name="Empresa (mensajería/IVR)",
        help_text=(
            "H31 (S74). Vínculo real a ivr_config.Company -- distinto "
            "de employer_company (texto libre tal cual viene del "
            "Excel de plantilla, con variantes como 'GRUAS ADOLFO "
            "ALVAREZ SL' / 'TRANSGRUAL SL' / 'TRANSGRUAL S.L.' para el "
            "mismo grupo). Este campo es el que usan las funciones de "
            "envío WhatsApp (whatsapp.services) para resolver "
            "WhatsAppTemplate/WhatsAppSession, que están indexados "
            "por Company, no por employer_company. Backfileado por "
            "normalización de las variantes reales conocidas a fecha "
            "de la migración 0060 -- ver ese archivo para el mapa "
            "exacto. Nulo cuando employer_company está vacío (persona "
            "aún sin cruzar contra el Excel) o cuando aparece una "
            "variante de texto nueva no cubierta todavía."
        ),
    )
    company_user = models.OneToOneField(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="person_identity",
        verbose_name="Usuario del panel vinculado",
        help_text=(
            "H31 (S74). Vínculo real a ivr_config.CompanyUser -- "
            "confirma que esta persona de plantilla es TAMBIÉN un "
            "usuario del panel (supervisor, administrador, operario "
            "de taller, etc., ver CompanyUser.role), no solo un "
            "registro de RRHH/documentación. Resuelto por cruce "
            "exacto de DNI (CompanyUser.dni == PersonIdentity.dni, "
            "mismo criterio de identificador duro que el resto del "
            "proyecto -- nunca por nombre). Verificado en producción "
            "(S74): de 25 CompanyUser reales, 11 tenían DNI relleno y "
            "los 11 cruzaron limpio, sin ambigüedad. Nulo para "
            "personal de plantilla sin cuenta de panel, o cuyo "
            "CompanyUser todavía no tiene el DNI relleno."
        ),
    )

    # ------------------------------------------------------------------
    # H35 (S105). Foto de perfil elegida entre los documentos-imagen ya
    # indexados de esta persona -- Miguel Angel: "en los documentos que
    # son imagenes hay que anadir la posibilidad de usar como foto de
    # perfil". Campo dedicado, NUNCA reutiliza el DocumentTypeCatalog
    # "IMAGEN" que ya usaba el avatar (ese mecanismo reasignaba el TIPO
    # del documento a IMAGEN, perdiendo su clasificacion real -- un DNI
    # o un carnet de gruista usado como foto dejaria de ser DNI/CARNET_
    # GRUISTA en el sistema, justo lo contrario del trabajo de todo H35).
    # Este campo no toca `document_type` del documento elegido en
    # absoluto. `PersonalDetailView` prioriza este campo sobre el
    # antiguo mecanismo IMAGEN si esta relleno (ver vista para el
    # fallback exacto).
    avatar_document = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Documento-imagen usado como foto de perfil",
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
        if self.worksite:
            return f"{self.company} -- {self.worksite}"
        return str(self.company)


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
    standard_expiry_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Vida útil estándar (años)",
        help_text=(
            "Años desde la entrega tras los cuales el EPI se "
            "considera caducado por defecto (norma EN 361/EN 365, "
            "sin fecha legal fija -- criterio de plataforma fijado "
            "por Miguel Ángel en 5 años, S73). Nulo para EPIs sin "
            "revisión periódica."
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
    destination_machine = models.ForeignKey(
        "fleet.MachineAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="epi_deliveries",
        verbose_name="Centro de gasto de destino",
        help_text=(
            "Nulo para la mayoría de EPIs (entrega personal sin CdG "
            "de destino). Relleno cuando el EPI va asignado a un "
            "Centro de Gasto además de a la persona -- p. ej. "
            "botiquines, que pueden ir a una máquina, un taller, un "
            "almacén o una plataforma (Miguel Ángel, S69/S72)."
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


class CompanyFiscalProfile(models.Model):
    """
    H31 (S113). Datos fiscales reales de una razón social del grupo
    (CIF, dirección), para el encabezado del documento de entrega de
    EPIs -- ninguno de los dos vivía antes en ningún sitio de la BBDD
    (`ivr_config.Company` es una única fila "Grupo Álvarez" para
    IVR/WhatsApp, no una por razón social real; `PersonIdentity.
    employer_company` es texto libre del Excel, sin CIF ni dirección).

    `name_aliases` (una variante de texto por línea, comparación sin
    mayúsculas/minúsculas) resuelve el mismo problema real que motivó
    `_RECIPIENT_TAX_ID_TO_COMPANY_CODE` en `spare_parts.services`
    (S004): la misma empresa aparece en varios sitios bajo variantes
    de texto libre distintas ("TRANSGRUAL SL" / "TRANSGRUAL S.L.").
    Confirmado real (S113, consulta SQL sobre `employer_company`) y
    corregido tras aclaración explícita de Miguel Ángel: 4 empresas
    reales, ninguna variante queda sin resolver -- Grúas Adolfo
    Álvarez (B29405040), Transgrual (B92493022, agrupa también
    "TRANSGRUAL Y ASITENCIA", variante de escritura ya decidida en
    S76 vía `COMPANY_FILTER_CHOICES`), Asistencia y Grúas Granada
    (B93261824) y Grualdi (B29739059, la 4ª empresa real del grupo,
    también ya reconocida en `COMPANY_FILTER_CHOICES` desde S76 --
    "esas son las empresas que hay y ya está. Ya no tenemos más
    empresas"). Dirección fiscal confirmada por Miguel Ángel para las
    tres primeras (C/ Ronda del Norte, 12, Santa Rosalía, 29591
    Málaga); Grualdi con dirección propia verificada contra registro
    mercantil público (C/ Diseminado de Cantos, 12, Málaga).

    Si `employer_company` de una persona no casa con ningún alias de
    ningún perfil, el documento de entrega se genera igualmente, sin
    encabezado de empresa (nunca se inventa un CIF ni una dirección).

    ---

    Real fiscal data (tax ID, address) of a group legal entity, for
    the EPI delivery document header -- see Spanish docstring above
    for the full real-data context (S113).
    """

    legal_name = models.CharField(
        max_length=200, verbose_name="Razón social",
    )
    tax_id = models.CharField(
        max_length=20, verbose_name="CIF",
    )
    fiscal_address = models.CharField(
        max_length=300, blank=True, verbose_name="Dirección fiscal",
    )
    name_aliases = models.TextField(
        blank=True,
        verbose_name="Variantes de texto (una por línea)",
        help_text=(
            "Formas en que PersonIdentity.employer_company puede "
            "aparecer para esta empresa real (comparación sin "
            "distinguir mayúsculas/minúsculas). Una por línea."
        ),
    )
    administrator = models.ForeignKey(
        "PersonIdentity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="administered_companies",
        verbose_name="Administrador/representante legal",
        help_text=(
            "H31 (S114). Para generar documentos programáticos "
            "(circulares con variables, p. ej. \"dar poderes a un "
            "trabajador\") que necesiten el nombre de quien firma en "
            "representación de la empresa. Confirmado contra contrato "
            "real de un trabajador de cada una de las 4 empresas "
            "(campo 'EN CONCEPTO' del modelo de contrato indefinido "
            "del SEPE) -- nunca asumido de memoria: Grúas Adolfo "
            "Álvarez y Transgrual llevan a Adolfo Álvarez Díaz como "
            "Gerente/Administrador; Grualdi y Asistencia y Grúas "
            "Granada llevan a José Luis Álvarez Díaz como Administrador/"
            "Administrador mancomunado -- Grualdi NO es Adolfo, pese a "
            "ser la suposición inicial de Miguel Ángel (\"como norma "
            "general es uno de los hermanos Álvarez Díaz [...] espera, "
            "lo suyo es leer contratos [...] e informar desde ahí\")."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil fiscal de empresa"
        verbose_name_plural = "Perfiles fiscales de empresa"
        ordering = ["legal_name"]

    def __str__(self):
        return self.legal_name


class EpiDeliveryBatchTemplate(models.Model):
    """
    H31 (S113). "Lote" de EPIs -- Miguel Ángel: el proceso real de la
    empresa entrega varios EPIs a la vez según el puesto (p. ej. "EPI
    mecánico", "EPI chóferes"), y el propio supervisor pone el nombre.
    Al usar el lote en una entrega real, el supervisor puede desmarcar
    del lote los EPIs que hoy no toca entregar -- este modelo guarda
    solo la lista completa reutilizable, nunca una entrega concreta
    (eso sigue siendo `EpiDelivery`, uno real por persona y EPI
    entregado).

    Sin FK a Company -- catálogo de toda la plataforma, mismo criterio
    que `JobPosition`/`PersonGroupTemplate`.

    ---

    An EPI "batch" -- a reusable, named set of catalog items the
    supervisor can deliver together (see Spanish docstring for full
    context, S113).
    """

    name = models.CharField(
        max_length=150, unique=True, verbose_name="Nombre del lote",
    )
    items = models.ManyToManyField(
        EpiItemCatalog,
        related_name="batch_templates",
        verbose_name="EPIs del lote",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plantilla de lote de EPIs"
        verbose_name_plural = "Plantillas de lote de EPIs"
        ordering = ["name"]

    def __str__(self):
        return self.name


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

    CHANNEL_EMAIL = "EMAIL"
    CHANNEL_WHATSAPP = "WHATSAPP"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Correo (.eml)"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
    ]
    channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_EMAIL,
        verbose_name="Canal de envío",
        help_text=(
            "Canal por el que se entregó/notificó esta circular a la "
            "persona -- EMAIL (.eml descargado, flujo original H31/S74) "
            "o WHATSAPP (plantilla circular_notification, H31/S115). "
            "Distinto de extraction_method, que describe cómo se "
            "determinó el tipo documental, no el canal de entrega."
        ),
    )
    whatsapp_read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Leída por WhatsApp (fecha/hora)",
        help_text=(
            "Nula por defecto. Se rellena cuando la persona pulsa el "
            "botón 'Leer aquí' de la plantilla circular_notification "
            "para ESTE envío concreto (channel=WHATSAPP) -- permite "
            "distinguir, entre varios envíos WhatsApp al mismo "
            "trabajador, cuál es el pendiente de confirmar lectura vía "
            "botón (el más reciente con este campo nulo)."
        ),
    )
    worksite = models.ForeignKey(
        "worksites.Worksite",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_acknowledgments",
        verbose_name="Obra",
        help_text=(
            "H31 (S115). Obra a la que se refiere esta circular concreta "
            "(p. ej. NOMBRAMIENTO_JEFE_MANIOBRAS), si aplica. Nula para "
            "circulares generales sin obra asociada."
        ),
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
        return "%s -- %s (%s)" % (
            self.person, self.document_type.code, self.delivery_date,
        )


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


class PersonalDossierTemplate(models.Model):
    """
    H31 (S103). "Plantilla" de dossier reutilizable por CUALQUIER
    supervisor o administrador de la empresa -- Miguel Ángel,
    verbatim: "selecciono 3 documentos y la plantilla guarda que
    documentos se han enviado y si ha sido en zip o en pdf [...]
    cuando se selecciona desde el gestor de plantillas se mandan
    dichos documentos con el formato que se seleccionó [...] mi
    intención era que documentos como el DNI o la tarjeta de
    conducción estén en plantillas y luego se añadan los documentos
    que son específicos de cada trabajador [...] las plantillas deben
    servir tb para cualquier supervisor y administrador".

    **CORREGIDO EN S106 -- el formato de salida YA NO vive en la
    plantilla.** Miguel Ángel, verbatim: "tenemos el zip y tenemos el
    PDF y hacemos dos plantillas [...] creo que es un error,
    solamente una plantilla [...] a la hora de usarla preguntamos:
    ¿esto cómo se va a enviar? ¿por PDF o por zip?". Tener
    `output_format` en el modelo obligaba a duplicar cada plantilla
    (una "X" en PDF, otra "X (ZIP)") solo para cubrir ambos formatos
    del mismo conjunto de tipos documentales -- exactamente el mismo
    conjunto de documentos, dos filas. El formato se pregunta ahora
    SIEMPRE en el momento de aplicar la plantilla (mismo criterio que
    ya usaba `PersonalDossierMassGenerateView` para el modo de
    agrupación -- "siempre PREGUNTADO, nunca asumido"), nunca se
    almacena por plantilla. `FORMAT_PDF`/`FORMAT_ZIP`/
    `FORMAT_CHOICES` se conservan como constantes reutilizables por
    las vistas que preguntan el formato al aplicar, pero ya no son un
    campo del modelo.

    CORREGIDO tras el diseño inicial (que ataba la plantilla a UNA
    persona -- error real, detectado por Miguel Ángel al ir a un
    segundo trabajador y no encontrar ninguna plantilla ahí): la
    plantilla vive a nivel de EMPRESA (`company`), nunca de persona --
    "DNI + tarjeta de conducción" es la misma plantilla base para
    cualquier trabajador de la empresa. Al aplicarla sobre una persona
    concreta (`PersonalDossierTemplateApplyView`), se combina con lo
    que esa persona tenga seleccionado en ese momento en sus
    casilleros -- así "documentos específicos de cada trabajador,
    como formación determinada en un área" se añaden sin tener que
    duplicar la plantilla por persona.

    DECISIÓN DE DISEÑO explícita (asunción declarada en sesión, no
    bloqueante): la plantilla guarda TIPOS documentales
    (`document_types`, M2M a DocumentTypeCatalog), nunca los IDs
    concretos de `DocumentIndexEntry` seleccionados en el momento de
    guardarla. Motivo: los documentos de una persona se renuevan
    (formación cada 3-4 años, reconocimiento médico anual, ITV...) y
    la entrada concreta seleccionada hoy quedará obsoleta mañana --
    toda la plataforma resuelve siempre "el vigente de este tipo" en
    vez de fijar una fila concreta (mismo criterio que
    `PersonalDetailView`/`_split_current_obsolete`). Aplicar una
    plantilla vuelve a resolver, en el momento de aplicarla y PARA LA
    PERSONA CONCRETA elegida, el documento VIGENTE de cada tipo
    guardado -- nunca reenvía un PDF/ZIP con documentos ya caducados
    desde que se creó la plantilla.

    Vive en `document_explorer` (no en `document_management`, que
    nunca importa modelos de dominio -- ver cabecera de ese módulo)
    porque referencia `DocumentTypeCatalog` directamente, igual que
    `EpiDelivery`/`DocumentAcknowledgment`.

    `name` nunca queda vacío: si el supervisor no escribe nombre al
    guardar, la vista le asigna "Dossier N" (N = correlativo por
    EMPRESA, ver PersonalDossierTemplateCreateView) -- editable
    después en cualquier momento ("pudiendo editar la plantilla [...]
    nombrarla").
    """

    FORMAT_PDF = "PDF"
    FORMAT_ZIP = "ZIP"
    FORMAT_CHOICES = [
        (FORMAT_PDF, "PDF único"),
        (FORMAT_ZIP, "ZIP"),
    ]

    SCOPE_PERSONAL = "PERSONAL"
    SCOPE_MACHINE = "MACHINE"
    SCOPE_CHOICES = [
        (SCOPE_PERSONAL, "Personal"),
        (SCOPE_MACHINE, "Maquinaria"),
    ]

    # H30 (S119), punto 6: plantillas de dossier también para la ficha de
    # máquina, con el mismo mecanismo que Personal. Cada ficha lista solo
    # las de su ámbito y el gestor ofrece solo los tipos de ese ámbito.
    # Las plantillas ya existentes son todas de Personal (default).
    scope = models.CharField(
        max_length=10,
        choices=SCOPE_CHOICES,
        default=SCOPE_PERSONAL,
        verbose_name="Ámbito",
        help_text=(
            "Personal o Maquinaria: en qué fichas se ofrece la "
            "plantilla y qué tipos documentales puede incluir."
        ),
    )
    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="dossier_templates",
        verbose_name="Empresa",
        help_text=(
            "Compartida por todos los supervisores/administradores de "
            "esta empresa -- nunca atada a una persona concreta."
        ),
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Nombre de la plantilla",
        help_text=(
            "Nunca vacío -- \"Dossier N\" autonumerado si el "
            "supervisor no escribe uno propio al guardar."
        ),
    )
    document_types = models.ManyToManyField(
        DocumentTypeCatalog,
        related_name="dossier_templates",
        verbose_name="Tipos documentales incluidos",
        help_text=(
            "El \"vigente\" de cada tipo se resuelve de nuevo, para la "
            "persona concreta elegida, cada vez que se aplica la "
            "plantilla -- nunca fila fija de DocumentIndexEntry."
        ),
    )
    # ------------------------------------------------------------------
    # H31/H36 (S109). EPIs a incluir como sección propia del dossier --
    # deliberadamente separado de `document_types` porque una entrega
    # de EPI vive en `EpiDelivery` (registro estructurado: persona,
    # EPI, fecha), nunca en `DocumentIndexEntry` -- son dos fuentes de
    # datos reales distintas. Al aplicar la plantilla se resuelven TODAS
    # las entregas reales de cada EPI marcado aquí para la persona
    # concreta (`_resolve_template_epi_deliveries`), igual criterio de
    # "resolver en el momento de aplicar" que `document_types`.
    #
    # SIN FIRMA TODAVIA (decision explicita de Miguel Angel, S109): la
    # seccion de EPIs del dossier se genera sin ningun bloque de firma
    # -- el pipeline de firma electronica cualificada (proveedor
    # externo homologado eIDAS, a elegir) esta en fase de eleccion de
    # proveedor, fuera del alcance de este campo. Anadir la firma real
    # es tarea aparte, sobre esta misma seccion, cuando el proveedor
    # este integrado.
    # ------------------------------------------------------------------
    epi_items = models.ManyToManyField(
        EpiItemCatalog,
        blank=True,
        related_name="dossier_templates",
        verbose_name="EPIs incluidos",
        help_text=(
            "Se resuelven las entregas reales (EpiDelivery) de cada "
            "EPI marcado, para la persona concreta, en el momento de "
            "aplicar la plantilla -- sin firma electrónica todavía "
            "(pendiente de elegir proveedor homologado eIDAS)."
        ),
    )
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_dossier_templates",
        verbose_name="Creada por",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Plantilla activa",
        help_text=(
            "S106. Marca cuál es la plantilla que el supervisor tiene "
            "seleccionada ahora mismo para previsualizar y usar, "
            "dentro del gestor de plantillas -- Miguel Ángel, "
            "verbatim: 'no hay forma de decir: esta plantilla es la "
            "que quiero usar y voy a previsualizar'. Solo una activa "
            "por empresa a la vez -- "
            "PersonalDossierTemplateSetActiveView desmarca las demás "
            "de la misma empresa al marcar una nueva."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última edición",
    )

    class Meta:
        verbose_name = "Plantilla de dossier"
        verbose_name_plural = "Plantillas de dossier"
        ordering = ["company_id", "created_at"]

    def __str__(self):
        return f"{self.name} ({self.company})"


class PersonGroupTemplate(models.Model):
    """
    H31 (S109). "Grupo de reparto" -- conjunto guardado de personas,
    reutilizable en cualquier accion masiva sobre Personal (entrega de
    EPI, notificacion/circular, generacion de dosieres) sin tener que
    volver a marcar el mismo casillero cada vez. Miguel Angel,
    verbatim: "normalmente se excluyen ciertas personas [...] marco
    Transgrual, me van a salir listados todos los trabajadores de
    Transgrual y ahora marco, por ejemplo, los que son gruistas [...]
    puedo mezclar dos empresas, porque a lo mejor le voy a dar a todos
    los choferes de todas las empresas un chaleco de alta
    visibilidad".

    Deliberadamente SIN FK a Company (a diferencia de
    PersonalDossierTemplate) -- el propio caso de uso que lo motiva es
    mezclar personas de varias empresas reales en un mismo grupo (el
    ejemplo de los choferes/chalecos de arriba). El filtro por empresa
    para construir el grupo sigue existiendo en el listado de Personal
    tal cual ya funciona hoy -- este modelo solo persiste el resultado
    final de la seleccion, cruzando empresas si el propio supervisor
    lo decide asi.

    Se guarda desde el frontend a partir del Set `selection` ya
    existente en `_personal_pane.html` (acumulado en cliente entre
    filtros/paginas dentro de la misma sesion de navegador) -- este
    modelo es exclusivamente lo que anade PERSISTENCIA CON NOMBRE mas
    alla de esa sesion, para reutilizarlo en dias distintos y en
    cualquiera de las acciones masivas.
    """

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre del grupo",
    )
    members = models.ManyToManyField(
        "document_explorer.PersonIdentity",
        related_name="group_templates",
        verbose_name="Personas incluidas",
    )
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_person_groups",
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última edición",
    )

    class Meta:
        verbose_name = "Grupo de reparto"
        verbose_name_plural = "Grupos de reparto"
        ordering = ["name"]

    def __str__(self):
        return self.name


class JobPosition(models.Model):
    """
    H31 (S109). Catálogo de "Requisitos de documentación" -- Gruista,
    Administrativo, Con tacógrafo, Sin tacógrafo... Cada requisito
    guarda qué tipos documentales son OBLIGATORIOS para quien lo tenga
    asignado, con la misma mecánica que `PersonalDossierTemplate`
    (marcado de tipos agrupados por familia) -- Miguel Ángel,
    verbatim: "esto deberíamos de hacerlo igual que estamos haciendo
    la gestión de los dosieres [...] igual que estamos marcando para
    crear una plantilla de dosier, pues deberíamos de marcar para
    crear una plantilla de puesto".

    Origen del hito: el triángulo de alerta por "documento que falta"
    (H31, S109, punto 3) marcaba como faltante CUALQUIER tipo del
    catálogo (70-80 tipos) que la persona no tuviera -- avisaba, por
    ejemplo, de un curso de carretilla elevadora a un administrativo,
    que nunca lo va a necesitar. Miguel Ángel, verbatim: "no es
    cuestión de marcar cuando falte uno de los 70 u 80 tipos [...]
    sino de los documentos que realmente son necesarios [...]
    dependiendo del tipo de puesto que cada trabajador desempeña".

    IMPORTANTE -- alcance de este modelo, CORREGIDO EN S119: al crear
    este modelo (S109) se decidió que el aviso de "documento CADUCADO"
    (`attention_types_by_family`/`has_alert`) fuera independiente del
    puesto -- se aplicaba a cualquier documento con caducidad real ya
    pasada, tuviera o no puesto asignado. Miguel Ángel revirtió esa
    decisión en S119, verbatim: "avisamos a una persona que es
    administrativa [...] de que tiene cumplido el carnet de conducir
    o el CAP [...] tenemos grupos hechos de requisitos documentales
    para avisar de unos requisitos de documentación. Tenemos que
    ceñirnos a eso." Desde S119, TANTO el aviso de faltante COMO el de
    caducado salen únicamente de `required_document_types` -- ver
    `document_explorer.required_documentation_service`, única fuente
    para los dos.

    RENOMBRADO DE CARA AL USUARIO EN S113 (nunca la clase ni el campo
    en código, solo verbose_name/textos de interfaz): Miguel Ángel,
    tras confundir este modelo con la entrega de EPIs -- "el nombre
    tiene a confusión, porque en el puesto lo que tenemos es [...] la
    documentación obligatoria por puestos [...] habría que darle otro
    nombre". Ahora se presenta como "Requisitos de documentación" en
    toda la interfaz -- el modelo, el campo FK y las vistas siguen
    llamándose JobPosition/job_position internamente, sin ningún
    cambio de esquema ni de URL, solo de rótulo visible.

    AMPLIADO EN S119 -- CATÁLOGO ÚNICO, GLOBAL, NUNCA POR DOMINIO:
    primer intento real de la propia sesión, corregido por Miguel
    Ángel antes de desplegarse con datos: se creó un modelo APARTE
    (`MachineDocumentRequirement`) para máquinas, con su propio
    selector de tipos filtrado a MACHINE/BOTH. Miguel Ángel, verbatim:
    "los requisitos documentales no son ni para personas ni para
    máquinas [...] la gestión de requisitos documentales es global
    [...] cogemos de todos los documentos, cogemos los que queremos y
    fabricamos un requisito documental [...] ese requisito se asigna a
    una máquina, a una dependencia o a una persona [...] no tenemos
    que tener un arreglo para máquinas y un arreglo para personas."
    Por eso el selector de tipos de `JobPositionManageView` ofrece TODO
    el catálogo activo, sin filtrar por dominio -- la pertinencia de
    cada tipo para un requisito concreto la decide quien lo crea y
    quien lo asigna, nunca una restricción de código. Un requisito
    pensado para personas asignado por error a una máquina simplemente
    generará avisos de documentos faltantes que no le corresponden --
    esa señal, visible en la propia ficha, es la que delata el error y
    lleva a corregir la asignación, sin necesidad de ninguna
    validación que lo impida de antemano.

    `PersonIdentity.job_position` y `MachineAsset.document_requirement`
    (los dos FK, nullable) son la persona o la máquina relacionada con
    el requisito -- sin ninguno asignado, ningún tipo se marca como
    faltante ni como caducado (nunca se asume un conjunto por defecto
    sin que Miguel Ángel lo haya definido explícitamente). El catálogo
    de requisitos es deliberadamente abierto y editable -- "que eso se
    pueda seguir perfilando en el futuro" -- nunca una lista cerrada
    fija en código.
    """

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nombre",
    )
    required_document_types = models.ManyToManyField(
        DocumentTypeCatalog,
        blank=True,
        related_name="job_positions",
        verbose_name="Documentos obligatorios para este requisito",
        help_text=(
            "S119: gobierna los dos avisos -- documento FALTANTE y "
            "documento CADUCADO -- tanto en la ficha de personal como "
            "en la de máquina. Catálogo completo, sin restricción de "
            "dominio: la pertinencia de cada tipo la decide quien "
            "crea y quien asigna el requisito, nunca el código."
        ),
    )
    required_driving_categories = models.ManyToManyField(
        "DrivingLicenceCategory",
        blank=True,
        related_name="job_positions",
        verbose_name="Clases de permiso de conducción exigidas",
        help_text=(
            "H30 (S120). Clases concretas del carné (B, C, CE...) que "
            "exige este requisito. Cada una se comprueba contra la "
            "matriz del carné vigente del sujeto: si no la tiene, "
            "falta; si su fecha ya pasó, caducada."
        ),
    )
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_job_positions",
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última edición",
    )

    class Meta:
        verbose_name = "Requisito de documentación"
        verbose_name_plural = "Requisitos de documentación"
        ordering = ["name"]

    def __str__(self):
        return self.name




class DrivingLicenceCategory(models.Model):
    """
    H30 (S120). Closed catalogue of Spanish driving licence classes
    (art. 4.2 RGC, RD 818/2009 as amended by RD 971/2020).
    ---
    H30 (S120). Catálogo cerrado de las 14 clases vigentes de permiso
    de conducción en España (art. 4.2 del Reglamento General de
    Conductores, redacción vigente tras el RD 971/2020): AM, A1, A2, A,
    B, BE, C1, C1E, C, CE, D1, D1E, D y DE. Sembrado por migración
    (0147) -- datos en base de datos, nunca una lista en el código.

    Confirmado por Miguel Ángel en S120, punto 1 de la hoja de ruta:
    (1) estas 14 clases son el catálogo completo; (2) los códigos 96 y
    97 NO son clases, se guardan como códigos de su clase en
    `DrivingLicenceGrant.codes`; (3) las clases del modelo de carné
    anterior al RD 772/1997 (B1, B2, C1 hasta 16 t, C2, E) se
    traducen a su clase actual equivalente al recolectar (DT 1ª del
    RGC), nunca se guardan como clases propias. BTP ya no existe
    (suprimido por el RD 1055/2015).
    """

    code = models.CharField(
        max_length=4,
        unique=True,
        verbose_name="Clase",
    )
    label = models.CharField(
        max_length=120,
        verbose_name="Vehículos que autoriza",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
    )

    class Meta:
        verbose_name = "Clase de permiso de conducción"
        verbose_name_plural = "Clases de permiso de conducción"
        ordering = ["display_order"]

    def __str__(self):
        return self.code


class DrivingLicenceGrant(models.Model):
    """
    H30 (S120). One class printed on one driving licence card: the
    matrix rows of columns 9-12 of the card's reverse side.
    ---
    H30 (S120). Una clase impresa en UN carné de conducir concreto --
    una fila de la matriz del reverso del carné: columna 9 (clase),
    10 (fecha de primera expedición de esa clase), 11 (fecha de
    caducidad de esa clase) y 12 (códigos armonizados, p. ej. 96 o
    97). Cuelga del `DocumentIndexEntry` del carné (tipo
    `CARNET_CONDUCIR`), no de la persona: al subir un carné renovado,
    sus clases cuelgan del documento nuevo y la vigencia se lee
    siempre del carné más reciente, nunca mezclando carnés.

    Origen -- caso real `id=27899` (Alberto Javier Álvarez Díaz): el
    carné guardaba una única `expiry_date` (la de las clases de
    camión, 2023) mientras la clase B que exige su puesto caduca en
    2028. Miguel Ángel, verbatim (S119): "esto en realidad es una
    matriz."
    """

    entry = models.ForeignKey(
        DocumentIndexEntry,
        on_delete=models.CASCADE,
        related_name="driving_licence_grants",
        verbose_name="Carné de conducir",
    )
    category = models.ForeignKey(
        DrivingLicenceCategory,
        on_delete=models.PROTECT,
        related_name="grants",
        verbose_name="Clase",
    )
    first_issue_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Primera expedición (columna 10)",
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Caducidad (columna 11)",
    )
    codes = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Códigos (columna 12)",
        help_text="Códigos armonizados tal cual el carné, p. ej. 96 o 97.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última edición",
    )

    class Meta:
        verbose_name = "Clase de un carné de conducir"
        verbose_name_plural = "Clases de carnés de conducir"
        ordering = ["entry", "category__display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=("entry", "category"),
                name="unique_driving_grant_per_card_and_category",
            ),
        ]

    def __str__(self):
        return "%s (%s)" % (self.category.code, self.entry_id)


# H30 (S121) -- accesorios de elevación (eslingas, líneas de carga,
# grilletes...): equivalente de los EPIs para la maquinaria.
LIFTING_ACCESSORY_REVIEW_MONTHS = 12


def add_months(value, months):
    """
    Return `value` shifted by `months` calendar months, clamping the day
    to the last day of the target month (31/01 + 1 month -> 28/02).
    ---
    Devuelve `value` desplazada `months` meses naturales, ajustando el
    día al último del mes de destino (31/01 + 1 mes -> 28/02).
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class LiftingAccessoryType(models.Model):
    """
    H30 (S121). Editable catalogue of lifting accessory types.
    ---
    H30 (S121). Catálogo de tipos de accesorio de elevación, editable
    desde el panel (alta, edición y baja) -- decisión 2 de Miguel Ángel
    en S121: "siempre que podamos añadir/quitar/editar". Sembrado por
    migración con los 6 tipos iniciales; datos en base de datos, nunca
    una lista en el código. "Quitar" es desactivar (`is_active=False`)
    cuando el tipo ya tiene accesorios, para conservar su histórico
    (mismo criterio que `EpiItemCatalog.is_active`).
    """

    code = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Código",
        help_text="Código corto único del tipo de accesorio.",
    )
    label = models.CharField(
        max_length=150,
        verbose_name="Nombre visible",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text=(
            "Desactivar en vez de borrar conserva los accesorios ya "
            "registrados con este tipo."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de alta",
    )

    class Meta:
        verbose_name = "Tipo de accesorio de elevación"
        verbose_name_plural = "Tipos de accesorio de elevación"
        ordering = ["display_order", "label"]

    def __str__(self):
        return self.label


class LiftingAccessory(models.Model):
    """
    H30 (S121). One physical lifting accessory (a sling, a load line, a
    shackle...), identified by its certificate or serial number.
    ---
    H30 (S121). Un accesorio de elevación físico (una eslinga, una
    línea de carga, un grillete...), identificado por su nº de
    certificado o de serie -- decisión 1 de Miguel Ángel en S121: una
    ficha por accesorio. Los datos salen del certificado del fabricante
    (Bezabala, Polymax, Deij...): descripción, medidas, carga de
    trabajo, norma, fabricante y fecha de suministro. A quién y a qué
    máquina se entrega vive en `LiftingAccessoryAssignment` (con
    historial); sus revisiones periódicas, en `LiftingAccessoryReview`.

    Sus certificados, igual que la ficha técnica de un EPI (decisión de
    Miguel Ángel, S121): documentos `CERT_ACCESORIO_ELEVACION` vinculados
    por el mecanismo genérico de siempre (`DocumentIndexEntry.
    domain_content_type`/`domain_object_id` apuntando a este accesorio),
    nunca una FK propia -- mismo error que se corrigió en S76 con
    `EpiItemCatalog.technical_sheet`. Admite varios por accesorio.
    """

    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="lifting_accessories",
        verbose_name="Empresa",
    )
    accessory_type = models.ForeignKey(
        LiftingAccessoryType,
        on_delete=models.PROTECT,
        related_name="accessories",
        verbose_name="Tipo",
    )
    identifier = models.CharField(
        max_length=100,
        verbose_name="Nº de certificado / serie",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Descripción",
    )
    dimensions = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Medidas",
        help_text="Tal cual el certificado, p. ej. '26 mm x 6 m'.",
    )
    working_load_kg = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Carga de trabajo (kg)",
    )
    standard = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Norma",
        help_text="P. ej. 'EN 13414-1' o 'EN 1492-1'.",
    )
    manufacturer = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Fabricante / proveedor",
    )
    supply_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de suministro",
        help_text=(
            "Fecha del certificado del fabricante. Sin ninguna revisión "
            "registrada, la vigencia se cuenta desde aquí."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="En servicio",
        help_text="Desmarcar al retirar el accesorio; nunca se borra.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de alta",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última edición",
    )

    class Meta:
        verbose_name = "Accesorio de elevación"
        verbose_name_plural = "Accesorios de elevación"
        ordering = ["accessory_type__display_order", "identifier"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "accessory_type", "identifier"),
                name="unique_lifting_accessory_per_company_type",
            ),
        ]

    def __str__(self):
        return "%s %s" % (self.accessory_type.label, self.identifier)

    def current_assignment(self):
        """
        Return the open assignment (no return date), or None.
        ---
        Devuelve la entrega abierta (sin fecha de devolución), o None.
        """
        return self.assignments.filter(end_date__isnull=True).order_by(
            "-start_date", "-id",
        ).first()

    def latest_review(self):
        """
        Return the most recent review, or None.
        ---
        Devuelve la revisión más reciente, o None.
        """
        return self.reviews.order_by("-review_date", "-id").first()

    def expiry_date(self):
        """
        Effective expiry: the latest review's, or supply date + 12 months.
        ---
        Caducidad efectiva: la de la revisión más reciente; sin
        revisiones, fecha de suministro + 12 meses; sin ninguna de las
        dos, None.
        """
        review = self.latest_review()
        if review is not None:
            return review.expiry_date
        if self.supply_date:
            return add_months(
                self.supply_date, LIFTING_ACCESSORY_REVIEW_MONTHS,
            )
        return None


class LiftingAccessoryAssignment(models.Model):
    """
    H30 (S121). Delivery of a lifting accessory to a responsible person
    and, optionally, a machine -- one row per delivery, with history.
    ---
    H30 (S121). Entrega de un accesorio de elevación -- decisión 3 de
    Miguel Ángel en S121: máquina opcional, con historial, y "hay que
    añadir la persona a quien se le entrega, que es la responsable del
    elemento". Una fila por entrega; la vigente es la que no tiene
    `end_date`. Una entrega nueva cierra la anterior (servicio
    `lifting_accessory_service.assign_accessory`) -- nunca se sobrescribe,
    para conservar el historial.
    """

    accessory = models.ForeignKey(
        LiftingAccessory,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Accesorio",
    )
    responsible_person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.PROTECT,
        related_name="lifting_accessory_assignments",
        verbose_name="Responsable",
        help_text="Persona a quien se entrega y responde del accesorio.",
    )
    machine = models.ForeignKey(
        "fleet.MachineAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lifting_accessory_assignments",
        verbose_name="Máquina",
    )
    start_date = models.DateField(
        verbose_name="Fecha de entrega",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de devolución",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Observaciones",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Entrega de accesorio de elevación"
        verbose_name_plural = "Entregas de accesorios de elevación"
        ordering = ["-start_date", "-id"]

    def __str__(self):
        return "%s -> %s (%s)" % (
            self.accessory, self.responsible_person, self.start_date,
        )


class LiftingAccessoryReview(models.Model):
    """
    H30 (S121). One periodic review of one lifting accessory.
    ---
    H30 (S121). Una revisión periódica de un accesorio de elevación --
    decisión 4 de Miguel Ángel en S121: la revisión cuelga de cada
    accesorio. Vigencia (decisión 5): fecha de revisión + 12 meses,
    salvo que el supervisor indique una caducidad explícita, que
    prevalece.
    """

    accessory = models.ForeignKey(
        LiftingAccessory,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Accesorio",
    )
    review_date = models.DateField(
        verbose_name="Fecha de revisión",
    )
    explicit_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Caducidad indicada",
        help_text=(
            "Solo si el supervisor la indica: prevalece sobre la fecha "
            "de revisión + 12 meses."
        ),
    )
    source_entry = models.ForeignKey(
        DocumentIndexEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lifting_accessory_reviews",
        verbose_name="Documento de la revisión",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Revisión de accesorio de elevación"
        verbose_name_plural = "Revisiones de accesorios de elevación"
        ordering = ["-review_date", "-id"]

    def __str__(self):
        return "%s (%s)" % (self.accessory, self.review_date)

    @property
    def expiry_date(self):
        """
        Explicit expiry if given, otherwise review date + 12 months.
        ---
        Caducidad indicada si la hay; si no, revisión + 12 meses.
        """
        if self.explicit_expiry_date:
            return self.explicit_expiry_date
        return add_months(self.review_date, LIFTING_ACCESSORY_REVIEW_MONTHS)
