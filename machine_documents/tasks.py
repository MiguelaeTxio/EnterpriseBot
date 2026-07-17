# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/tasks.py
"""
Celery task for machine_documents (Hito 23) -- replaces the
synchronous batch pipeline that ran directly inside
MachineDocumentBatchUploadView.post() until 2026-07-14.

INCIDENT THAT MOTIVATED THIS (2026-07-14): the first end-to-end panel
test of the upload flow -- classify each PDF, detect a master
document, compare coverage, extract uncovered pages, upload everything
to Drive -- ran synchronously inside the HTTP request. With 9 real
documents (one of them, by mistake, a heavy user manual) the total
wall-clock time landed almost exactly on PythonAnywhere's hard
5-minute webapp request timeout, and the load balancer killed the
connection and returned a 504 to the browser -- even though the server
had in fact finished persisting everything just as it got killed
(confirmed via the server error log and a direct query against
MachineDocument). Miguel Ángel's explicit decision: move the whole
pipeline to a Celery task (Always-on Task, same infrastructure already
used by classify_fault_line / upload_task_photo_to_drive /
upload_delivery_note_photo_to_drive) so PythonAnywhere's 5-minute
limit stops being a concern regardless of batch size -- "desde ya",
no technical debt left for later.

process_machine_document_batch(document_pks) is the only task here.
It takes the pks of the MachineDocument rows created (status=PENDING)
by the upload view -- creation there is fast (just saving the
uploaded file to disk, no Gemini/Drive calls), so the request/response
cycle stays well under any timeout no matter how many files are in the
batch. The task itself does the slow part: classify each document
(heuristic first, Gemini otherwise, both in machine_documents.
document_classification_service), detect/compare a candidate master
document against the batch's individuals, extract any uncovered
content into new documents, and upload everything to Drive -- mirrors
the logic that used to live in the view almost 1:1, just moved off the
request thread.

---

Tarea Celery de machine_documents (Hito 23) -- sustituye al pipeline
síncrono que corría directamente dentro de
MachineDocumentBatchUploadView.post() hasta el 2026-07-14.

INCIDENTE QUE LO MOTIVÓ (2026-07-14): la primera prueba end-to-end
desde el panel del flujo de subida -- clasificar cada PDF, detectar un
documento maestro, comparar cobertura, extraer páginas no cubiertas,
subir todo a Drive -- corría de forma síncrona dentro de la petición
HTTP. Con 9 documentos reales (uno de ellos, por error, un manual de
uso pesado) el tiempo total de ejecución cayó casi exactamente sobre
el timeout duro de 5 minutos del webapp de PythonAnywhere, y el
balanceador de carga mató la conexión y devolvió un 504 al navegador
-- aunque el servidor de hecho había terminado de persistir todo justo
cuando lo mataron (confirmado vía el log de errores del servidor y una
consulta directa a MachineDocument). Decisión explícita de Miguel
Ángel: mover todo el pipeline a una tarea Celery (Always-on Task,
misma infraestructura ya usada por classify_fault_line /
upload_task_photo_to_drive / upload_delivery_note_photo_to_drive) para
que el límite de 5 minutos de PythonAnywhere deje de ser un problema
sin importar el tamaño del lote -- "desde ya", sin dejar deuda técnica
para después.

process_machine_document_batch(document_pks) es la única tarea de este
archivo. Recibe los pks de las filas MachineDocument creadas
(status=PENDING) por la vista de subida -- esa creación es rápida
(solo guarda el archivo subido en disco, sin llamadas a Gemini/Drive),
así que el ciclo petición/respuesta se mantiene muy por debajo de
cualquier timeout sin importar cuántos archivos tenga el lote. La
tarea en sí hace la parte lenta: clasificar cada documento (heurística
primero, Gemini si no, ambas en machine_documents.
document_classification_service), detectar/comparar un documento
maestro candidato contra los individuales del lote, extraer cualquier
contenido no cubierto en documentos nuevos, y subir todo a Drive --
replica casi 1:1 la lógica que antes vivía en la vista, solo que fuera
del hilo de la petición.
"""
import logging

from celery.contrib.django.task import DjangoTask
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile

from document_management.alert_service import create_default_expiry_alerts
from document_management.models import DocumentAlert
from document_ingestion.deduplication_service import compute_content_hash
from enterprise_core.celery import app
from spare_parts.gcs_service import (
    GCSNotConfigured,
    upload_machine_document_file,
)

from .document_classification_service import (
    assess_master_coverage,
    classify_by_filename_heuristic,
    classify_document,
    extract_pages,
)
from .models import MachineDocument

logger = logging.getLogger(__name__)


@app.task(base=DjangoTask, bind=True, max_retries=1, default_retry_delay=60)
def process_machine_document_batch(self, document_pks: list[int]) -> None:
    """
    Processes a batch of MachineDocument rows created with
    status=PENDING by MachineDocumentBatchUploadView.post(): classifies
    each one, detects/compares a candidate master document, extracts
    uncovered content, and uploads everything to Drive. Idempotent at
    the per-document level (only PENDING rows are picked up on each
    run, so a manual re-trigger after a partial failure never
    reprocesses documents that already succeeded).

    Never lets one document's failure abort the batch: each document
    is wrapped in its own try/except, marked status=ERROR with
    error_message on failure, and processing continues with the rest.
    Vertex AI 429s are retried inside classify_document() /
    assess_master_coverage() themselves (see
    document_classification_service._generate_content_with_retry) --
    this task-level max_retries=1 is a last-resort safety net, not the
    primary retry mechanism.

    ---

    Procesa un lote de filas MachineDocument creadas con
    status=PENDING por MachineDocumentBatchUploadView.post(): clasifica
    cada una, detecta/compara un documento maestro candidato, extrae
    contenido no cubierto, y sube todo a Drive. Idempotente a nivel de
    documento individual (en cada ejecución solo se recogen las filas
    PENDING, así que un reintento manual tras un fallo parcial nunca
    reprocesa documentos que ya tuvieron éxito).

    Nunca deja que el fallo de un documento aborte el lote entero: cada
    documento va envuelto en su propio try/except, se marca
    status=ERROR con error_message si falla, y el procesamiento
    continúa con el resto. Los 429 de Vertex AI se reintentan dentro de
    classify_document() / assess_master_coverage() mismas (ver
    document_classification_service._generate_content_with_retry) --
    este max_retries=1 a nivel de tarea es una red de seguridad de
    último recurso, no el mecanismo de reintento principal.
    """
    documents = list(
        MachineDocument.objects
        .filter(pk__in=document_pks, status=MachineDocument.Status.PENDING)
        .select_related("machine_asset", "company", "uploaded_by")
    )
    if not documents:
        logger.info(
            "# [process_machine_document_batch] Ningún documento "
            "PENDING encontrado para pks=%s -- nada que hacer "
            "(probablemente ya procesado en una ejecución anterior).",
            document_pks,
        )
        return

    logger.info(
        "# [process_machine_document_batch] Iniciando lote de %d "
        "documento(s): pks=%s.",
        len(documents), document_pks,
    )

    # ------------------------------------------------------------
    # Step 1 -- classify every document individually. Heuristic
    # first (never touches Gemini), classify_document() otherwise.
    # Paso 1 -- clasificar cada documento individualmente. Heurística
    # primero (nunca toca Gemini), classify_document() en caso
    # contrario.
    # ------------------------------------------------------------
    classified: dict[int, dict] = {}
    for document in documents:
        try:
            document.source_file.open("rb")
            file_bytes = document.source_file.read()
        except Exception as exc:
            logger.error(
                "# [process_machine_document_batch] #%d: no se pudo "
                "leer el archivo local: %s",
                document.pk, exc, exc_info=True,
            )
            document.status = MachineDocument.Status.ERROR
            document.error_message = "No se pudo leer el archivo."
            document.save(update_fields=["status", "error_message"])
            continue
        finally:
            document.source_file.close()

        filename = document.original_filename or document.source_file.name

        heuristic_result = classify_by_filename_heuristic(filename)
        if heuristic_result is not None:
            result = heuristic_result
            via_heuristic = True
        else:
            result = classify_document(file_bytes, filename)
            via_heuristic = False

        if not result["document_type"]:
            logger.warning(
                "# [process_machine_document_batch] #%d (%s): "
                "clasificación fallida, marcado ERROR.",
                document.pk, filename,
            )
            document.status = MachineDocument.Status.ERROR
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
        document.document_number = result["document_number"]
        document.issuing_entity = result["issuing_entity"]
        document.is_possible_master = result["is_possible_master"]
        # UNASSIGNED en vez de CLASSIFIED cuando no hay máquina enlazada
        # (ingesta automática de carpeta, S024) -- ver
        # MachineDocument.Status.UNASSIGNED.
        document.status = (
            MachineDocument.Status.CLASSIFIED
            if document.machine_asset_id
            else MachineDocument.Status.UNASSIGNED
        )
        document.save(update_fields=[
            "document_type", "display_name", "expiry_date", "issue_date",
            "document_number", "issuing_entity", "is_possible_master",
            "status",
        ])

        create_default_expiry_alerts(
            document=document,
            expiry_date=document.expiry_date,
            document_label=document.display_name,
            subject_label=(
                document.machine_asset.code if document.machine_asset_id
                else "Sin asignar"
            ),
            company=document.company,
            default_contact=document.uploaded_by,
        )

        classified[document.pk] = {
            "document": document,
            "bytes": file_bytes,
            "filename": filename,
            "result": result,
            "via_heuristic": via_heuristic,
        }

    # ------------------------------------------------------------
    # Step 2 -- for every candidate master among THIS batch, compare
    # against the rest of the batch and extract any uncovered
    # content as a new MachineDocument. Heuristic-classified entries
    # (manuals) are excluded from the comparison set -- their bytes
    # must never reach Gemini.
    #
    # BUGFIX (S024-bis, real caso reportado por Miguel Ángel con
    # ejemplo concreto): un maestro procesado con éxito -- ya sea
    # "fully_covered" (nada que extraer) o con extracción exitosa de
    # las páginas no cubiertas -- NUNCA debe llegar al Paso 3 (subida
    # a GCS). Antes de esta corrección, el maestro se clasificaba en
    # el Paso 1 igual que cualquier documento y este bucle nunca lo
    # quitaba de `classified`, así que acababa subido y persistido
    # como un MachineDocument más (confirmado con datos reales: las
    # filas "Dossier de Maquinaria - E-6998-BDY" encontradas en el
    # reset de zona cero). `masters_to_discard` recoge los pks a
    # borrar (fila + archivo local) y excluir de `classified` al
    # terminar el bucle -- solo en los dos casos donde el maestro se
    # procesó con éxito; si falla la extracción o la clasificación del
    # contenido extraído, el maestro se CONSERVA como red de
    # seguridad (perder la única copia del contenido sería peor que
    # dejarlo duplicado).
    #
    # Paso 2 -- para cada candidato a maestro de ESTE lote, comparar
    # contra el resto del lote y extraer cualquier contenido no
    # cubierto como un MachineDocument nuevo. Las entradas
    # clasificadas por heurística (manuales) se excluyen del
    # conjunto de comparación -- sus bytes nunca deben llegar a
    # Gemini.
    # ------------------------------------------------------------
    masters_to_discard: set[int] = set()

    for pk, item in list(classified.items()):
        if item["via_heuristic"] or not item["result"]["is_possible_master"]:
            continue

        individuals = [
            (other["filename"], other["bytes"])
            for other_pk, other in classified.items()
            if other_pk != pk and not other["via_heuristic"]
        ]
        if not individuals:
            # Sin nada contra lo que comparar -- se conserva tal cual,
            # el Paso 2 no vuelve a tocarlo. Limpiar el flag para que
            # el visor de subida en vivo deje de considerarlo
            # "pendiente de resolver" (S024-cuater).
            item["document"].is_possible_master = False
            item["document"].save(update_fields=["is_possible_master"])
            continue

        coverage = assess_master_coverage(
            item["bytes"], item["filename"], individuals,
        )
        if not coverage["uncovered_pages"]:
            # Todo el contenido del maestro ya está cubierto por los
            # individuales -- se descarta sin más, nunca se sube.
            masters_to_discard.add(pk)
            continue

        try:
            extracted_bytes = extract_pages(
                item["bytes"], coverage["uncovered_pages"],
            )
        except Exception as exc:
            logger.error(
                "# [process_machine_document_batch] #%d (%s): fallo "
                "extrayendo páginas no cubiertas %s: %s",
                pk, item["filename"], coverage["uncovered_pages"], exc,
                exc_info=True,
            )
            item["document"].is_possible_master = False
            item["document"].save(update_fields=["is_possible_master"])
            continue

        extracted_filename = (
            f"{item['filename']} (páginas no cubiertas).pdf"
        )
        extra_result = classify_document(extracted_bytes, extracted_filename)
        if not extra_result["document_type"]:
            logger.warning(
                "# [process_machine_document_batch] #%d (%s): "
                "extracción de páginas no cubiertas obtenida pero su "
                "clasificación falló -- se descarta la extracción, "
                "el maestro se conserva tal cual.",
                pk, item["filename"],
            )
            item["document"].is_possible_master = False
            item["document"].save(update_fields=["is_possible_master"])
            continue

        # Segunda salvaguarda (S024-bis, caso real): el juicio de
        # Gemini sobre qué páginas del maestro están "sin cubrir"
        # puede equivocarse -- confirmado con un caso real donde
        # assess_master_coverage marcó como no cubiertas páginas que
        # en realidad correspondían a documentos ya subidos
        # individualmente en el MISMO lote (mismo document_type,
        # misma fecha), generando un duplicado semántico que el hash
        # nunca detecta (la extracción produce un PDF nuevo,
        # bytes distintos al original aunque el contenido sea el
        # mismo). Si ya existe, para esta MISMA máquina, un documento
        # CLASSIFIED del mismo tipo con la misma fecha de caducidad (o,
        # si ninguno tiene caducidad, la misma fecha de emisión), se
        # descarta la extracción sin crear el duplicado -- se confía
        # en el documento subido individualmente, no en el extraído.
        machine_asset = item["document"].machine_asset
        if machine_asset is not None:
            duplicate_candidates = MachineDocument.objects.filter(
                machine_asset=machine_asset,
                document_type=extra_result["document_type"],
                status=MachineDocument.Status.CLASSIFIED,
            ).exclude(pk=pk)
            is_duplicate = any(
                (
                    extra_result["expiry_date"] is not None
                    and candidate.expiry_date == extra_result["expiry_date"]
                ) or (
                    extra_result["expiry_date"] is None
                    and candidate.expiry_date is None
                    and extra_result["issue_date"] is not None
                    and candidate.issue_date == extra_result["issue_date"]
                )
                for candidate in duplicate_candidates
            )
            if is_duplicate:
                logger.warning(
                    "# [process_machine_document_batch] #%d (%s): "
                    "extracción descartada -- ya existe un documento "
                    "%r para %s con la misma fecha (assess_master_"
                    "coverage marcó incorrectamente estas páginas "
                    "como no cubiertas).",
                    pk, item["filename"], extra_result["document_type"],
                    machine_asset.code,
                )
                masters_to_discard.add(pk)
                continue

        new_document = MachineDocument.objects.create(
            machine_asset=item["document"].machine_asset,
            company=item["document"].company,
            uploaded_by=item["document"].uploaded_by,
            document_type=extra_result["document_type"],
            display_name=extra_result["display_name"],
            source_master_hint=item["filename"],
            expiry_date=extra_result["expiry_date"],
            issue_date=extra_result["issue_date"],
            document_number=extra_result["document_number"],
            issuing_entity=extra_result["issuing_entity"],
            content_hash=compute_content_hash(extracted_bytes),
            status=(
                MachineDocument.Status.CLASSIFIED
                if item["document"].machine_asset_id
                else MachineDocument.Status.UNASSIGNED
            ),
            original_filename=extracted_filename,
        )
        new_document.source_file.save(
            extracted_filename, ContentFile(extracted_bytes), save=True,
        )
        create_default_expiry_alerts(
            document=new_document,
            expiry_date=new_document.expiry_date,
            document_label=new_document.display_name,
            subject_label=(
                new_document.machine_asset.code
                if new_document.machine_asset_id else "Sin asignar"
            ),
            company=new_document.company,
            default_contact=new_document.uploaded_by,
        )
        logger.info(
            "# [process_machine_document_batch] Documento nuevo #%d "
            "creado a partir de páginas no cubiertas de #%d (%s).",
            new_document.pk, pk, item["filename"],
        )

        classified[new_document.pk] = {
            "document": new_document,
            "bytes": extracted_bytes,
            "filename": extracted_filename,
            "result": extra_result,
            "via_heuristic": False,
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
            content_type=ContentType.objects.get_for_model(MachineDocument),
            object_id=master_document.pk,
        ).delete()
        if master_document.source_file:
            master_document.source_file.delete(save=False)
        master_document.delete()
        logger.info(
            "# [process_machine_document_batch] Maestro #%d (%s) "
            "descartado -- nunca se sube a GCS ni se persiste.",
            pk, master_item["filename"],
        )

    # ------------------------------------------------------------
    # Step 3 -- upload every CLASSIFIED document without a Drive
    # link yet. Deletes the local file only after a successful
    # upload (mirrors upload_task_photo_to_drive /
    # upload_delivery_note_photo_to_drive exactly) -- on failure the
    # local file stays so nothing is lost and a manual retry stays
    # possible.
    # Paso 3 -- subir cada documento CLASSIFIED que todavía no tenga
    # enlace de Drive. Borra el archivo local solo tras una subida
    # con éxito (replica exactamente upload_task_photo_to_drive /
    # upload_delivery_note_photo_to_drive) -- ante un fallo el
    # archivo local se conserva para no perder nada y poder
    # reintentar a mano.
    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # Step 3 -- upload every CLASSIFIED document without a GCS blob
    # yet. Deletes the local file only after a successful upload
    # (mirrors upload_task_photo_to_drive /
    # upload_delivery_note_photo_to_drive exactly) -- on failure the
    # local file stays so nothing is lost and a manual retry stays
    # possible.
    # Paso 3 -- subir cada documento CLASSIFIED que todavía no tenga
    # blob de GCS. Borra el archivo local solo tras una subida
    # con éxito (replica exactamente upload_task_photo_to_drive /
    # upload_delivery_note_photo_to_drive) -- ante un fallo el
    # archivo local se conserva para no perder nada y poder
    # reintentar a mano.
    # ------------------------------------------------------------
    for item in classified.values():
        document = item["document"]
        if document.status not in (
            MachineDocument.Status.CLASSIFIED,
            MachineDocument.Status.UNASSIGNED,
        ):
            continue
        if document.gcs_blob_name:
            continue

        try:
            blob_name = upload_machine_document_file(document)
        except GCSNotConfigured as exc:
            logger.error(
                "# [process_machine_document_batch] #%d: Google Cloud "
                "Storage no configurado -- documento NO subido, "
                "archivo local NO borrado. %s",
                document.pk, exc,
            )
            continue
        except Exception as exc:
            logger.error(
                "# [process_machine_document_batch] #%d: fallo "
                "subiendo a GCS: %s",
                document.pk, exc, exc_info=True,
            )
            continue

        document.gcs_blob_name = blob_name
        document.source_file.delete(save=False)
        document.save(update_fields=[
            "gcs_blob_name", "source_file",
        ])
        logger.info(
            "# [process_machine_document_batch] #%d subido a GCS "
            "(blob=%s) y archivo local eliminado.",
            document.pk, blob_name,
        )

    logger.info(
        "# [process_machine_document_batch] Lote completado: %d "
        "documento(s) procesados (incluyendo extraídos de maestro).",
        len(classified),
    )
