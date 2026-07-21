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
from document_management.models import DocumentAlert, DocumentSubstitutionLog
from document_management.vigencia_service import DocumentSnapshot, evaluate_substitution
from document_ingestion.deduplication_service import compute_content_hash
from document_ingestion.preflight_discard_service import (
    CANONICAL_GROUP_DISPLAY_NAMES,
    find_obsolescence_group,
    learn_from_classification,
)
from enterprise_core.celery import app
from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    GCSNotConfigured,
    download_bytes,
    upload_machine_document_file,
)

from .document_classification_service import (
    MANUAL_DOCUMENT_TYPE,
    assess_master_coverage,
    classify_by_filename_heuristic,
    classify_document,
    extract_pages,
    is_probable_master_by_filename_and_size,
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

        # S025, decisión explícita de Miguel Ángel: un posible
        # maestro/dossier detectado por nombre+peso se descarta AQUÍ
        # MISMO, sin ninguna llamada a Gemini de ningún tipo (ni
        # clasificación, ni comparación de cobertura) -- nunca entra
        # en `classified`, así que el Paso 2 (comparación de
        # cobertura) ni se entera de que existió. El enrutado
        # (document_ingestion.entity_matching_service.route_document)
        # ya aplicó el mismo heurístico para no gastar tampoco esa
        # llamada. IngestedFile.routed_document_pk sigue apuntando a
        # este pk ya borrado -- el visor de subida en vivo lo muestra
        # como "descartado" igual que un maestro real comparado por
        # Gemini (_batch_status_rows, panel/views_documentation.py).
        if is_probable_master_by_filename_and_size(filename, len(file_bytes)):
            logger.info(
                "# [process_machine_document_batch] #%d (%s): posible "
                "maestro/dossier detectado por nombre+peso -- "
                "descartado SIN llamada a Gemini (ni clasificación ni "
                "comparación de cobertura).",
                document.pk, filename,
            )
            if document.source_file:
                document.source_file.delete(save=False)
            document.delete()
            continue

        heuristic_result = classify_by_filename_heuristic(filename)
        if heuristic_result is not None:
            result = heuristic_result
            via_heuristic = True
        else:
            # S026, fase 3 -- máquina+tipo+fecha (REGLA B de
            # document_ingestion.preflight_discard_service) YA decidió
            # el tipo en el preflight previo a la subida para la
            # mayoría de los casos; aquí se vuelve a comprobar (mismo
            # diccionario dinámico: estático + Insurer de BD +
            # aprendizaje) porque este documento puede haber llegado
            # por una vía que no pasó por el preflight (ingesta
            # automática de carpeta) o el aprendizaje puede haber
            # cambiado entre el preflight y este punto del mismo lote.
            # Miguel Ángel: "caso de que por heurística determinamos
            # un tipo conocido... directamente lo tenemos ya
            # clasificado por el nombre. Que no lo tenemos claro, a
            # eso entra Gemini, lo clasifica ella" -- Gemini SIGUE
            # llamándose siempre (es la única vía para extraer fechas/
            # número de documento/entidad emisora, que la heurística
            # nunca lee del contenido), pero su document_type se
            # descarta a favor del de la heurística cuando el grupo es
            # uno de los conocidos con etiqueta legible
            # (CANONICAL_GROUP_DISPLAY_NAMES) -- los grupos dinámicos
            # (aseguradora real o aprendidos) no tienen etiqueta manual
            # y se dejan tal cual los devuelva Gemini.
            heuristic_group = find_obsolescence_group(
                filename,
                machine=document.machine_asset,
                company=document.company,
            )
            result = classify_document(file_bytes, filename)
            via_heuristic = False

            if heuristic_group is not None:
                display_label = CANONICAL_GROUP_DISPLAY_NAMES.get(
                    heuristic_group,
                )
                if display_label and result.get("document_type"):
                    logger.info(
                        "# [process_machine_document_batch] #%d (%s): "
                        "tipo ya conocido por heurística (%r) -- "
                        "Gemini usado solo para extracción de datos, "
                        "document_type de Gemini (%r) sustituido.",
                        document.pk, filename, heuristic_group,
                        result["document_type"],
                    )
                    result["document_type"] = display_label
            elif result.get("document_type"):
                # La heurística NO reconoció el tipo y Gemini sí pudo
                # clasificarlo -- se aprende para que el resto del
                # lote (y futuras subidas) ya lo reconozcan por nombre
                # sin volver a llamar a Gemini (Miguel Ángel, S026: "el
                # propio sistema propone automáticamente nuevas
                # entradas de diccionario... se usa en la propia
                # sesión de subida").
                learn_from_classification(
                    filename, result["document_type"],
                    machine=document.machine_asset,
                    company=document.company,
                )

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

        # Salvaguarda de discrepancia (S026, cierre de sesión) --
        # Miguel Ángel: "no deberíamos de dejarlo única y
        # exclusivamente al nombre del archivo... si se sube y se
        # asigna a esa máquina, marcarlo con incidencia y decir, ojo,
        # el interior no coincide con el exterior". La máquina YA
        # quedó asignada por CARPETA (prioridad 1) o por nombre de
        # archivo (prioridad 2, solo sin carpeta reconocible) en
        # document_ingestion.tasks.route_ingested_files -- esto NUNCA
        # cambia esa asignación, solo avisa.
        #
        # content_mismatch_warning puede venir YA relleno desde el
        # enrutado (carpeta y nombre de archivo discreparon entre sí)
        # -- NUNCA se resetea a ciegas aquí: si Gemini no encuentra
        # ninguna discrepancia de contenido, se deja tal cual estaba;
        # si sí encuentra una, la sustituye (la de contenido es más
        # específica -- lee dentro del propio documento).
        reference_in_content = result.get("machine_reference_in_content", "")
        if reference_in_content and document.machine_asset_id:
            from document_ingestion.entity_matching_service import (
                _normalize_for_matching,
                match_machine_asset,
            )
            normalized_reference = _normalize_for_matching(reference_in_content)
            normalized_code = _normalize_for_matching(
                document.machine_asset.code,
            )
            normalized_plate = _normalize_for_matching(
                document.machine_asset.plate or "",
            )
            if normalized_reference and normalized_reference not in (
                normalized_code, normalized_plate,
            ):
                document.content_mismatch_warning = (
                    f"Máquina asignada: {document.machine_asset.code}, "
                    f"pero el CONTENIDO del documento menciona la "
                    f"referencia {reference_in_content!r} -- revisar a "
                    f"mano si está bien archivado."
                )
                # Resuelve la referencia a una MachineAsset real, si es
                # posible -- necesario para el botón "Resolver
                # incidencia con <máquina>" de la ficha de máquina
                # (S026). match_machine_asset compara por igualdad
                # normalizada exacta (no subcadena, a diferencia de
                # match_machine_asset_by_filename) -- coherente con
                # que aquí la referencia ya viene limpia, extraída por
                # Gemini del contenido, no de un nombre de archivo con
                # texto alrededor.
                document.content_mismatch_candidate_machine = (
                    match_machine_asset(document.company, reference_in_content)
                )
                logger.warning(
                    "# [process_machine_document_batch] #%d (%s): "
                    "discrepancia nombre/contenido -- asignado a %s "
                    "por nombre, contenido menciona %r.",
                    document.pk, filename, document.machine_asset.code,
                    reference_in_content,
                )

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
            "content_mismatch_warning", "content_mismatch_candidate_machine",
            "status",
        ])

        # S025, decisión explícita de Miguel Ángel: "en el dosier no
        # nos tenemos que fiar absolutamente en nada... no tiene
        # sentido ninguno alertar del documento maestro". Un posible
        # maestro normalmente se descarta en el Paso 2 (y con él sus
        # alertas, ver más abajo), pero mientras sigue is_possible_
        # master=True aquí (todavía sin resolver) nunca debe generar
        # alertas -- ni siquiera en el caso raro donde sobrevive como
        # red de seguridad (extracción fallida): un documento maestro
        # nunca es sujeto propio de alerta, su contenido ya está
        # representado por los documentos individuales reales.
        if not document.is_possible_master:
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

        # Ampliar con documentos YA PERSISTIDOS de la misma máquina --
        # bug real (Miguel Ángel, caso concreto): al volver a subir un
        # lote donde los individuales ya existían de una subida
        # anterior, la deduplicación por hash los descarta ANTES de
        # llegar aquí (nunca entran en `classified`), así que el
        # maestro se quedaba comparando contra una lista vacía y se
        # persistía entero como si fuera un documento nuevo -- "el
        # dosier se lo ha tragado entero". El maestro nunca se
        # persiste (masters_to_discard lo borra siempre que se
        # descarta a mano), así que tampoco hay un hash suyo contra el
        # que comparar en la siguiente subida -- la única forma
        # robusta es comparar su contenido contra lo que YA está
        # vigente para esta máquina, no solo contra el resto del lote
        # actual.
        machine_asset = item["document"].machine_asset
        if machine_asset is not None:
            persisted_siblings = MachineDocument.objects.filter(
                machine_asset=machine_asset,
                status=MachineDocument.Status.CLASSIFIED,
            ).exclude(pk__in=classified.keys())
            for sibling in persisted_siblings:
                if not sibling.gcs_blob_name:
                    continue
                try:
                    sibling_bytes = download_bytes(
                        MACHINE_DOCUMENTS_BUCKET, sibling.gcs_blob_name,
                    )
                except Exception as exc:
                    logger.error(
                        "# [process_machine_document_batch] #%d (%s): "
                        "error descargando documento ya persistido #%d "
                        "(%s) para comparar cobertura: %s",
                        pk, item["filename"], sibling.pk,
                        sibling.gcs_blob_name, exc, exc_info=True,
                    )
                    continue
                individuals.append((
                    sibling.original_filename or sibling.display_name,
                    sibling_bytes,
                ))

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
        if coverage.get("comparison_failed"):
            # S025, hallazgo real de Miguel Ángel con log de
            # producción: un error de Gemini durante la comparación
            # (ej. 400 INVALID_ARGUMENT por límite de tokens al
            # acumular muchos individuales ya persistidos para la
            # misma máquina) NUNCA debe tratarse como "cobertura
            # confirmada" -- el maestro se CONSERVA como documento
            # real (misma red de seguridad que ya existía para el
            # fallo de extracción/clasificación de páginas no
            # cubiertas, más abajo), nunca se descarta sin haber
            # comparado nada de verdad.
            logger.warning(
                "# [process_machine_document_batch] #%d (%s): la "
                "comparación de cobertura falló de verdad (%s) -- "
                "maestro CONSERVADO como documento real, nunca "
                "descartado sin comparar.",
                pk, item["filename"], coverage.get("reasoning", ""),
            )
            item["document"].is_possible_master = False
            item["document"].save(update_fields=["is_possible_master"])
            continue
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
    # Step 2bis (S025) -- sustitución SILENCIOSA por documento_type,
    # registrada en un log de trazabilidad. Corrige explícitamente el
    # diseño original del anexo H26 sección 2.4 (diálogo interactivo
    # que preguntaba al usuario) -- decisión de Miguel Ángel en S025:
    # "no tiene sentido que salte... se hace el cambio simplemente y
    # no se avisa [...] que quede registrado como en una especie de
    # log visible". La comparación de fechas la hace
    # vigencia_service.evaluate_substitution() (lógica pura, agnóstica
    # de dominio) -- este bloque solo persiste el resultado. Solo
    # documentos CLASSIFIED con máquina asignada (los UNASSIGNED no
    # tienen con qué comparar todavía) y que ya superaron el Paso 2
    # (masters_to_discard ya aplicado, `classified` ya no contiene
    # maestros descartados).
    # ------------------------------------------------------------
    machine_content_type = ContentType.objects.get_for_model(MachineDocument)
    for item in classified.values():
        document = item["document"]
        if (
            document.status != MachineDocument.Status.CLASSIFIED
            or not document.machine_asset_id
            or document.document_type == MANUAL_DOCUMENT_TYPE
        ):
            continue

        existing_same_type = list(
            MachineDocument.objects.filter(
                machine_asset_id=document.machine_asset_id,
                document_type=document.document_type,
                status=MachineDocument.Status.CLASSIFIED,
            ).exclude(pk=document.pk)
        )
        if not existing_same_type:
            continue

        incoming_snapshot = DocumentSnapshot(
            identifier=document.pk,
            expiry_date=document.expiry_date,
            issue_date=document.issue_date,
        )
        existing_snapshots = [
            DocumentSnapshot(
                identifier=sibling.pk,
                expiry_date=sibling.expiry_date,
                issue_date=sibling.issue_date,
            )
            for sibling in existing_same_type
        ]
        result = evaluate_substitution(incoming_snapshot, existing_snapshots)
        if not result.has_existing_of_same_type:
            continue

        siblings_by_pk = {sibling.pk: sibling for sibling in existing_same_type}
        machine_label = document.machine_asset.code

        if result.incoming_should_prevail:
            for archived_pk in result.existing_to_archive:
                archived_document = siblings_by_pk.get(archived_pk)
                if archived_document is None:
                    continue
                DocumentSubstitutionLog.objects.create(
                    company=document.company,
                    superseding_content_type=machine_content_type,
                    superseding_object_id=document.pk,
                    superseding_label=document.display_name,
                    superseded_content_type=machine_content_type,
                    superseded_object_id=archived_document.pk,
                    superseded_label=archived_document.display_name,
                    subject_label=machine_label,
                    document_type=document.document_type,
                    reasoning=result.reasoning,
                )
        else:
            # El entrante no prevalece -- el/los existente(s) del
            # mismo tipo se quedan como estaban. Se registra contra el
            # existente más reciente (criterio de vigencia_service:
            # expiry_date si lo tiene, si no issue_date), como
            # referencia legible de "quién sigue vigente".
            prevailing = max(
                existing_same_type,
                key=lambda d: d.expiry_date or d.issue_date or d.created_at.date(),
            )
            DocumentSubstitutionLog.objects.create(
                company=document.company,
                superseding_content_type=machine_content_type,
                superseding_object_id=prevailing.pk,
                superseding_label=prevailing.display_name,
                superseded_content_type=machine_content_type,
                superseded_object_id=document.pk,
                superseded_label=document.display_name,
                subject_label=machine_label,
                document_type=document.document_type,
                reasoning=result.reasoning,
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
