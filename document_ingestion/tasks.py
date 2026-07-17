# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/tasks.py
"""
Tarea Celery de enrutado (H23/H25, S024) -- primer eslabón de la
ingesta automática de carpeta. Recibe los pks de IngestedFile creados
(status=PENDING_ROUTING) por la vista de subida en lote y, para cada
uno:

1. Llama a entity_matching_service.classify_and_route() (llamada
   Gemini barata de enrutado -- ver ese módulo).
2. Según el dominio devuelto, intenta emparejar contra un
   MachineAsset (match_machine_asset) o un CompanyUser
   (match_company_user) real de la empresa.
3. Crea el MachineDocument/PersonalDocument correspondiente
   (status=PENDING; machine_asset/company_user asignado si hubo
   coincidencia, nulo si no -- el pipeline de cada dominio decide
   CLASSIFIED vs UNASSIGNED al terminar de clasificar, ver
   machine_documents.tasks/personal_documents.tasks).
4. Si el dominio es UNKNOWN (o falla el enrutado), la fila
   IngestedFile se marca NEEDS_REVIEW en vez de convertirse en
   documento de ningún dominio -- alguien tiene que decidir a mano de
   qué se trata.

Al terminar de enrutar todo el lote, encola UNA tarea de cada dominio
afectado (process_machine_document_batch/process_personal_document_batch)
con todos los pks nuevos de ese dominio -- mismo principio de lote que
ya usan esas dos tareas, no una tarea por documento.

Diseño de dos llamadas por documento (enrutado aquí + clasificación
completa en el pipeline de cada dominio) documentado en
entity_matching_service.py -- no se repite aquí.
"""
import logging

from celery.contrib.django.task import DjangoTask
from django.core.files.base import ContentFile

from enterprise_core.celery import app
from machine_documents.models import MachineDocument
from machine_documents.tasks import process_machine_document_batch
from personal_documents.models import PersonalDocument
from personal_documents.tasks import process_personal_document_batch

from .entity_matching_service import (
    DOMAIN_MACHINE,
    DOMAIN_PERSONAL,
    classify_and_route,
    match_company_user,
    match_machine_asset,
)
from .models import IngestedFile

logger = logging.getLogger(__name__)


@app.task(base=DjangoTask, bind=True, max_retries=1, default_retry_delay=60)
def route_ingested_files(self, ingested_file_pks: list[int]) -> None:
    """
    Enruta un lote de IngestedFile PENDING_ROUTING a MachineDocument o
    PersonalDocument (o los deja NEEDS_REVIEW si no se identifica el
    dominio), y encola el pipeline de clasificación completo de cada
    dominio afectado. Nunca deja que el fallo de un archivo aborte el
    lote entero -- mismo patrón que los pipelines de dominio.
    """
    ingested_files = list(
        IngestedFile.objects
        .filter(
            pk__in=ingested_file_pks,
            status=IngestedFile.Status.PENDING_ROUTING,
        )
        .select_related("company", "uploaded_by")
    )
    if not ingested_files:
        logger.info(
            "# [route_ingested_files] Ningún archivo PENDING_ROUTING "
            "encontrado para pks=%s -- nada que hacer.",
            ingested_file_pks,
        )
        return

    logger.info(
        "# [route_ingested_files] Enrutando lote de %d archivo(s): "
        "pks=%s.",
        len(ingested_files), ingested_file_pks,
    )

    new_machine_pks: list[int] = []
    new_personal_pks: list[int] = []

    for ingested in ingested_files:
        try:
            ingested.source_file.open("rb")
            file_bytes = ingested.source_file.read()
        except Exception as exc:
            logger.error(
                "# [route_ingested_files] #%d: no se pudo leer el "
                "archivo local: %s",
                ingested.pk, exc, exc_info=True,
            )
            ingested.status = IngestedFile.Status.ERROR
            ingested.error_message = "No se pudo leer el archivo."
            ingested.save(update_fields=["status", "error_message"])
            continue
        finally:
            ingested.source_file.close()

        filename = ingested.original_filename or ingested.source_file.name
        route = classify_and_route(file_bytes, filename)
        company = ingested.company

        if route["domain"] == DOMAIN_MACHINE:
            matched_machine = (
                match_machine_asset(
                    company, route["machine_reference_hint"],
                )
                if route["is_confident"] else None
            )
            new_document = MachineDocument(
                machine_asset=matched_machine,
                company=company,
                uploaded_by=ingested.uploaded_by,
                original_filename=filename,
                status=MachineDocument.Status.PENDING,
                detected_reference_hint=(
                    "" if matched_machine
                    else route["machine_reference_hint"]
                ),
            )
            new_document.source_file.save(
                filename, ContentFile(file_bytes), save=False,
            )
            new_document.save()
            new_machine_pks.append(new_document.pk)

            ingested.status = IngestedFile.Status.ROUTED
            ingested.routed_domain = DOMAIN_MACHINE
            ingested.source_file.delete(save=False)
            ingested.save(update_fields=[
                "status", "routed_domain", "source_file",
            ])
            logger.info(
                "# [route_ingested_files] #%d (%s) -> MACHINE "
                "(MachineDocument #%d, %s).",
                ingested.pk, filename, new_document.pk,
                "asignado" if matched_machine else "SIN ASIGNAR",
            )

        elif route["domain"] == DOMAIN_PERSONAL:
            matched_worker = (
                match_company_user(company, route["worker_dni_hint"])
                if route["is_confident"] else None
            )
            new_document = PersonalDocument(
                company_user=matched_worker,
                company=company,
                uploaded_by=ingested.uploaded_by,
                original_filename=filename,
                status=PersonalDocument.Status.PENDING,
                detected_dni_hint=(
                    "" if matched_worker else route["worker_dni_hint"]
                ),
            )
            new_document.source_file.save(
                filename, ContentFile(file_bytes), save=False,
            )
            new_document.save()
            new_personal_pks.append(new_document.pk)

            ingested.status = IngestedFile.Status.ROUTED
            ingested.routed_domain = DOMAIN_PERSONAL
            ingested.source_file.delete(save=False)
            ingested.save(update_fields=[
                "status", "routed_domain", "source_file",
            ])
            logger.info(
                "# [route_ingested_files] #%d (%s) -> PERSONAL "
                "(PersonalDocument #%d, %s).",
                ingested.pk, filename, new_document.pk,
                "asignado" if matched_worker else "SIN ASIGNAR",
            )

        else:
            ingested.status = IngestedFile.Status.NEEDS_REVIEW
            ingested.routed_domain = route["domain"]
            ingested.error_message = route["reasoning"]
            ingested.save(update_fields=[
                "status", "routed_domain", "error_message",
            ])
            logger.warning(
                "# [route_ingested_files] #%d (%s) -> dominio no "
                "identificado (%s) -- NEEDS_REVIEW.",
                ingested.pk, filename, route["domain"],
            )

    if new_machine_pks:
        process_machine_document_batch.delay(new_machine_pks)
        logger.info(
            "# [route_ingested_files] %d documento(s) MACHINE "
            "encolado(s) para clasificación: %s.",
            len(new_machine_pks), new_machine_pks,
        )
    if new_personal_pks:
        process_personal_document_batch.delay(new_personal_pks)
        logger.info(
            "# [route_ingested_files] %d documento(s) PERSONAL "
            "encolado(s) para clasificación: %s.",
            len(new_personal_pks), new_personal_pks,
        )
