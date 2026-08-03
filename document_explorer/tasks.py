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
