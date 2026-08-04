# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/tasks.py
"""
Celery task for batch classification (H29, S040).

Real production incident that forced this: a recursive batch over
~50 files of A-29 (checkbox + "Clasificar seleccionados", synchronous
`ClassifyView.post`) ran one real Gemini call after another inside a
single HTTP request and blew past PythonAnywhere's load balancer
timeout -- 504, "Something went wrong". The site itself was fine
(every Always-on Task stayed Running); only that one long request
died. Moved to the same background-task mechanism already proven in
this project for exactly this kind of per-item Gemini call
(`spare_parts.tasks.extract_delivery_note_data`) instead of inventing
a new one.

Second real problem the same incident exposed: the old synchronous
version only wrote `DataOperationLog`/`DataOperationLogEntry` at the
very end of the loop, in one `bulk_create`. When the request died
mid-batch, several files had already been renamed for real in the
database (`apply_classification` saves per file, immediately) with
**zero** trace in the audit history Miguel Ángel asked for in 3.23 --
exactly the opacity that feature exists to prevent. This task creates
one `DataOperationLogEntry` per file as it finishes, not at the end,
so a crash (of Celery itself, of the whole worker, anything) only
ever loses the *unprocessed* tail of the batch, never the audit trail
of what already happened.

---

Tarea Celery para la clasificación por lote (H29, S040).

Incidente real de producción que forzó esto: un lote recursivo sobre
~50 archivos de A-29 (casillas + "Clasificar seleccionados",
`ClassifyView.post` síncrona) encadenó una llamada real a Gemini tras
otra dentro de una sola petición HTTP y superó el tiempo límite del
balanceador de PythonAnywhere -- 504, "Something went wrong". El
sitio en sí estaba bien (todas las Always-on Tasks seguían Running);
solo esa petición larga murió. Movido al mismo mecanismo de tarea en
segundo plano ya probado en este proyecto para exactamente este tipo
de llamada a Gemini por elemento
(`spare_parts.tasks.extract_delivery_note_data`) en vez de inventar
uno nuevo.

Segundo problema real que expuso el mismo incidente: la versión
síncrona anterior solo escribía `DataOperationLog`/
`DataOperationLogEntry` al final del todo del bucle, en un único
`bulk_create`. Cuando la petición murió a mitad de lote, varios
archivos ya se habían renombrado de verdad en base de datos
(`apply_classification` guarda por archivo, al momento) sin **ningún**
rastro en el historial de auditoría que pedía Miguel Ángel en 3.23 --
justo la opacidad que esa funcionalidad existe para evitar. Esta tarea
crea una `DataOperationLogEntry` por archivo según termina, no al
final, así que un fallo (del propio Celery, de todo el worker,
cualquier cosa) solo pierde la cola *sin procesar* del lote, nunca el
rastro de auditoría de lo que ya había pasado.
"""
import logging

from celery.contrib.django.task import DjangoTask
from django.db import transaction
from enterprise_core.celery import app

from . import classification_service
from .models import DataOperationLog, DataOperationLogEntry, DocumentIndexEntry

logger = logging.getLogger(__name__)


@app.task(base=DjangoTask, bind=True, max_retries=0)
def classify_entries_task(self, log_id: int, entry_pks: list) -> None:
    """
    Runs `classification_service.apply_classification()` over
    `entry_pks` one at a time, writing one `DataOperationLogEntry`
    immediately after each file (never buffered to the end -- see
    module docstring). Updates the `DataOperationLog` row's counters
    as it goes, and its `status` to COMPLETED when done, or FAILED if
    this task itself blows up with something genuinely unexpected.

    Never raises out of the per-file loop for an EXPECTED
    classification failure -- one bad file (a `.docx`, a transient
    Gemini error) is logged as `NOT_CLASSIFIED` and the task moves on
    to the next one, exactly like the old synchronous view already
    did per-file. Only a real bug aborts the whole task -- caught here
    so the log is marked FAILED instead of staying stuck at RUNNING
    forever in silence, then re-raised so Celery still records the
    task failure normally.

    ---

    Ejecuta `classification_service.apply_classification()` sobre
    `entry_pks` uno a uno, escribiendo una `DataOperationLogEntry`
    justo después de cada archivo (nunca guardada en memoria hasta el
    final -- ver docstring del módulo). Actualiza los contadores de la
    fila `DataOperationLog` según avanza, y su `status` a COMPLETED al
    terminar, o a FAILED si esta tarea revienta de verdad con algo
    genuinamente inesperado.

    Nunca lanza fuera del bucle por archivo ante un fallo de
    clasificación ESPERADO -- un archivo malo (un `.docx`, un error
    puntual de Gemini) se registra como `NOT_CLASSIFIED` y la tarea
    sigue con el siguiente, exactamente igual que ya hacía la vista
    síncrona anterior por archivo. Solo un fallo real del código
    aborta la tarea entera -- capturado aquí para marcar el registro
    como FAILED en vez de dejarlo encallado en RUNNING para siempre en
    silencio, y relanzado después para que Celery siga registrando el
    fallo de la tarea con normalidad.
    """
    log = DataOperationLog.objects.get(pk=log_id)

    try:
        applied_count = 0
        not_applied_count = 0

        entries = DocumentIndexEntry.objects.filter(pk__in=entry_pks)
        entries_by_pk = {entry.pk: entry for entry in entries}

        for group_number, pk in enumerate(entry_pks, start=1):
            entry = entries_by_pk.get(pk)
            if entry is None:
                continue

            original_name = entry.name
            result = classification_service.apply_classification(entry)

            if "error" in result:
                not_applied_count += 1
                action = DataOperationLogEntry.ACTION_NOT_CLASSIFIED
                detail = "Error: %s" % result["error"]
            else:
                hints = ", ".join(
                    filter(None, [
                        result.get("machine_code_hint"),
                        " ".join(filter(None, [
                            result.get("first_surname_hint"),
                            result.get("second_surname_hint"),
                            result.get("given_name_hint"),
                        ])),
                        result.get("date_hint"),
                    ])
                )
                mismatch = result.get("machine_mismatch_warning")
                detail = (
                    "Dominio: %s -- Tipo: %s (%s) -- %s%s%s"
                    % (
                        result.get("domain", "?"),
                        result.get("document_type_code", "?"),
                        result.get("confidence", "?"),
                        result.get("reasoning", ""),
                        " -- Pistas: %s" % hints if hints else "",
                        " -- %s" % mismatch if mismatch else "",
                    )
                )
                if result.get("classified"):
                    applied_count += 1
                    action = DataOperationLogEntry.ACTION_CLASSIFIED
                else:
                    not_applied_count += 1
                    action = DataOperationLogEntry.ACTION_NOT_CLASSIFIED

            # Una consulta por archivo, a propósito -- es justo lo
            # que arregla el incidente (rastro real según se avanza,
            # nunca todo junto al final donde un 504 se lo puede
            # llevar por delante).
            DataOperationLogEntry.objects.create(
                log=log,
                group_number=group_number,
                action=action,
                index_entry=entry,
                bucket=entry.bucket,
                blob_name=entry.blob_name,
                name=entry.name,
                previous_name=original_name,
                parent_path=entry.parent_path,
                size_bytes=entry.size_bytes,
                crc32c=entry.crc32c,
                detail=detail,
            )

        with transaction.atomic():
            log.groups_count = len(entry_pks)
            log.kept_count = applied_count
            log.trashed_count = not_applied_count
            log.status = DataOperationLog.STATUS_COMPLETED
            log.save(update_fields=[
                "groups_count", "kept_count", "trashed_count", "status",
            ])
    except Exception:
        logger.exception(
            "# [classify_entries_task] Fallo inesperado, log #%d", log_id,
        )
        log.status = DataOperationLog.STATUS_FAILED
        log.save(update_fields=["status"])
        raise


@app.task(base=DjangoTask, bind=True, max_retries=0)
def refresh_quarantine_index_task(self) -> None:
    """
    **Low-frequency SAFETY NET, not the primary mechanism** (corrected
    same session, H29 annex 3.30) -- the primary path is
    `document_explorer.views.RegisterUploadedObjectView`, a webhook
    the H28 agent calls right after each successful upload, writing
    the index row at that exact moment. Miguel Ángel was explicit that
    the panel must never depend on a periodic refresh to see what is
    already in GCS: "no debe de ser necesario refrescar desde Google
    Cloud Storage." This task only exists for when that webhook call
    itself fails (agent down mid-upload, no network at that instant,
    etc.) -- hence the hourly cadence in `CELERY_BEAT_SCHEDULE`, not
    every few minutes.

    Real incident that led to building the underlying `index_writer.
    refresh_folder()` machinery this task reuses, S040: Miguel Ángel
    dropped a test folder/file straight into a watched folder, the
    H28 agent uploaded it to quarantine correctly (confirmed in the
    agent's own history and, later, in the bucket itself), but it
    stayed invisible in the panel because nothing ever told the index
    it existed. Verbatim: "no podemos tener (...) un archivo ya
    subido (...) y que esté totalmente oculto al usuario. Esto puede
    provocar muchos errores."

    Deliberately scoped to `_CUARENTENA/` only, not the whole bucket
    -- confirmed against the real code (`h28_migration_agent/
    uploader.py`, `build_blob_name` vs `build_quarantine_blob_name`)
    that the agent NEVER writes a new file straight into `DOC.
    MAQUINAS`/`DOC. PERSONAL`; every new file always lands in
    quarantine first. So quarantine is the only place new files can
    ever go "invisible" this way -- refreshing the whole ~37.500-file
    tree on a timer would be needless cost for a problem that only
    ever happens in one small corner of it.

    Walks `_CUARENTENA/` breadth-first using `index_writer.
    refresh_folder()` (same routine logic as the
    `refresh_document_folder` management command, not duplicated)
    one level at a time -- quarantine is expected to stay small
    (pending classification, not the whole historical corpus), so a
    plain queue-based walk is simple and cheap enough; no need for
    the single-listing-call optimisation `refresh_document_folder`'s
    docstring describes for the full bucket.

    ---

    **Red de seguridad de baja frecuencia, no el mecanismo principal**
    (corregido en la misma sesión, anexo H29 3.30) -- el camino
    principal es `document_explorer.views.RegisterUploadedObjectView`,
    un webhook al que el agente H28 avisa justo tras cada subida con
    éxito, escribiendo la fila del índice en ese mismo momento. Miguel
    Ángel fue explícito en que el panel nunca debe depender de un
    refresco periódico para ver lo que ya está en GCS: "no debe de ser
    necesario refrescar desde Google Cloud Storage." Esta tarea solo
    existe para cuando ese propio aviso falla (agente caído a mitad de
    subida, sin red en ese instante, etc.) -- de ahí la cadencia
    horaria en `CELERY_BEAT_SCHEDULE`, no cada pocos minutos.

    Incidente real que llevó a construir la maquinaria de
    `index_writer.refresh_folder()` que esta tarea reutiliza, S040:
    Miguel Ángel soltó una carpeta/archivo de
    prueba directamente en una carpeta vigilada, el agente H28 lo
    subió a cuarentena correctamente (confirmado en el propio
    historial del agente y, después, en el propio cubo), pero se
    quedó invisible en el panel porque nada le decía nunca al índice
    que existía. Verbatim: "no podemos tener (...) un archivo ya
    subido (...) y que esté totalmente oculto al usuario. Esto puede
    provocar muchos errores."

    Acotada a propósito solo a `_CUARENTENA/`, no al cubo entero --
    confirmado contra el código real (`h28_migration_agent/
    uploader.py`, `build_blob_name` frente a
    `build_quarantine_blob_name`) que el agente NUNCA escribe un
    archivo nuevo directamente en `DOC. MAQUINAS`/`DOC. PERSONAL`;
    todo archivo nuevo pasa siempre antes por cuarentena. Así que
    cuarentena es el único sitio donde un archivo nuevo puede quedar
    "invisible" de esta forma -- refrescar el árbol entero de
    ~37.500 archivos con un temporizador sería un coste innecesario
    para un problema que solo ocurre en un rincón pequeño de él.

    Recorre `_CUARENTENA/` en anchura con `index_writer.
    refresh_folder()` (misma lógica rutinaria que ya usa el comando
    de gestión `refresh_document_folder`, no duplicada) un nivel cada
    vez -- se espera que la cuarentena se mantenga pequeña (pendiente
    de clasificar, no el corpus histórico entero), así que un
    recorrido simple por cola es suficientemente barato; no hace
    falta la optimización de listado único que describe el docstring
    de `refresh_document_folder` para el cubo completo.
    """
    from document_explorer.buckets import PRIMARY_BUCKET, QUARANTINE_PREFIX
    from document_explorer import index_writer

    root = QUARANTINE_PREFIX.rstrip("/")
    queue = [root]
    folders_seen = 0

    while queue:
        folder_path = queue.pop(0)
        folders_seen += 1
        _, _, _, subfolders = index_writer.refresh_folder(
            PRIMARY_BUCKET, folder_path,
        )
        queue.extend(subfolders)

    logger.info(
        "# [refresh_quarantine_index_task] %d carpeta(s) de cuarentena "
        "recorrida(s).", folders_seen,
    )


_QUARANTINE_CONSUME_BATCH_SIZE = 40


@app.task(base=DjangoTask, bind=True, max_retries=0)
def consume_quarantine_task(self) -> None:
    """
    Periodic (Celery Beat) Always-on Task that classifies the real
    quarantine backlog -- H29 roadmap point 2, Miguel Ángel: "es
    necesario empezar ya a clasificar lo que tenemos en cuarentena,
    tener la Always-on Task (...) todo lo que haga el agente de la
    Always-on Task tiene que quedar reflejado en el historial, en el
    mismo historial que estamos viendo los cambios que hacemos."

    Runs `classification_service.apply_quarantine_classification()`
    over up to `_QUARANTINE_CONSUME_BATCH_SIZE` live files still
    sitting under `_CUARENTENA/`, oldest first -- capped on purpose,
    same reasoning as `classify_entries_task`'s move to the background
    in the first place: a real Gemini call per file, bounded per run
    so no single run grows unbounded as the backlog grows.

    Writes to the exact same `DataOperationLog`/`DataOperationLogEntry`
    tables as manual classification (`operation_type=
    QUARANTINE_CONSUME`), one entry per file as it finishes -- same
    incremental-audit reasoning as `classify_entries_task` (H29 3.28):
    a crash mid-run must never lose the trace of what already
    happened. Files relocated for real (MACHINE via folder/code, or
    PERSONAL via an exact DNI match against `PersonIdentity`, S041)
    are logged as `ACTION_RELOCATED`. Files Gemini is CERTAIN combine
    two or more distinct catalogued documents (`is_dossier`, S041 --
    Miguel Ángel: "cuando tenemos la seguridad de que es un dossier
    (...) hay que eliminarlo directamente") are soft-deleted to
    `_DOSSIER_TRASH_USERNAME`'s papelera and logged as `ACTION_TRASHED`
    -- never a guess, plain unclassifiable `DESCONOCIDO` still falls
    through to the fallback below. Everything else (identity/machine
    not resolved with certainty) is logged as `ACTION_NOT_CLASSIFIED`
    even when a type was successfully suggested -- Miguel Ángel's
    explicit fallback: classify everything, but never move or delete
    anything the system isn't sure about; leave it flagged for a
    human instead.

    ---

    Always-on Task periódica (Celery Beat) que clasifica de verdad la
    cola de cuarentena -- punto 2 de la hoja de ruta H29, Miguel Ángel:
    "es necesario empezar ya a clasificar lo que tenemos en cuarentena,
    tener la Always-on Task (...) todo lo que haga el agente de la
    Always-on Task tiene que quedar reflejado en el historial, en el
    mismo historial que estamos viendo los cambios que hacemos."

    Ejecuta `classification_service.apply_quarantine_classification()`
    sobre hasta `_QUARANTINE_CONSUME_BATCH_SIZE` archivos vivos que
    sigan dentro de `_CUARENTENA/`, los más antiguos primero -- acotado
    a propósito, mismo motivo que llevó a `classify_entries_task` a
    segundo plano en primer lugar: una llamada real a Gemini por
    archivo, limitada por ejecución para que ninguna corrida crezca
    sin límite según crece la cola.

    Escribe en las mismas tablas `DataOperationLog`/
    `DataOperationLogEntry` que la clasificación manual
    (`operation_type=QUARANTINE_CONSUME`), una línea por archivo según
    termina -- mismo razonamiento de auditoría incremental que
    `classify_entries_task` (H29 3.28): un fallo a mitad de ejecución
    nunca debe perder el rastro de lo que ya pasó. Los archivos que se
    reubican de verdad (MÁQUINA por carpeta/código, o PERSONAL por
    coincidencia exacta de DNI contra `PersonIdentity`, S041) quedan
    como `ACTION_RELOCATED`. Los archivos de los que Gemini tiene
    CERTEZA de que combinan dos o más documentos catalogados distintos
    (`is_dossier`, S041 -- Miguel Ángel: "cuando tenemos la seguridad
    de que es un dossier (...) hay que eliminarlo directamente") se
    reubican a la papelera de `_DOSSIER_TRASH_USERNAME` y quedan como
    `ACTION_TRASHED` -- nunca una sospecha, un `DESCONOCIDO` simple sin
    certeza de dossier sigue cayendo en el mismo fallback de siempre.
    Todo lo demás (identidad/máquina sin resolver con certeza) queda
    como `ACTION_NOT_CLASSIFIED` incluso cuando sí se sugirió un tipo
    -- red de seguridad explícita de Miguel Ángel: clasificar todo,
    pero no mover ni eliminar nunca nada de lo que el sistema no esté
    seguro; dejarlo marcado para un humano.
    """
    from document_explorer import classification_service
    from document_explorer.buckets import PRIMARY_BUCKET, QUARANTINE_PREFIX
    from document_explorer.models import DocumentIndexEntry

    entries = list(
        DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            parent_path__startswith=QUARANTINE_PREFIX,
        )
        .order_by("indexed_at")[:_QUARANTINE_CONSUME_BATCH_SIZE]
    )
    if not entries:
        return

    # Real incident, S040: si el worker se reinicia a mitad de una
    # pasada (p. ej. por un despliegue), el proceso muere en seco y la
    # fila del DataOperationLog anterior se queda en RUNNING para
    # siempre -- nunca llega al bloque except propio. Las líneas ya
    # escritas están bien (registro incremental, 3.28) pero la propia
    # fila queda huérfana. Con concurrency=1 y un solo disparo por
    # intervalo, cualquier RUNNING de este mismo operation_type que
    # siga existiendo al arrancar una pasada nueva solo puede ser
    # exactamente eso -- se cierra como FAILED con una nota, nunca se
    # deja acumulando confusión en el panel de estado (3.33).
    orphaned = DataOperationLog.objects.filter(
        operation_type=DataOperationLog.OPERATION_QUARANTINE_CONSUME,
        status=DataOperationLog.STATUS_RUNNING,
    )
    for stale_log in orphaned:
        stale_log.status = DataOperationLog.STATUS_FAILED
        stale_log.save(update_fields=["status"])
        logger.warning(
            "# [consume_quarantine_task] Pasada huerfana #%d cerrada "
            "como FAILED (worker reiniciado a mitad, probable "
            "despliegue).", stale_log.pk,
        )

    log = DataOperationLog.objects.create(
        operation_type=DataOperationLog.OPERATION_QUARANTINE_CONSUME,
        bucket=PRIMARY_BUCKET,
        path_prefix=QUARANTINE_PREFIX.rstrip("/"),
        status=DataOperationLog.STATUS_RUNNING,
    )

    try:
        relocated_count = 0
        pending_count = 0
        dossier_trashed_count = 0

        for group_number, entry in enumerate(entries, start=1):
            original_name = entry.name
            result = (
                classification_service
                .apply_quarantine_classification(entry)
            )

            if "error" in result:
                pending_count += 1
                action = DataOperationLogEntry.ACTION_NOT_CLASSIFIED
                detail = "Error: %s" % result["error"]
            else:
                hints = ", ".join(
                    filter(None, [
                        result.get("machine_code_hint"),
                        " ".join(filter(None, [
                            result.get("first_surname_hint"),
                            result.get("second_surname_hint"),
                            result.get("given_name_hint"),
                        ])),
                        result.get("dni_hint"),
                        result.get("date_hint"),
                    ])
                )
                mismatch = result.get("machine_mismatch_warning")
                detail = (
                    "Dominio: %s -- Tipo: %s (%s) -- %s%s%s"
                    % (
                        result.get("domain", "?"),
                        result.get("document_type_code", "?"),
                        result.get("confidence", "?"),
                        result.get("reasoning", ""),
                        " -- Pistas: %s" % hints if hints else "",
                        " -- %s" % mismatch if mismatch else "",
                    )
                )
                if result.get("relocated"):
                    relocated_count += 1
                    action = DataOperationLogEntry.ACTION_RELOCATED
                elif result.get("trashed"):
                    dossier_trashed_count += 1
                    action = DataOperationLogEntry.ACTION_TRASHED
                    detail = "[DOSSIER ELIMINADO] " + detail
                else:
                    pending_count += 1
                    action = DataOperationLogEntry.ACTION_NOT_CLASSIFIED

            DataOperationLogEntry.objects.create(
                log=log,
                group_number=group_number,
                action=action,
                index_entry=entry,
                bucket=entry.bucket,
                blob_name=entry.blob_name,
                name=entry.name,
                previous_name=original_name,
                parent_path=entry.parent_path,
                size_bytes=entry.size_bytes,
                crc32c=entry.crc32c,
                detail=detail,
            )

        with transaction.atomic():
            log.groups_count = len(entries)
            log.kept_count = relocated_count
            log.trashed_count = pending_count
            log.dossier_trashed_count = dossier_trashed_count
            log.status = DataOperationLog.STATUS_COMPLETED
            log.save(update_fields=[
                "groups_count", "kept_count", "trashed_count",
                "dossier_trashed_count", "status",
            ])
    except Exception:
        logger.exception(
            "# [consume_quarantine_task] Fallo inesperado, log #%d", log.pk,
        )
        log.status = DataOperationLog.STATUS_FAILED
        log.save(update_fields=["status"])
        raise
