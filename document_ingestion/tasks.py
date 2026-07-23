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
    match_company_user,
    match_machine_asset,
    match_machine_asset_by_filename,
    normalize_dni,
    route_document,
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
    # Seguimiento para el fallback de herencia de máquina por carpeta
    # (Miguel Ángel, S026, cierre de sesión -- ver el bloque tras el
    # bucle principal): (MachineDocument, source_folder_path,
    # MachineAsset|None) de cada archivo enrutado a MACHINE en este
    # mismo lote.
    machine_routing_records: list[tuple] = []

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
        company = ingested.company
        # webkitRelativePath (origen real de source_folder_path, ver
        # hub.html JS) incluye el nombre de archivo como ÚLTIMO
        # segmento ("A36/A-35 CE.pdf") -- hay que quedarse solo con la
        # parte de carpeta antes de buscar la máquina ahí, o el propio
        # nombre de archivo (que puede mencionar OTRA máquina, caso
        # real de esta sesión) contaminaría la búsqueda por carpeta.
        folder_only_path = (
            ingested.source_folder_path.rsplit("/", 1)[0]
            if ingested.source_folder_path
            and "/" in ingested.source_folder_path
            else ""
        )

        # S026 (cierre de sesión, ampliado) -- la CARPETA manda.
        # Miguel Ángel, explícito: "la carpeta es la que manda.
        # Supuestamente, dentro de esa carpeta de esa máquina está su
        # documentación. Todos los errores que detectemos dentro...
        # la vamos a subir y la vamos a marcar como incidencia".
        # Orden de prioridad para determinar la máquina:
        #   1. CARPETA (source_folder_path) -- si identifica una
        #      máquina, ES la máquina asignada, sin excepción.
        #   2. NOMBRE DE ARCHIVO individual -- solo decide la máquina
        #      cuando la carpeta NO identificó ninguna (subida plana,
        #      sin subcarpetas). Si la carpeta SÍ identificó una
        #      máquina pero el nombre del archivo individual menciona
        #      OTRA distinta, eso NUNCA reasigna -- se registra como
        #      incidencia (content_mismatch_warning) para revisión
        #      manual, nunca se mueve solo.
        #   3. CONTENIDO (Gemini, route_document) -- solo si ni
        #      carpeta ni nombre de archivo identificaron nada.
        # Dominio elegido por el usuario al subir (2026-07-23) -- si
        # es PERSONAL, el emparejamiento por carpeta/nombre de archivo
        # contra MachineAsset NUNCA se intenta, sea cual sea el texto
        # del nombre (caso real que motivó esto: "DOC VARIOS ALONSO
        # PEDROSA,MANUEL.pdf" -- una carpeta de personal -- coincidió
        # por la palabra "VARIOS" con una MachineAsset basura real de
        # ese mismo código, mezclando personal con maquinaria).
        _skip_machine_matching = (
            ingested.forced_domain == IngestedFile.ForcedDomain.PERSONAL
        )
        folder_matched_machine = (
            match_machine_asset_by_filename(company, folder_only_path)
            if folder_only_path and not _skip_machine_matching else None
        )
        filename_matched_machine = (
            match_machine_asset_by_filename(company, filename)
            if not _skip_machine_matching else None
        )

        initial_mismatch_warning = ""
        initial_mismatch_candidate_machine = None

        if folder_matched_machine is not None:
            domain = DOMAIN_MACHINE
            matched_machine = folder_matched_machine
            machine_reference_hint = ""
            worker_dni_hint = ""
            is_confident = True
            reasoning = (
                "Máquina identificada por la carpeta de origen -- "
                "sin llamada a Gemini."
            )
            logger.info(
                "# [route_ingested_files] #%d (%s) -> máquina %s por "
                "CARPETA (%r), sin Gemini.",
                ingested.pk, filename, folder_matched_machine.code,
                folder_only_path,
            )
            if (
                filename_matched_machine is not None
                and filename_matched_machine.pk != folder_matched_machine.pk
            ):
                initial_mismatch_warning = (
                    f"La carpeta de origen asignó este documento a "
                    f"{folder_matched_machine.code}, pero su propio "
                    f"nombre de archivo menciona "
                    f"{filename_matched_machine.code} -- revisar a "
                    f"mano si está bien archivado."
                )
                initial_mismatch_candidate_machine = filename_matched_machine
                logger.warning(
                    "# [route_ingested_files] #%d (%s): discrepancia "
                    "carpeta/nombre -- carpeta dice %s, nombre dice "
                    "%s.",
                    ingested.pk, filename, folder_matched_machine.code,
                    filename_matched_machine.code,
                )
        elif filename_matched_machine is not None:
            domain = DOMAIN_MACHINE
            matched_machine = filename_matched_machine
            machine_reference_hint = ""
            worker_dni_hint = ""
            is_confident = True
            reasoning = (
                "Máquina identificada por nombre de archivo (sin "
                "carpeta reconocible) -- sin llamada a Gemini."
            )
            logger.info(
                "# [route_ingested_files] #%d (%s) -> máquina %s por "
                "NOMBRE DE ARCHIVO (sin carpeta reconocible), sin "
                "Gemini.",
                ingested.pk, filename, filename_matched_machine.code,
            )
        else:
            route = route_document(file_bytes, filename, company)
            domain = route["domain"]
            machine_reference_hint = route["machine_reference_hint"]
            worker_dni_hint = route["worker_dni_hint"]
            is_confident = route["is_confident"]
            reasoning = route["reasoning"]
            # El dominio elegido por el usuario al subir manda siempre
            # sobre lo que Gemini crea reconocer en el contenido
            # (2026-07-23) -- si subió como Personal, nunca se acepta
            # un resultado MACHINE de esta llamada, y viceversa. Solo
            # aplica cuando el usuario SÍ eligió explícitamente
            # (forced_domain no vacío); las filas antiguas sin ese
            # dato siguen confiando en route_document tal cual.
            if ingested.forced_domain:
                domain = ingested.forced_domain
                if domain != DOMAIN_MACHINE:
                    machine_reference_hint = ""
                if domain != DOMAIN_PERSONAL:
                    worker_dni_hint = ""
            matched_machine = (
                match_machine_asset(company, machine_reference_hint)
                if domain == DOMAIN_MACHINE and is_confident
                else None
            )

        if domain == DOMAIN_MACHINE:
            new_document = MachineDocument(
                machine_asset=matched_machine,
                company=company,
                uploaded_by=ingested.uploaded_by,
                original_filename=filename,
                content_hash=ingested.content_hash,
                status=MachineDocument.Status.PENDING,
                detected_reference_hint=(
                    "" if matched_machine
                    else machine_reference_hint
                ),
                content_mismatch_warning=initial_mismatch_warning,
                content_mismatch_candidate_machine=(
                    initial_mismatch_candidate_machine
                ),
            )
            new_document.source_file.save(
                filename, ContentFile(file_bytes), save=False,
            )
            new_document.save()
            new_machine_pks.append(new_document.pk)
            machine_routing_records.append((
                new_document, ingested.source_folder_path, matched_machine,
            ))

            ingested.status = IngestedFile.Status.ROUTED
            ingested.routed_domain = DOMAIN_MACHINE
            ingested.routed_document_pk = new_document.pk
            ingested.source_file.delete(save=False)
            ingested.save(update_fields=[
                "status", "routed_domain", "routed_document_pk",
                "source_file",
            ])
            logger.info(
                "# [route_ingested_files] #%d (%s) -> MACHINE "
                "(MachineDocument #%d, %s).",
                ingested.pk, filename, new_document.pk,
                "asignado" if matched_machine else "SIN ASIGNAR",
            )

        elif domain == DOMAIN_PERSONAL:
            matched_worker = (
                match_company_user(company, worker_dni_hint)
                if is_confident else None
            )
            new_document = PersonalDocument(
                company_user=matched_worker,
                company=company,
                uploaded_by=ingested.uploaded_by,
                original_filename=filename,
                content_hash=ingested.content_hash,
                status=PersonalDocument.Status.PENDING,
                detected_dni_hint=(
                    "" if matched_worker
                    else normalize_dni(worker_dni_hint)
                ),
            )
            new_document.source_file.save(
                filename, ContentFile(file_bytes), save=False,
            )
            new_document.save()
            new_personal_pks.append(new_document.pk)

            ingested.status = IngestedFile.Status.ROUTED
            ingested.routed_domain = DOMAIN_PERSONAL
            ingested.routed_document_pk = new_document.pk
            ingested.source_file.delete(save=False)
            ingested.save(update_fields=[
                "status", "routed_domain", "routed_document_pk",
                "source_file",
            ])
            logger.info(
                "# [route_ingested_files] #%d (%s) -> PERSONAL "
                "(PersonalDocument #%d, %s).",
                ingested.pk, filename, new_document.pk,
                "asignado" if matched_worker else "SIN ASIGNAR",
            )

        else:
            ingested.status = IngestedFile.Status.NEEDS_REVIEW
            ingested.routed_domain = domain
            ingested.error_message = reasoning
            ingested.save(update_fields=[
                "status", "routed_domain", "error_message",
            ])
            logger.warning(
                "# [route_ingested_files] #%d (%s) -> dominio no "
                "identificado (%s) -- NEEDS_REVIEW.",
                ingested.pk, filename, domain,
            )

    # Herencia de máquina por carpeta (Miguel Ángel, S026, cierre de
    # sesión -- caso real: 3 documentos de una misma carpeta quedaron
    # SIN ASIGNAR porque su propio nombre de archivo no llevaba el
    # código/matrícula de la máquina, aunque el resto de la carpeta sí
    # se identificó bien). Palabras textuales: "aunque en el nombre no
    # tenga el código de la máquina, están en la carpeta de la
    # máquina. Entonces, una vez que tenemos determinado qué máquina
    # es, los documentos que se están subiendo de esa carpeta
    # pertenecen a esa máquina."
    #
    # Un documento MACHINE sin máquina emparejada hereda la de sus
    # HERMANOS de la MISMA carpeta (source_folder_path) del MISMO
    # lote, solo si todos los hermanos ya emparejados de esa carpeta
    # coinciden en una única máquina -- si la carpeta mezcla más de
    # una máquina distinta entre sus hermanos, o ninguno se emparejó,
    # se deja sin asignar (nunca se adivina a ciegas sin una señal
    # real de la propia carpeta).
    folder_matched_machine_pks: dict[str, set] = {}
    folder_unassigned_documents: dict[str, list] = {}
    machines_by_pk: dict[int, object] = {}
    for document, folder_path, matched_machine in machine_routing_records:
        if not folder_path:
            continue
        if matched_machine is not None:
            machines_by_pk[matched_machine.pk] = matched_machine
            folder_matched_machine_pks.setdefault(folder_path, set()).add(
                matched_machine.pk,
            )
        else:
            folder_unassigned_documents.setdefault(folder_path, []).append(
                document,
            )

    for folder_path, unassigned_documents in folder_unassigned_documents.items():
        matched_pks = folder_matched_machine_pks.get(folder_path)
        if not matched_pks or len(matched_pks) != 1:
            continue
        inherited_machine = machines_by_pk[next(iter(matched_pks))]
        for document in unassigned_documents:
            document.machine_asset = inherited_machine
            document.detected_reference_hint = ""
            document.save(update_fields=[
                "machine_asset", "detected_reference_hint",
            ])
            logger.info(
                "# [route_ingested_files] MachineDocument #%d (%s) "
                "heredó máquina %s de sus hermanos de carpeta %r -- "
                "no se pudo emparejar por contenido ni por nombre, "
                "pero el resto de la carpeta sí (S026).",
                document.pk, document.original_filename,
                inherited_machine.code, folder_path,
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


@app.task(base=DjangoTask, bind=True, max_retries=1, default_retry_delay=60)
def retry_unassigned_routing(self, domain: str, company_pk: int) -> None:
    """
    Reintenta el enrutado de todos los documentos "sin asignar"
    (status=UNASSIGNED) de un dominio para una empresa -- a petición
    de Miguel Ángel tras detectar que la versión anterior del prompt
    de enrutado (antes de S024-bis) ignoraba el nombre de archivo,
    dejando "sin asignar" documentos con el código/matrícula/DNI
    literalmente en el nombre. NO reclasifica el documento
    (document_type/display_name ya están bien, eso no falló) -- solo
    reintenta encontrar la máquina/trabajador real, con la versión
    corregida de entity_matching_service.classify_and_route().

    Descarga el blob desde GCS (carpeta SIN_ASIGNAR), reintenta el
    enrutado, y si encuentra coincidencia: actualiza machine_asset/
    company_user, pasa a CLASSIFIED, limpia el hint detectado, MUEVE
    el blob de GCS a la carpeta real (sube bajo la ruta nueva + borra
    la antigua -- nunca dos copias) y corrige subject_label en
    cualquier DocumentAlert ya creada. Si sigue sin encontrar
    coincidencia, lo deja tal cual -- nunca fuerza una asignación
    dudosa.
    """
    from django.contrib.contenttypes.models import ContentType

    from document_management.models import DocumentAlert
    from ivr_config.models import Company
    from spare_parts.gcs_service import (
        MACHINE_DOCUMENTS_BUCKET,
        PERSONNEL_DOCUMENTS_BUCKET,
        delete_file,
        download_bytes,
        sanitize_path_component,
        upload_bytes,
    )

    company = Company.objects.filter(pk=company_pk).first()
    if company is None:
        logger.error(
            "# [retry_unassigned_routing] Company #%s no encontrada.",
            company_pk,
        )
        return

    if domain == "machine":
        model = MachineDocument
        bucket_name = MACHINE_DOCUMENTS_BUCKET
    elif domain == "personal":
        model = PersonalDocument
        bucket_name = PERSONNEL_DOCUMENTS_BUCKET
    else:
        logger.error(
            "# [retry_unassigned_routing] Dominio no válido: %r.", domain,
        )
        return

    unassigned_docs = list(
        model.objects
        .filter(company=company, status=model.Status.UNASSIGNED)
        .exclude(gcs_blob_name="")
    )
    if not unassigned_docs:
        logger.info(
            "# [retry_unassigned_routing] Ningún documento sin asignar "
            "para %s en %s.",
            domain, company,
        )
        return

    logger.info(
        "# [retry_unassigned_routing] Reintentando %d documento(s) "
        "sin asignar (%s, %s).",
        len(unassigned_docs), domain, company,
    )

    resolved_count = 0
    for document in unassigned_docs:
        try:
            file_bytes = download_bytes(bucket_name, document.gcs_blob_name)
        except Exception as exc:
            logger.error(
                "# [retry_unassigned_routing] #%d: error descargando "
                "blob %s: %s",
                document.pk, document.gcs_blob_name, exc, exc_info=True,
            )
            continue

        filename = document.original_filename or document.gcs_blob_name
        route = route_document(file_bytes, filename, company)

        if domain == "machine":
            hint = route["machine_reference_hint"]
            target = (
                match_machine_asset(company, hint)
                if route["is_confident"] else None
            )
        else:
            hint = route["worker_dni_hint"]
            target = (
                match_company_user(company, hint)
                if route["is_confident"] else None
            )

        if target is None:
            logger.info(
                "# [retry_unassigned_routing] #%d (%s): sigue sin "
                "coincidencia (pista=%r).",
                document.pk, domain, hint,
            )
            continue

        old_blob_name = document.gcs_blob_name
        if domain == "machine":
            document.machine_asset = target
            document.detected_reference_hint = ""
            new_subject_label = target.code
            new_blob_name = (
                f"{target.code}/"
                f"{sanitize_path_component(document.document_type)} - "
                f"{sanitize_path_component(document.display_name)}.pdf"
            )
        else:
            document.company_user = target
            document.detected_dni_hint = ""
            new_subject_label = (
                target.user.get_full_name() or target.user.username
            )
            new_blob_name = (
                f"{sanitize_path_component(target.dni or new_subject_label)}/"
                f"{sanitize_path_component(document.document_type)} - "
                f"{sanitize_path_component(document.display_name)}.pdf"
            )

        try:
            upload_bytes(bucket_name, new_blob_name, file_bytes)
            delete_file(bucket_name, old_blob_name)
        except Exception as exc:
            logger.error(
                "# [retry_unassigned_routing] #%d: error moviendo blob "
                "de GCS: %s",
                document.pk, exc, exc_info=True,
            )
            continue

        document.gcs_blob_name = new_blob_name
        document.status = model.Status.CLASSIFIED
        document.save()

        content_type = ContentType.objects.get_for_model(document)
        DocumentAlert.objects.filter(
            content_type=content_type, object_id=document.pk,
        ).update(subject_label=new_subject_label)

        resolved_count += 1
        logger.info(
            "# [retry_unassigned_routing] #%d (%s) vinculado a %s tras "
            "reintento.",
            document.pk, domain, new_subject_label,
        )

    logger.info(
        "# [retry_unassigned_routing] %d/%d documento(s) vinculados "
        "tras reintento (%s, company=%s).",
        resolved_count, len(unassigned_docs), domain, company,
    )
