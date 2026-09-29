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

    S124: one single listing of the whole prefix and one index query;
    only blobs missing from the index are created (see the comment in
    the body for the real 12-minute incident that led to this).

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

    S124: un único listado del prefijo entero y una única consulta al
    índice; solo se dan de alta los blobs que faltan (ver el
    comentario del cuerpo para el incidente real de 12 minutos que lo
    motivó).
    """
    # H30 (S124), punto 6: la versión anterior recorría la cuarentena
    # carpeta a carpeta (`refresh_folder`, un listado de GCS y una
    # reconciliación por carpeta) y tardaba más de 12 minutos,
    # ocupando el worker. Causa real: por la directriz 4.12 el blob
    # nunca se mueve, así que el prefijo físico `_CUARENTENA/` no se
    # vacía nunca -- 1.385 archivos ya reubicados y 381 carpetas a
    # 29/09/2026, creciendo con cada archivo que entra. Esta red de
    # seguridad solo tiene que encontrar blobs que el índice no tiene:
    # un único listado del prefijo entero, una única consulta de los
    # ya indexados (incluidos los que están en la papelera, para que
    # no reaparezcan) y alta solo de lo que falte, con las mismas
    # funciones de `index_writer` (nunca toca filas existentes, 4.12).
    import time

    from django.db import transaction

    from document_explorer import index_writer
    from document_explorer.buckets import PRIMARY_BUCKET, QUARANTINE_PREFIX
    from document_explorer.models import DocumentIndexEntry, path_digest
    from spare_parts.gcs_service import get_storage_client

    started = time.monotonic()
    blobs = [
        blob for blob in get_storage_client().list_blobs(
            PRIMARY_BUCKET, prefix=QUARANTINE_PREFIX,
        )
        if not blob.name.endswith("/")
    ]
    by_hash = {path_digest(blob.name): blob for blob in blobs}
    indexed = set(
        DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET, purged_at__isnull=True,
            blob_name_hash__in=list(by_hash),
        ).values_list("blob_name_hash", flat=True)
    )
    missing = [
        blob for digest, blob in by_hash.items() if digest not in indexed
    ]
    created = 0
    if missing:
        rows = [index_writer.file_row(blob) for blob in missing]
        parents = sorted({row["parent_path"] for row in rows})
        with transaction.atomic():
            for parent in parents:
                index_writer.ensure_folder_chain(PRIMARY_BUCKET, parent)
            created, _updated = index_writer.persist_rows(
                PRIMARY_BUCKET, rows,
                scope_hashes={path_digest(row["blob_name"]) for row in rows},
                skip_fields=("total_size_bytes",),
            )
            index_writer.recount_children(
                PRIMARY_BUCKET, folder_paths=parents,
            )

    logger.info(
        "# [refresh_quarantine_index_task] %d objeto(s) en cuarentena, "
        "%d sin indexar dado(s) de alta, %.1f s.",
        len(blobs), created, time.monotonic() - started,
    )


_QUARANTINE_CONSUME_BATCH_SIZE = 40


def _resolve_expiry_for_relocated_entry(entry) -> None:
    """
    H30 (S50) -- pipeline de fecha EN TIEMPO REAL, enganchado justo
    despues de que un archivo se reubique de verdad fuera de
    cuarentena. Miguel Angel, verbatim: "cuando un archivo llegue,
    conforme llegue y se clasifique, hay que sacar la fecha de
    caducidad si la tiene [...] antes tenemos que agotar todos los
    pasos. Heuristica primero, OCR despues, y llamada a Gemini
    despues."

    Deliberadamente separada de `apply_quarantine_classification()`
    (nunca se toca esa funcion, ya muy documentada con incidentes
    reales) -- este paso corre DESPUES, como post-procesado del
    resultado ya reubicado, mismo principio de responsabilidad unica
    que el resto de `consume_quarantine_task`.

    Nunca bloquea la reubicacion si falla -- cualquier excepcion
    (descarga, OCR, Gemini) se registra en el log y se sigue. Si
    ninguno de los tres pasos encuentra fecha, el documento queda con
    `expiry_date`/`issue_date` en blanco a proposito -- la propia
    ausencia de fecha en un tipo `tracks_expiry=True` es la señal de
    "necesita atencion humana" que se ve en el panel de
    Documentacion (columna de alerta), sin necesidad de ningun campo
    booleano nuevo.
    """
    from document_explorer import expiry_resolution_service
    from document_management.alert_service import (
        create_default_expiry_alerts, get_docs_supervisor_contacts,
    )
    from fleet.models import MachineAsset
    from ivr_config.models import Company
    from spare_parts.gcs_service import download_bytes

    entry.refresh_from_db()
    if not entry.document_type_id or not entry.document_type.tracks_expiry:
        return
    if entry.expiry_date or entry.issue_date:
        return
    if not entry.domain_content_type_id or not entry.domain_object_id:
        return

    try:
        data = download_bytes(entry.bucket, entry.blob_name)
        field, found = expiry_resolution_service.resolve_expiry_date(
            entry.document_type, entry.name, data,
        )
    except Exception:
        logger.exception(
            "# [_resolve_expiry_for_relocated_entry] Fallo resolviendo "
            "fecha de #%d (%s) -- se deja en blanco, atencion humana "
            "requerida.", entry.pk, entry.name,
        )
        return

    if not field:
        logger.info(
            "# [_resolve_expiry_for_relocated_entry] #%d (%s): sin "
            "fecha legible tras agotar heuristica/OCR/Gemini -- "
            "queda en blanco, atencion humana requerida.",
            entry.pk, entry.name,
        )
        return

    if field == "expiry":
        entry.expiry_date = found
        entry.save(update_fields=["expiry_date"])
    else:
        entry.issue_date = found
        entry.save(update_fields=["issue_date"])
        # H30 (S50): una fecha de EMISION no dispara alerta de
        # caducidad -- no hay "caducidad" que avisar (create_default_
        # expiry_alerts es literalmente eso, un aviso ANTES de que
        # algo caduque). Se guarda la fecha para vigencia_service,
        # pero no se crea ninguna alerta.
        logger.info(
            "# [_resolve_expiry_for_relocated_entry] #%d (%s): "
            "issue_date=%s resuelto (sin alerta -- no es fecha de "
            "caducidad).", entry.pk, entry.name, found,
        )
        return

    domain_obj = entry.domain_content_type.get_object_for_this_type(
        pk=entry.domain_object_id,
    )
    if isinstance(domain_obj, MachineAsset):
        subject_label = "%s -- %s" % (domain_obj.code, domain_obj.brand_model)
    else:
        subject_label = "%s %s, %s" % (
            domain_obj.first_surname, domain_obj.second_surname,
            domain_obj.given_name,
        )

    alerts = create_default_expiry_alerts(
        document=entry,
        expiry_date=entry.expiry_date,
        document_label=entry.document_type.label,
        subject_label=subject_label,
        company=Company.objects.first(),
    )
    contacts = get_docs_supervisor_contacts()
    for alert in alerts:
        alert.contacts.add(*contacts)
    logger.info(
        "# [_resolve_expiry_for_relocated_entry] #%d (%s): %s=%s "
        "resuelto, %d alerta(s) creada(s).",
        entry.pk, entry.name, field, found, len(alerts),
    )


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
    -- never a guess. **Extended S042 (decision 3.14, N=1 -- Miguel
    Ángel: "con que entre una vez y no se pueda clasificar ya es
    suficiente")**: everything else (identity/machine not resolved
    with certainty, a plain `DESCONOCIDO`, or even a technical
    classification error) gets exactly ONE pass through this task and
    then leaves `_CUARENTENA/` for real, moved (pure index write,
    `move_service.move_entry`, `blob_name` untouched) into the real
    "NO CONFORMES" folder and logged as `ACTION_SENT_TO_NO_CONFORMES`
    -- it never re-enters this task's query on its own again. A human
    with delete authority over that folder reviews it there, may leave
    a `curator_note` for the next Gemini attempt (read by
    `classify_entry`/`_build_prompt`), and requeues it back to
    `_CUARENTENA/` by hand via `RequeueNoConformesView` -- "sin
    ninguna relación con el estado de la cola" (Miguel Ángel).

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
    (`is_dossier`, S041 -- Miguel Ángel: "cuando tenemos la certeza
    de que es un dossier (...) hay que eliminarlo directamente") se
    reubican a la papelera de `_DOSSIER_TRASH_USERNAME` y quedan como
    `ACTION_TRASHED` -- nunca una sospecha. **Ampliado en S042
    (decisión 3.14, N=1 -- Miguel Ángel: "con que entre una vez y no
    se pueda clasificar ya es suficiente")**: todo lo demás (identidad
    /máquina sin resolver con certeza, un `DESCONOCIDO` simple, o
    incluso un error técnico de clasificación) recibe exactamente UNA
    pasada por esta tarea y a partir de ahí sale de verdad de
    `_CUARENTENA/`, movido (escritura de índice pura,
    `move_service.move_entry`, `blob_name` intacto) a la carpeta real
    "NO CONFORMES" y registrado como `ACTION_SENT_TO_NO_CONFORMES` --
    nunca vuelve a entrar solo en la consulta de esta tarea. Un humano
    con autoridad de borrado sobre esa carpeta lo revisa allí, puede
    dejar una `curator_note` para el siguiente intento de Gemini
    (leída por `classify_entry`/`_build_prompt`), y lo reencola a mano
    de vuelta a `_CUARENTENA/` vía `RequeueNoConformesView` -- "sin
    ninguna relación con el estado de la cola" (Miguel Ángel).
    """
    from document_explorer import classification_service, move_service
    from document_explorer.buckets import (
        NO_CONFORMES_PREFIX, PRIMARY_BUCKET, QUARANTINE_PREFIX,
        quarantine_scope_q,
    )
    from document_explorer.models import DocumentIndexEntry

    entries = list(
        DocumentIndexEntry.objects.filter(
            quarantine_scope_q(),
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
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

            # S042, Miguel Ángel: "no podemos nosotros borrar
            # nada... dotar al sistema de las herramientas
            # pertinentes para que lo haga de forma automática" --
            # misma directriz que la redundancia de comprimidos justo
            # debajo, aplicada aquí al caso más simple posible: un
            # archivo de 0 bytes no necesita ninguna llamada a Gemini
            # para confirmar que está vacío. Ver el docstring de
            # classification_service.is_empty_file() para el
            # incidente real que lo confirma. `result` cae al mismo
            # bloque compartido de más abajo (hints/detail/acción),
            # nunca duplicado aquí.
            # S043, Miguel Ángel, verbatim, tras un .log real de
            # spooler de impresión colado en cuarentena: "No debería
            # de enviarse a Gemini, hay que borrarlo." Ni siquiera
            # necesita el tamaño del archivo -- solo la extensión, así
            # que va antes que is_empty_file. Ver el docstring de
            # classification_service.is_known_junk_extension() para el
            # incidente real y por qué es deliberadamente más estrecho
            # que "Gemini no soporta este tipo".
            if classification_service.is_known_junk_extension(entry):
                trashed_ok = classification_service.trash_dossier_entry(
                    entry,
                )
                result = {
                    "domain": "N/A", "document_type_code": "N/A",
                    "confidence": "N/A",
                    "reasoning": (
                        "Extensión de archivo confirmada como basura "
                        "real (nunca documentación) -- eliminado "
                        "automáticamente, sin pasar por Gemini."
                    ),
                    "trashed": trashed_ok,
                    "trash_reason": "EXTENSIÓN BASURA ELIMINADA",
                    "relocated": False,
                }
            elif classification_service.is_empty_file(entry):
                trashed_ok = classification_service.trash_dossier_entry(
                    entry,
                )
                result = {
                    "domain": "N/A", "document_type_code": "N/A",
                    "confidence": "N/A",
                    "reasoning": (
                        "Archivo de 0 bytes -- eliminado "
                        "automáticamente, sin pasar por Gemini."
                    ),
                    "trashed": trashed_ok,
                    "trash_reason": "ARCHIVO VACÍO ELIMINADO",
                    "relocated": False,
                }
            elif classification_service.resolve_duplicate_of_filed_document(
                entry,
            ):
                # S042, Miguel Ángel, verbatim, tras el incidente real
                # de A-69 Leasing BBVA.pdf (142 pasadas, dos filas
                # vivas con el mismo CRC32C y tamaño, una ya archivada,
                # otra dando vueltas por cuarentena sin fin): "cuando
                # detecte un duplicado, borrarlo, el que se está
                # colando, y dejamos el que ya tenemos guardado... se
                # envía a la papelera." Ni CRC32C ni tamaño necesitan
                # descargar nada -- ya están en la propia fila. Ver el
                # docstring de resolve_duplicate_of_filed_document()
                # para el alcance exacto (nunca toca el panel de
                # Duplicados ni su propio flujo, solo cuarentena).
                trashed_ok = classification_service.trash_dossier_entry(
                    entry,
                )
                result = {
                    "domain": "N/A", "document_type_code": "N/A",
                    "confidence": "N/A",
                    "reasoning": (
                        "Duplicado exacto (mismo CRC32C y tamaño) de "
                        "un documento ya archivado fuera de cuarentena "
                        "-- eliminado automáticamente, sin pasar por "
                        "Gemini."
                    ),
                    "trashed": trashed_ok,
                    "trash_reason": "DUPLICADO YA ARCHIVADO ELIMINADO",
                    "relocated": False,
                }
            else:
                # S042, Miguel Ángel, verbatim, tras ver dos archivos
                # comprimidos reales cuyo contenido entero ya existía
                # archivado por separado: "no podemos nosotros
                # borrar nada... dotar al sistema de las
                # herramientas pertinentes para que lo haga de forma
                # automática." Se comprueba ANTES de Gemini -- nunca
                # puede leer bytes de un .zip/.rar (ver
                # classification_service._SUPPORTED_MIME_TYPES/
                # _LIBREOFFICE_CONVERTIBLE_EXTENSIONS/
                # _XPS_EXTENSIONS), así que intentarlo sería tiempo y
                # coste real tirados. Ver el docstring de
                # resolve_archive_redundancy() para el alcance exacto
                # (solo BORRA cuando el 100% del contenido ya existe;
                # con contenido genuinamente nuevo dentro se deja
                # para NO CONFORMES, extraer y subir eso como objetos
                # GCS nuevos es una decisión de infraestructura
                # aparte).
                redundancy = (
                    classification_service
                    .resolve_archive_redundancy(entry)
                )
                if redundancy is not None and redundancy["fully_redundant"]:
                    matched = redundancy["matched_paths"]
                    trashed_ok = (
                        classification_service.trash_dossier_entry(entry)
                    )
                    result = {
                        "domain": "N/A", "document_type_code": "N/A",
                        "confidence": "N/A",
                        "reasoning": (
                            "Archivo comprimido cuyo contenido entero "
                            "(%d archivo(s): %s) ya existe archivado "
                            "por separado -- Gemini no puede leer "
                            "bytes comprimidos, así que ni se ha "
                            "intentado."
                            % (len(matched), ", ".join(matched))
                        ),
                        "trashed": trashed_ok,
                        "trash_reason": "ARCHIVO REDUNDANTE ELIMINADO",
                        "relocated": False,
                    }
                elif redundancy is not None:
                    matched = redundancy["matched_paths"]
                    result = {
                        "error": (
                            "Archivo comprimido -- %d de sus archivos "
                            "ya existen archivados por separado (%s), "
                            "pero el resto es contenido nuevo. Gemini "
                            "no puede leer archivos comprimidos; "
                            "extraer y archivar lo nuevo requiere "
                            "revisión manual."
                            % (
                                len(matched),
                                ", ".join(matched)
                                if matched else "ninguno",
                            )
                        ),
                    }
                else:
                    result = (
                        classification_service
                        .apply_quarantine_classification(entry)
                    )

            if "error" in result:
                pending_count += 1
                action = DataOperationLogEntry.ACTION_SENT_TO_NO_CONFORMES
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
                person_note = result.get("person_identity_note")
                machine_note = result.get("machine_asset_note")
                detail = (
                    "Dominio: %s -- Tipo: %s (%s) -- %s%s%s%s%s"
                    % (
                        result.get("domain", "?"),
                        result.get("document_type_code", "?"),
                        result.get("confidence", "?"),
                        result.get("reasoning", ""),
                        " -- Pistas: %s" % hints if hints else "",
                        " -- %s" % mismatch if mismatch else "",
                        " -- %s" % person_note if person_note else "",
                        " -- %s" % machine_note if machine_note else "",
                    )
                )
                if result.get("relocated"):
                    relocated_count += 1
                    action = DataOperationLogEntry.ACTION_RELOCATED
                    _resolve_expiry_for_relocated_entry(entry)
                elif result.get("trashed"):
                    dossier_trashed_count += 1
                    action = DataOperationLogEntry.ACTION_TRASHED
                    detail = (
                        "[%s] " % result.get(
                            "trash_reason", "DOSSIER ELIMINADO",
                        )
                    ) + detail
                else:
                    pending_count += 1
                    action = DataOperationLogEntry.ACTION_SENT_TO_NO_CONFORMES

            if action == DataOperationLogEntry.ACTION_SENT_TO_NO_CONFORMES:
                # Decisión 3.14 (S041, ampliada S042), Miguel Ángel:
                # "con que entre una vez y no se pueda clasificar ya
                # es suficiente" -- N=1. `blob_name` no se toca
                # (move_entry es puntero puro, 4.12); el dominio real
                # se sigue leyendo de ahí, no de parent_path, así que
                # un reencolado posterior desde NO CONFORMES no pierde
                # la pista aunque este movimiento cambie parent_path.
                move_service.move_entry(
                    entry, NO_CONFORMES_PREFIX.rstrip("/"),
                )
                detail = "[A NO CONFORMES] " + detail

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


@app.task(base=DjangoTask, bind=True, max_retries=0)
def check_system_agents_task(self) -> None:
    """
    Every 5 minutes: WhatsApp alert when a system agent stops beating.

    ---

    H30 (S123), punto 7. Cada 5 minutos: alerta por WhatsApp cuando un
    agente de sistema (H28) lleva más de 15 minutos sin latido, una vez
    por caída, y aviso al recuperarse -- ver
    `system_agent_service.check_agents`.
    """
    from .system_agent_service import check_agents

    check_agents()
