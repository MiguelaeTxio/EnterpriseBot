# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/personal_documents/tasks.py
"""
Celery task for personal_documents (Hito 25) -- sibling of
machine_documents.tasks.process_machine_document_batch (H23), mismo
diseño: clasifica cada documento (sin heurística de nombre de archivo
todavía, ver personal_documents/document_classification_service.py --
YAGNI), detecta/compara un documento maestro candidato contra los
individuales del lote (ai_services.document_vision_service,
agnóstico de dominio), extrae contenido no cubierto, y sube todo a
Google Cloud Storage (spare_parts.gcs_service.upload_personal_document_file).

Dos diferencias frente a la version de machine_documents:
1. Sin clasificación heurística de nombre de archivo -- no existe
   todavía ninguna categoría que deba evitar Gemini para documentación
   de personal (a diferencia de "MANUAL" en H23).
2. Copia también validity_rule/computed_expiry_date (campos propios de
   PersonalDocument, S024) desde el resultado de classify_document(),
   que MachineDocument no tiene.

process_personal_document_batch(document_pks) es la única tarea de
este archivo. Recibe los pks de las filas PersonalDocument creadas
(status=PENDING) por la vista de subida -- esa creación es rápida
(solo guarda el archivo subido en disco, sin llamadas a Gemini/GCS),
mismo principio async que machine_documents (incidente 2026-07-14,
504 de PythonAnywhere).

Igual que en machine_documents: si company_user es nulo (documento
"sin asignar" de la ingesta automática de carpeta, S024 -- ver
PersonalDocument.Status.UNASSIGNED), el resultado de clasificación se
persiste igualmente, con status=UNASSIGNED en vez de CLASSIFIED, y se
sube a GCS bajo la subcarpeta 'SIN_ASIGNAR' (ver
spare_parts.gcs_service.upload_personal_document_file).

---

Tarea Celery de personal_documents (Hito 25) -- hermana de
machine_documents.tasks.process_machine_document_batch (H23), mismo
diseño.
"""
import logging

from celery.contrib.django.task import DjangoTask
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile

from ai_services.document_vision_service import (
    assess_master_coverage,
    extract_pages,
)
from document_management.alert_service import create_default_expiry_alerts
from document_management.models import DocumentAlert
from document_ingestion.deduplication_service import compute_content_hash
from enterprise_core.celery import app
from spare_parts.gcs_service import (
    GCSNotConfigured,
    upload_personal_document_file,
)

from .document_classification_service import classify_document
from .models import PersonalDocument

logger = logging.getLogger(__name__)


@app.task(base=DjangoTask, bind=True, max_retries=1, default_retry_delay=60)
def process_personal_document_batch(self, document_pks: list[int]) -> None:
    """
    Procesa un lote de filas PersonalDocument creadas con
    status=PENDING: clasifica cada una, detecta/compara un documento
    maestro candidato, extrae contenido no cubierto, y sube todo a
    GCS. Idempotente a nivel de documento individual (en cada
    ejecución solo se recogen las filas PENDING). Nunca deja que el
    fallo de un documento aborte el lote entero -- mismo patrón que
    machine_documents.tasks.process_machine_document_batch.
    """
    documents = list(
        PersonalDocument.objects
        .filter(pk__in=document_pks, status=PersonalDocument.Status.PENDING)
        .select_related("company_user", "company", "uploaded_by")
    )
    if not documents:
        logger.info(
            "# [process_personal_document_batch] Ningún documento "
            "PENDING encontrado para pks=%s -- nada que hacer.",
            document_pks,
        )
        return

    logger.info(
        "# [process_personal_document_batch] Iniciando lote de %d "
        "documento(s): pks=%s.",
        len(documents), document_pks,
    )

    # ------------------------------------------------------------
    # Step 1 -- classify every document individually.
    # ------------------------------------------------------------
    classified: dict[int, dict] = {}
    for document in documents:
        try:
            document.source_file.open("rb")
            file_bytes = document.source_file.read()
        except Exception as exc:
            logger.error(
                "# [process_personal_document_batch] #%d: no se pudo "
                "leer el archivo local: %s",
                document.pk, exc, exc_info=True,
            )
            document.status = PersonalDocument.Status.ERROR
            document.error_message = "No se pudo leer el archivo."
            document.save(update_fields=["status", "error_message"])
            continue
        finally:
            document.source_file.close()

        filename = document.original_filename or document.source_file.name
        result = classify_document(file_bytes, filename)

        if not result["document_type"]:
            logger.warning(
                "# [process_personal_document_batch] #%d (%s): "
                "clasificación fallida, marcado ERROR.",
                document.pk, filename,
            )
            document.status = PersonalDocument.Status.ERROR
            document.error_message = (
                "La clasificación no devolvió un tipo de documento "
                "-- ver logs de Gemini para el detalle."
            )
            document.save(update_fields=["status", "error_message"])
            continue

        document.document_type = result["document_type"]
        document.display_name = result["display_name"]
        document.expiry_date = result["expiry_date"]
        document.issue_date = result["issue_date"]
        document.validity_rule = result["validity_rule"]
        document.computed_expiry_date = result["computed_expiry_date"]
        document.document_number = result["document_number"]
        document.issuing_entity = result["issuing_entity"]
        # UNASSIGNED en vez de CLASSIFIED cuando no hay trabajador
        # enlazado (ingesta automática de carpeta, S024).
        document.status = (
            PersonalDocument.Status.CLASSIFIED
            if document.company_user_id
            else PersonalDocument.Status.UNASSIGNED
        )
        document.save(update_fields=[
            "document_type", "display_name", "expiry_date", "issue_date",
            "validity_rule", "computed_expiry_date", "document_number",
            "issuing_entity", "status",
        ])

        create_default_expiry_alerts(
            document=document,
            expiry_date=document.expiry_date or document.computed_expiry_date,
            document_label=document.display_name,
            subject_label=(
                (document.company_user.user.get_full_name()
                 or document.company_user.user.username)
                if document.company_user_id else "Sin asignar"
            ),
            company=document.company,
            default_contact=document.uploaded_by,
        )

        classified[document.pk] = {
            "document": document,
            "bytes": file_bytes,
            "filename": filename,
            "result": result,
        }

    # ------------------------------------------------------------
    # Step 2 -- master-document coverage comparison, agnóstico de
    # dominio (ai_services.document_vision_service).
    #
    # BUGFIX (S024-bis, mismo caso real reportado por Miguel Ángel y
    # corregido en machine_documents/tasks.py, ver ese docstring para
    # el detalle completo): un maestro procesado con éxito (cubierto
    # del todo o con extracción exitosa) nunca debe llegar al Paso 3
    # -- se descarta, nunca se sube a GCS ni se persiste.
    # ------------------------------------------------------------
    masters_to_discard: set[int] = set()

    for pk, item in list(classified.items()):
        if not item["result"]["is_possible_master"]:
            continue

        individuals = [
            (other["filename"], other["bytes"])
            for other_pk, other in classified.items()
            if other_pk != pk
        ]
        if not individuals:
            continue

        coverage = assess_master_coverage(
            item["bytes"], item["filename"], individuals,
        )
        if not coverage["uncovered_pages"]:
            masters_to_discard.add(pk)
            continue

        try:
            extracted_bytes = extract_pages(
                item["bytes"], coverage["uncovered_pages"],
            )
        except Exception as exc:
            logger.error(
                "# [process_personal_document_batch] #%d (%s): fallo "
                "extrayendo páginas no cubiertas %s: %s",
                pk, item["filename"], coverage["uncovered_pages"], exc,
                exc_info=True,
            )
            continue

        extracted_filename = (
            f"{item['filename']} (páginas no cubiertas).pdf"
        )
        extra_result = classify_document(extracted_bytes, extracted_filename)
        if not extra_result["document_type"]:
            logger.warning(
                "# [process_personal_document_batch] #%d (%s): "
                "extracción de páginas no cubiertas obtenida pero su "
                "clasificación falló -- se descarta.",
                pk, item["filename"],
            )
            continue

        # Segunda salvaguarda (S024-bis, mismo caso real corregido en
        # machine_documents/tasks.py -- ver ese docstring para el
        # detalle completo): si ya existe, para el MISMO trabajador,
        # un documento CLASSIFIED del mismo tipo con la misma fecha
        # efectiva de caducidad (expiry_date o, si ninguno la tiene,
        # computed_expiry_date) o la misma fecha de emisión, se
        # descarta la extracción -- el juicio de Gemini sobre
        # cobertura del maestro puede equivocarse, y el hash nunca
        # detecta este caso (la extracción genera bytes nuevos).
        company_user = item["document"].company_user
        if company_user is not None:
            extra_effective_expiry = (
                extra_result["expiry_date"] or extra_result["computed_expiry_date"]
            )
            duplicate_candidates = PersonalDocument.objects.filter(
                company_user=company_user,
                document_type=extra_result["document_type"],
                status=PersonalDocument.Status.CLASSIFIED,
            ).exclude(pk=pk)
            is_duplicate = any(
                (
                    extra_effective_expiry is not None
                    and (candidate.expiry_date or candidate.computed_expiry_date)
                    == extra_effective_expiry
                ) or (
                    extra_effective_expiry is None
                    and candidate.expiry_date is None
                    and candidate.computed_expiry_date is None
                    and extra_result["issue_date"] is not None
                    and candidate.issue_date == extra_result["issue_date"]
                )
                for candidate in duplicate_candidates
            )
            if is_duplicate:
                logger.warning(
                    "# [process_personal_document_batch] #%d (%s): "
                    "extracción descartada -- ya existe un documento "
                    "%r con la misma fecha (assess_master_coverage "
                    "marcó incorrectamente estas páginas como no "
                    "cubiertas).",
                    pk, item["filename"], extra_result["document_type"],
                )
                masters_to_discard.add(pk)
                continue

        new_document = PersonalDocument.objects.create(
            company_user=item["document"].company_user,
            company=item["document"].company,
            uploaded_by=item["document"].uploaded_by,
            document_type=extra_result["document_type"],
            display_name=extra_result["display_name"],
            source_master_hint=item["filename"],
            expiry_date=extra_result["expiry_date"],
            issue_date=extra_result["issue_date"],
            validity_rule=extra_result["validity_rule"],
            computed_expiry_date=extra_result["computed_expiry_date"],
            document_number=extra_result["document_number"],
            issuing_entity=extra_result["issuing_entity"],
            content_hash=compute_content_hash(extracted_bytes),
            status=(
                PersonalDocument.Status.CLASSIFIED
                if item["document"].company_user_id
                else PersonalDocument.Status.UNASSIGNED
            ),
            original_filename=extracted_filename,
        )
        new_document.source_file.save(
            extracted_filename, ContentFile(extracted_bytes), save=True,
        )
        create_default_expiry_alerts(
            document=new_document,
            expiry_date=(
                new_document.expiry_date or new_document.computed_expiry_date
            ),
            document_label=new_document.display_name,
            subject_label=(
                (new_document.company_user.user.get_full_name()
                 or new_document.company_user.user.username)
                if new_document.company_user_id else "Sin asignar"
            ),
            company=new_document.company,
            default_contact=new_document.uploaded_by,
        )
        logger.info(
            "# [process_personal_document_batch] Documento nuevo #%d "
            "creado a partir de páginas no cubiertas de #%d (%s).",
            new_document.pk, pk, item["filename"],
        )

        classified[new_document.pk] = {
            "document": new_document,
            "bytes": extracted_bytes,
            "filename": extracted_filename,
            "result": extra_result,
        }
        # Extracción con éxito -- el maestro se descarta, ver nota al
        # principio de este bloque.
        masters_to_discard.add(pk)

    # Descartar de verdad los maestros procesados con éxito: borrar su
    # archivo local (nunca llegó a subirse a GCS) y su fila de BD, y
    # quitarlos de `classified` para que el Paso 3 no los toque.
    for pk in masters_to_discard:
        master_item = classified.pop(pk, None)
        if master_item is None:
            continue
        master_document = master_item["document"]
        DocumentAlert.objects.filter(
            content_type=ContentType.objects.get_for_model(PersonalDocument),
            object_id=master_document.pk,
        ).delete()
        if master_document.source_file:
            master_document.source_file.delete(save=False)
        master_document.delete()
        logger.info(
            "# [process_personal_document_batch] Maestro #%d (%s) "
            "descartado -- nunca se sube a GCS ni se persiste.",
            pk, master_item["filename"],
        )

    # ------------------------------------------------------------
    # Step 3 -- upload every CLASSIFIED/UNASSIGNED document without a
    # GCS blob yet.
    # ------------------------------------------------------------
    for item in classified.values():
        document = item["document"]
        if document.status not in (
            PersonalDocument.Status.CLASSIFIED,
            PersonalDocument.Status.UNASSIGNED,
        ):
            continue
        if document.gcs_blob_name:
            continue

        try:
            blob_name = upload_personal_document_file(document)
        except GCSNotConfigured as exc:
            logger.error(
                "# [process_personal_document_batch] #%d: Google Cloud "
                "Storage no configurado -- documento NO subido, "
                "archivo local NO borrado. %s",
                document.pk, exc,
            )
            continue
        except Exception as exc:
            logger.error(
                "# [process_personal_document_batch] #%d: fallo "
                "subiendo a GCS: %s",
                document.pk, exc, exc_info=True,
            )
            continue

        document.gcs_blob_name = blob_name
        document.source_file.delete(save=False)
        document.save(update_fields=["gcs_blob_name", "source_file"])
        logger.info(
            "# [process_personal_document_batch] #%d subido a GCS "
            "(blob=%s) y archivo local eliminado.",
            document.pk, blob_name,
        )

    logger.info(
        "# [process_personal_document_batch] Lote completado: %d "
        "documento(s) procesados (incluyendo extraídos de maestro).",
        len(classified),
    )
