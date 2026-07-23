# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/models.py
"""
IngestedFile -- staging de un archivo subido en la ingesta automática
de carpeta (H23/H25, S024) ANTES de saber a qué dominio (MACHINE/
PERSONAL) ni a qué entidad concreta pertenece. La vista de subida crea
una fila por PDF (status=PENDING_ROUTING) y encola
document_ingestion.tasks.route_ingested_files; esa tarea resuelve el
dominio+entidad (entity_matching_service.classify_and_route +
match_machine_asset/match_company_user), crea el
MachineDocument/PersonalDocument correspondiente (asignado o
UNASSIGNED según haya habido coincidencia), y encola el pipeline de
clasificación completo de ese dominio
(machine_documents.tasks.process_machine_document_batch /
personal_documents.tasks.process_personal_document_batch) -- esta fila
de IngestedFile se marca ROUTED y su source_file se copia (no se
comparte) al MachineDocument/PersonalDocument nuevo, así que se puede
borrar sin perder nada una vez enrutada.

Domain-agnostic a propósito -- vive en document_ingestion, no en
machine_documents ni en personal_documents, por el mismo motivo que
entity_matching_service.py (ver ese módulo).
"""
from django.db import models

from ivr_config.models import Company, CompanyUser


class IngestedFile(models.Model):
    """
    Un archivo subido en la ingesta automática de carpeta, todavía sin
    dominio ni entidad resueltos.
    """

    class Status(models.TextChoices):
        PENDING_ROUTING = "PENDING_ROUTING", "Pendiente de enrutar"
        ROUTED = "ROUTED", "Enrutado"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Dominio no identificado -- revisar a mano"
        ERROR = "ERROR", "Error"

    class ForcedDomain(models.TextChoices):
        MACHINE = "MACHINE", "Maquinaria"
        PERSONAL = "PERSONAL", "Personal"

    forced_domain = models.CharField(
        max_length=20,
        choices=ForcedDomain.choices,
        blank=True,
        default="",
        verbose_name="Dominio elegido al subir",
        help_text=(
            "Dominio (Maquinaria/Personal) elegido explícitamente por "
            "el usuario en el formulario de subida (2026-07-23, tras "
            "un caso real: un documento de personal cuyo nombre de "
            "archivo contenía la palabra 'VARIOS' se emparejó por "
            "error contra una MachineAsset con ese mismo código). "
            "Mientras esté informado, route_ingested_files NUNCA "
            "prueba a emparejar contra el dominio contrario, sea cual "
            "sea el contenido del archivo. Vacío únicamente en filas "
            "antiguas previas a este cambio -- mantienen el "
            "comportamiento de detección automática de siempre."
        ),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="ingested_files",
        verbose_name="Empresa",
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ingested_files_uploaded",
        verbose_name="Subido por",
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre de archivo original",
    )
    source_folder_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Carpeta de origen",
        help_text="webkitRelativePath del navegador (S024-ter) -- solo "
                  "trazabilidad para el visor de subida en vivo, nunca "
                  "se usa para enrutar ni para nombrar el blob en GCS.",
    )
    upload_batch_id = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Lote de subida",
        help_text="Identificador compartido por todos los archivos de "
                  "una misma subida (S024-ter) -- permite al visor en "
                  "vivo (panel/views_documentation.py,  "
                  "UploadBatchStatusFragmentView) consultar el estado "
                  "de todo un lote sin depender del nombre de archivo.",
    )
    source_file = models.FileField(
        upload_to="document_ingestion/%Y/%m/",
        blank=True,
        verbose_name="Archivo",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Hash de contenido (SHA-256)",
        help_text="Calculado en la vista de subida (S024) -- se "
                  "propaga al MachineDocument/PersonalDocument "
                  "resultante al enrutar, sin recalcular.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_ROUTING,
        verbose_name="Estado",
    )
    error_message = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Mensaje de error",
    )
    routed_domain = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Dominio resuelto",
        help_text="MACHINE/PERSONAL/UNKNOWN (ver "
                  "document_ingestion.entity_matching_service) -- "
                  "trazabilidad, no se usa para enrutar de nuevo.",
    )
    routed_document_pk = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="PK del documento resultante",
        help_text="PK del MachineDocument/PersonalDocument creado al "
                  "enrutar (S024-ter) -- junto con routed_domain, "
                  "enlace directo para que el visor de subida en vivo "
                  "consulte el estado real de clasificación sin "
                  "adivinar por nombre de archivo. Nulo si el archivo "
                  "no llegó a enrutarse a ningún documento "
                  "(NEEDS_REVIEW/ERROR), o si el documento resultante "
                  "se borró después por ser un documento maestro "
                  "descartado (ver masters_to_discard en "
                  "machine_documents.tasks/personal_documents.tasks).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de subida",
    )

    class Meta:
        verbose_name = "Archivo en ingesta (sin enrutar)"
        verbose_name_plural = "Archivos en ingesta (sin enrutar)"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename or '(sin nombre)'} — {self.status}"


class LearnedDocumentTypeKeyword(models.Model):
    """
    Entrada del diccionario de tipos de documento APRENDIDA
    automáticamente (H23/H25, S026) -- cuando la heurística de nombre
    de archivo no reconoce el tipo de un documento y Gemini lo
    clasifica, se propone una palabra/frase candidata extraída del
    propio nombre (ver
    document_ingestion.preflight_discard_service.learn_from_classification())
    asociada al grupo canónico correspondiente al document_type que
    dio Gemini. Queda activa DE INMEDIATO -- utilizable ya dentro del
    mismo lote de subida en curso (Miguel Ángel, S026: "cuando una
    keyword nueva se propone, se usa en la propia sesión de subida"),
    sin revisión previa -- pero sí revisable/editable a mano después
    (is_active permite desactivar una entrada mala sin perder el
    histórico, ver también LearnedDocumentTypeKeywordCRUD*).

    Aprendizaje POR EMPRESA (Miguel Ángel, S026: "yo lo veo también
    mejor por empresa") -- cada company acumula su propio diccionario,
    aislado del resto.

    Agnóstico de dominio a propósito (vive en document_ingestion, no
    en machine_documents) -- personal_documents (H25) lo reutiliza tal
    cual cuando se conecte ahí, mismo principio DRY que
    entity_matching_service/IngestedFile.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="learned_document_type_keywords",
        verbose_name="Empresa",
    )
    keyword = models.CharField(
        max_length=100,
        verbose_name="Palabra clave aprendida",
        help_text="Candidata extraída del nombre de archivo tras "
                  "quitar código de máquina/matrícula, fecha y "
                  "extensión -- ver "
                  "preflight_discard_service._extract_candidate_keyword().",
    )
    canonical_group = models.CharField(
        max_length=100,
        verbose_name="Grupo canónico",
        help_text="Grupo al que se asocia esta keyword -- si el "
                  "document_type de Gemini coincidió con un grupo ya "
                  "existente (ver _OBSOLESCENCE_GROUP_KEYWORDS) se usa "
                  "ese; si no, se crea un grupo nuevo a partir del "
                  "propio document_type de Gemini, normalizado "
                  "(Miguel Ángel, S016: Gemini puede proponer "
                  "categorías libres, sin lista cerrada -- este campo "
                  "hereda esa libertad).",
    )
    source_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre de archivo de origen",
        help_text="Trazabilidad -- el nombre de archivo real que "
                  "disparó este aprendizaje la primera vez.",
    )
    source_document_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="document_type de Gemini (origen)",
        help_text="Texto tal cual lo devolvió Gemini la primera vez "
                  "-- trazabilidad, no se usa para matching (para eso "
                  "está canonical_group).",
    )
    occurrences = models.PositiveIntegerField(
        default=1,
        verbose_name="Repeticiones",
        help_text="Se incrementa cada vez que esta misma keyword "
                  "vuelve a aprenderse a partir de otro documento -- "
                  "señal de confianza para la revisión manual "
                  "posterior, nunca desactiva/activa nada por sí sola.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="False si se desactivó a mano desde el listado -- "
                  "una entrada inactiva nunca participa en la "
                  "determinación de tipo, pero se conserva para "
                  "histórico/auditoría en vez de borrarse.",
    )
    first_seen = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Primera vez vista",
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        verbose_name="Última vez vista",
    )

    class Meta:
        verbose_name = "Palabra clave de tipo de documento (aprendida)"
        verbose_name_plural = "Palabras clave de tipo de documento (aprendidas)"
        ordering = ["-last_seen"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "keyword"],
                name="unique_learned_keyword_per_company",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.keyword} → {self.canonical_group} ({self.company})"
