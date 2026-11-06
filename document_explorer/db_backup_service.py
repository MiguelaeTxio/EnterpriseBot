# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/db_backup_service.py
"""
Database backups (H24, S146): dump, retention and the H28 agent side.

The server dumps MySQL with `mysqldump` and streams it, gzip-compressed,
straight into a GCS object: nothing is written to the PythonAnywhere
disk (5 GB quota). The H28 agent downloads each copy to a dedicated
OneDrive folder, checks the SHA-256 and reports back. Retention: the
latest 14 daily copies, one per week for 8 weeks (the Sunday one) and
one per month for 12 months (the day-1 one). The bucket is only a
transit: it keeps the 3 latest copies already in OneDrive.

---

Copias de seguridad de la base de datos (H24, S146).

Miguel Ángel: "copiar todo lo que tenemos en base de datos [...] el
formato más conveniente para que quede todo comprimido y que podamos
recuperarlo en cualquier momento"; frecuencia elegida: "Diaria y
escalonada" (14 diarias, 8 semanales, 12 mensuales). Antes de
construir preguntó dónde se hacía el volcado, por la cuota de disco del
servidor: por eso el volcado va por tubería de `mysqldump` a la
compresión y de ahí al cubo, sin archivo intermedio. Restaurar:
`gunzip -c EnterpriseBot_BD_AAAAMMDD_HHMM.sql.gz | mysql <base>`.
"""
import hashlib
import logging
import re
import subprocess
import time
import zlib

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.utils import timezone

from spare_parts.gcs_service import ensure_bucket, get_storage_client

from .models import DatabaseBackup

logger = logging.getLogger(__name__)

# Cubo propio, separado de `cgs_grupo_alvarez`: el explorador del panel
# nunca puede listar ni indexar una copia de la BD.
# ---
# Own bucket, apart from `cgs_grupo_alvarez`: the panel explorer can
# never list or index a database copy.
BACKUP_BUCKET = "enterprisebot-alvarez-db-backups"
FILE_NAME_FORMAT = "EnterpriseBot_BD_%Y%m%d_%H%M.sql.gz"
FILE_NAME_RE = re.compile(r"^EnterpriseBot_BD_\d{8}_\d{4}\.sql\.gz$")
LOCAL_FOLDER_NAME = "COPIAS DE SEGURIDAD BD"
CHUNK_BYTES = 1024 * 1024
DUMP_END_MARKER = b"-- Dump completed"

KEEP_DAILY = 14
KEEP_WEEKLY = 8
KEEP_MONTHLY = 12
KEEP_IN_BUCKET = 3

# Tablas de control de la restauración de prueba (hoja de ruta S146).
# ---
# Control tables for the test restore (S146 roadmap).
CONTROL_MODELS = (
    "document_explorer.PersonIdentity",
    "document_explorer.DocumentIndexEntry",
    "hr_calendar.ClockEvent",
)


def _control_counts():
    """Exact row count of each control table, by table name.
    ---
    Filas exactas de cada tabla de control (COUNT(*) directo, sin
    gestores que filtren).
    """
    counts = {}
    with connection.cursor() as cursor:
        for label in CONTROL_MODELS:
            table = apps.get_model(label)._meta.db_table
            cursor.execute("SELECT COUNT(*) FROM `%s`" % table)
            counts[table] = cursor.fetchone()[0]
    return counts


def _dump_command():
    db = settings.DATABASES["default"]
    # La contraseña la toma mysqldump de ~/.my.cnf, que mantiene
    # PythonAnywhere (comprobado con EnterpriseBot_001.txt en S146).
    return [
        "mysqldump",
        "-u", db["USER"],
        "-h", db["HOST"],
        "--single-transaction", "--routines", "--triggers", "--events",
        "--set-gtid-purged=OFF", "--no-tablespaces",
        "--column-statistics=0",
        db["NAME"],
    ]


def _stream_dump_to_blob(blob):
    """Run mysqldump and stream its gzip output into the blob.
    ---
    Ejecuta mysqldump y vuelca su salida comprimida en gzip al objeto,
    trozo a trozo. Devuelve (comprimido, sin_comprimir, sha256). Lanza
    RuntimeError si mysqldump falla o el volcado no termina con su
    línea final.
    """
    digest = hashlib.sha256()
    compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
    raw_bytes = 0
    gz_bytes = 0
    tail = b""
    process = subprocess.Popen(
        _dump_command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    with blob.open("wb", content_type="application/gzip") as out:
        def _write(data):
            nonlocal gz_bytes
            if data:
                digest.update(data)
                out.write(data)
                gz_bytes += len(data)

        while True:
            chunk = process.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            raw_bytes += len(chunk)
            tail = (tail + chunk)[-200:]
            _write(compressor.compress(chunk))
        _write(compressor.flush())
        stderr = process.stderr.read().decode("utf-8", "replace")
        code = process.wait()
        if code != 0:
            raise RuntimeError(
                "mysqldump salió con %s: %s" % (code, stderr.strip()[:900]))
        if DUMP_END_MARKER not in tail:
            raise RuntimeError(
                "el volcado no termina con '-- Dump completed'")
    return gz_bytes, raw_bytes, digest.hexdigest()


def run_backup():
    """Take one full copy. Returns the DatabaseBackup row.
    ---
    Hace una copia completa: filas de control antes, volcado al cubo,
    filas de control después. Si algo falla, la copia queda "Fallida"
    con su error y el objeto a medias se borra del cubo.
    """
    started = timezone.localtime()
    # El nombre lleva el minuto: si ya hay una copia en este minuto
    # (copia en el momento justo antes de restaurar), se espera al
    # siguiente.
    while DatabaseBackup.objects.filter(
            file_name=started.strftime(FILE_NAME_FORMAT)).exists():
        time.sleep(61 - started.second)
        started = timezone.localtime()
    backup = DatabaseBackup.objects.create(
        file_name=started.strftime(FILE_NAME_FORMAT),
        started_at=started,
    )
    backup.blob_name = backup.file_name
    try:
        client = get_storage_client()
        bucket = ensure_bucket(client, BACKUP_BUCKET)
        blob = bucket.blob(backup.blob_name)
        before = _control_counts()
        size, raw, sha = _stream_dump_to_blob(blob)
        after = _control_counts()
    except Exception as error:  # noqa: BLE001 -- se guarda y se avisa
        logger.exception("# [db_backup] Fallo en %s", backup.file_name)
        backup.status = DatabaseBackup.STATUS_FAILED
        backup.error = str(error)[:2000]
        backup.finished_at = timezone.now()
        backup.save()
        try:
            get_storage_client().bucket(BACKUP_BUCKET).blob(
                backup.blob_name).delete()
        except Exception:  # noqa: BLE001 -- puede no existir
            pass
        return backup
    backup.status = DatabaseBackup.STATUS_READY
    backup.size_bytes = size
    backup.uncompressed_bytes = raw
    backup.sha256 = sha
    backup.row_counts = {"antes": before, "despues": after}
    backup.finished_at = timezone.now()
    backup.save()
    logger.info(
        "# [db_backup] %s lista: %d bytes (%d sin comprimir), sha256 %s",
        backup.file_name, size, raw, sha,
    )
    prune_bucket()
    return backup


def keep_names():
    """File names that must stay in OneDrive (daily, weekly, monthly).
    ---
    Nombres que se quedan en OneDrive: la última copia de cada uno de
    los 14 días más recientes, la última de cada una de las 8 semanas
    más recientes (la del domingo) y la primera de cada uno de los 12
    meses más recientes (la del día 1). Además, toda copia que todavía
    no se haya bajado.
    """
    copies = list(DatabaseBackup.objects.filter(status__in=(
        DatabaseBackup.STATUS_READY, DatabaseBackup.STATUS_DOWNLOADED,
    ), removed_from_local_at__isnull=True).order_by("-started_at"))
    keep = {c.file_name for c in copies
            if c.status == DatabaseBackup.STATUS_READY}
    days, weeks, months = {}, {}, {}
    for copy in copies:
        local = timezone.localtime(copy.started_at)
        days.setdefault(local.date(), copy)
        weeks.setdefault(local.isocalendar()[:2], copy)
        # Orden descendente: la última que se ve de un mes es la
        # primera del mes.
        months[(local.year, local.month)] = copy
    for group, limit in ((days, KEEP_DAILY), (weeks, KEEP_WEEKLY),
                         (months, KEEP_MONTHLY)):
        for key in sorted(group, reverse=True)[:limit]:
            keep.add(group[key].file_name)
    return sorted(keep)


def prune_bucket():
    """Keep in the bucket only the 3 latest copies already in OneDrive.
    ---
    El cubo es solo de paso: se quedan las 3 últimas copias ya bajadas
    a OneDrive. Una copia que todavía no se ha bajado nunca se borra
    del cubo.
    """
    downloaded = DatabaseBackup.objects.filter(
        status=DatabaseBackup.STATUS_DOWNLOADED,
        removed_from_bucket_at__isnull=True,
    ).order_by("-started_at")
    stale = list(downloaded[KEEP_IN_BUCKET:])
    if not stale:
        return
    bucket = get_storage_client().bucket(BACKUP_BUCKET)
    for copy in stale:
        try:
            bucket.blob(copy.blob_name).delete()
        except Exception as error:  # noqa: BLE001
            if "404" not in str(error):
                logger.warning("# [db_backup] No se pudo quitar %s: %s",
                               copy.blob_name, error)
                continue
        copy.removed_from_bucket_at = timezone.now()
        copy.save(update_fields=["removed_from_bucket_at"])


def agent_payload():
    """What the H28 agent has to do: copies to download and to keep.
    ---
    Lo que pide el agente: copias pendientes de bajar, nombres que se
    quedan en OneDrive y el nombre de la carpeta.
    """
    pending = DatabaseBackup.objects.filter(
        status=DatabaseBackup.STATUS_READY,
    ).order_by("started_at")
    return {
        "folder_name": LOCAL_FOLDER_NAME,
        "pending": [{
            "id": copy.pk, "file_name": copy.file_name,
            "size": copy.size_bytes, "sha256": copy.sha256,
        } for copy in pending],
        "keep": keep_names(),
    }


def open_blob(backup):
    """Readable stream of the copy in the bucket.
    ---
    Lectura del objeto de la copia en el cubo, para servírselo al
    agente.
    """
    return get_storage_client().bucket(BACKUP_BUCKET).blob(
        backup.blob_name).open("rb")


def report_download(backup, sha256, local_path, host):
    """The agent has the copy in OneDrive; check its SHA-256.
    ---
    El agente ya tiene la copia en OneDrive. Solo se da por bajada si su
    SHA-256 coincide con el del volcado. Devuelve el texto de error, o
    "" si todo cuadra.
    """
    if sha256 != backup.sha256:
        backup.error = "SHA-256 distinto en OneDrive: %s" % sha256
        backup.save(update_fields=["error"])
        return backup.error
    backup.status = DatabaseBackup.STATUS_DOWNLOADED
    backup.downloaded_at = timezone.now()
    backup.local_path = local_path[:2000]
    backup.host = host[:255]
    backup.error = ""
    backup.save()
    prune_bucket()
    return ""


def report_removed(names):
    """Mark the copies the agent removed from OneDrive by retention.
    ---
    Marca las copias que el agente ha quitado de OneDrive por la
    retención. Devuelve cuántas.
    """
    valid = [name for name in names if FILE_NAME_RE.match(name)]
    return DatabaseBackup.objects.filter(
        file_name__in=valid, removed_from_local_at__isnull=True,
    ).update(removed_from_local_at=timezone.now())


def _restore_command():
    db = settings.DATABASES["default"]
    return ["mysql", "-u", db["USER"], "-h", db["HOST"], db["NAME"]]


def _stream_blob_to_mysql(backup):
    """Feed the copy, decompressed on the fly, into mysql.
    ---
    Lee la copia del cubo, la descomprime por trozos y se la pasa a
    `mysql`; nada pasa por el disco del servidor. Lanza RuntimeError si
    mysql falla.
    """
    decompressor = zlib.decompressobj(31)
    process = subprocess.Popen(
        _restore_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        with open_blob(backup) as handle:
            while True:
                chunk = handle.read(CHUNK_BYTES)
                if not chunk:
                    break
                process.stdin.write(decompressor.decompress(chunk))
            process.stdin.write(decompressor.flush())
    except BrokenPipeError:
        pass
    finally:
        process.stdin.close()
    stderr = process.stderr.read().decode("utf-8", "replace")
    code = process.wait()
    if code != 0:
        raise RuntimeError(
            "mysql salió con %s: %s" % (code, stderr.strip()[:900]))


def restore_backup(backup_pk, username):
    """Restore one copy over the production database.
    ---
    Restaura una copia sobre la base de datos de producción (solo
    administradores, desde el panel). Pasos:

    1. Copia de seguridad del estado actual (si falla, no se restaura).
    2. Se guarda el registro de copias (esta tabla también va en el
       volcado: restaurar una copia antigua borraría las posteriores).
    3. La copia elegida se vuelca en MySQL por tubería desde el cubo.
    4. Se repone el registro de copias y se aplican las migraciones que
       falten (si la copia es anterior a alguna).
    Devuelve el texto de error, o "" si ha ido bien.
    """
    backup = DatabaseBackup.objects.get(pk=backup_pk)
    backup.restore_status = DatabaseBackup.RESTORE_RUNNING
    backup.restore_requested_by = username[:150]
    backup.restore_started_at = timezone.now()
    backup.restore_finished_at = None
    backup.restore_error = ""
    backup.restore_safety_copy = ""
    backup.save()
    safety = run_backup()
    if safety.status != DatabaseBackup.STATUS_READY:
        error = "No se restaura: falló la copia previa (%s)" % safety.error
        DatabaseBackup.objects.filter(pk=backup_pk).update(
            restore_status=DatabaseBackup.RESTORE_FAILED,
            restore_finished_at=timezone.now(), restore_error=error[:2000],
            restore_safety_copy=safety.file_name,
        )
        return error
    DatabaseBackup.objects.filter(pk=backup_pk).update(
        restore_safety_copy=safety.file_name)
    registry = list(DatabaseBackup.objects.values())
    error = ""
    try:
        _stream_blob_to_mysql(backup)
    except Exception as exc:  # noqa: BLE001 -- se guarda y se avisa
        logger.exception("# [db_backup] Fallo restaurando %s",
                         backup.file_name)
        error = str(exc)[:2000]
    close_old_connections()
    try:
        call_command("migrate", interactive=False, verbosity=0)
    except Exception as exc:  # noqa: BLE001
        logger.exception("# [db_backup] Fallo en migrate tras restaurar")
        error = (error + " | migrate: %s" % exc)[:2000]
    DatabaseBackup.objects.all().delete()
    DatabaseBackup.objects.bulk_create(
        [DatabaseBackup(**row) for row in registry])
    DatabaseBackup.objects.filter(pk=backup_pk).update(
        restore_status=(DatabaseBackup.RESTORE_FAILED if error
                        else DatabaseBackup.RESTORE_DONE),
        restore_finished_at=timezone.now(), restore_error=error,
    )
    logger.info("# [db_backup] Restauración de %s: %s", backup.file_name,
                error or "correcta")
    return error
