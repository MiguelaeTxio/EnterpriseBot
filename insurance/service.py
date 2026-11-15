# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/service.py
"""
Running an insurance report: reading the documents in chunks and
building the data.

---

Hacer un informe de seguros en segundo plano: leer los documentos que
faltan por tandas cortas (la tarea se vuelve a encolar sola para no
tener ocupado el worker de Celery una hora seguida; el resto de tareas
pasan entre tanda y tanda) y, cuando están todos, montar el informe.
"""
import datetime
import hashlib
import logging
import time

from django.db import transaction
from django.utils import timezone

from insurance import builder
from insurance import companies
from insurance import ledger as ledger_reader
from insurance import readings
from insurance.models import InsuranceLedger
from insurance.models import InsuranceReport

logger = logging.getLogger(__name__)

CHUNK_SECONDS = 150
# Copia de los PDF del mayor: prefijo interno (como _BANDEJA_ENTRADA),
# nunca indexado en el explorador; son datos de contabilidad.
LEDGER_PREFIX = "_SEGUROS_LIBROS_MAYORES/"


class InsuranceError(Exception):
    """
    A user-facing error of the insurance tab.
    ---
    Error para mostrar al usuario en la pestaña Seguros.
    """


def _log(report, text):
    line = "[%s] %s" % (timezone.localtime().strftime("%d/%m %H:%M:%S"),
                        text)
    logger.info("# [insurance %s] %s", report.pk, text)
    InsuranceReport.objects.filter(pk=report.pk).update(
        log=(report.log + line + "\n")[-60000:], progress_text=text[:255])
    report.log = (report.log + line + "\n")[-60000:]


def save_ledger(upload_name, pdf_bytes, company_user):
    """
    Read and store one uploaded ledger PDF (same PDF twice = same row).
    ---
    Lee y guarda un PDF del mayor subido. Si ya se subió el mismo PDF
    (misma huella), devuelve el que ya estaba. El PDF se guarda en el
    cubo, en un prefijo interno que no se ve en el explorador.
    """
    from spare_parts.gcs_service import upload_bytes

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    existing = InsuranceLedger.objects.filter(sha256=digest).first()
    if existing is not None:
        return existing, False
    try:
        parsed = ledger_reader.parse(pdf_bytes)
    except ledger_reader.LedgerError as exc:
        raise InsuranceError("%s: %s" % (upload_name, exc)) from exc
    bucket = _bucket()
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    blob_name = "%s%s_%s_%s" % (LEDGER_PREFIX, parsed["company"] or "SIN",
                                stamp, _safe(upload_name))
    upload_bytes(bucket, blob_name, pdf_bytes, "application/pdf")
    ledger = InsuranceLedger.objects.create(
        company_code=parsed["company"],
        original_name=upload_name[:255],
        sha256=digest,
        bucket=bucket,
        blob_name=blob_name,
        date_from=_iso(parsed["date_from"]),
        date_to=_iso(parsed["date_to"]),
        printed_at=_iso(parsed["printed_at"]),
        entries=parsed["entries"],
        entry_count=len(parsed["entries"]),
        total=parsed["total"],
        uploaded_by=company_user,
    )
    return ledger, True


def _bucket():
    from document_explorer.buckets import PRIMARY_BUCKET

    return PRIMARY_BUCKET


def _safe(name):
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[-120:]


def _iso(text):
    try:
        return datetime.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def create_report(company_user, month_from, month_to, company_codes,
                  ledger_ids, title=""):
    """
    Create a queued report and start it.
    ---
    Crea el informe en cola y lo lanza en segundo plano.
    """
    from insurance.tasks import run_insurance_report_task

    if month_to and month_to < month_from:
        raise InsuranceError("El mes «hasta» es anterior al «desde».")
    codes = [c for c in company_codes if c in companies.LABELS]
    report = InsuranceReport.objects.create(
        title=title.strip()[:200] or default_title(month_from, month_to,
                                                   codes),
        month_from=month_from, month_to=month_to, companies=codes,
        created_by=company_user,
    )
    ledgers = list(InsuranceLedger.objects.filter(pk__in=ledger_ids))
    report.ledgers.set(ledgers)
    transaction.on_commit(
        lambda: run_insurance_report_task.delay(report.pk))
    return report


MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def month_label(day):
    """
    "noviembre 2026".
    ---
    Nombre del mes y año.
    """
    return "%s %s" % (MONTHS[day.month - 1], day.year) if day else ""


def due_label(report):
    """
    "Desde noviembre 2026" or "Noviembre 2026 – enero 2027".
    ---
    Texto del mes de vencimiento de un informe.
    """
    if report.month_to and report.month_to == report.month_from:
        return month_label(report.month_from).capitalize()
    if report.month_to:
        return "%s – %s" % (month_label(report.month_from).capitalize(),
                            month_label(report.month_to))
    return "Desde %s" % month_label(report.month_from)


def default_title(month_from, month_to, codes):
    """
    Title when none is typed.
    ---
    Título si no se escribe ninguno.
    """
    holder = type("R", (), {"month_from": month_from,
                            "month_to": month_to})
    who = ", ".join(companies.label(c) for c in codes) or (
        "todas las empresas")
    return "Seguros que vencen %s · %s" % (
        due_label(holder).lower(), who)


def run_step(report_id):
    """
    One step of a report; returns True when another step is needed.
    ---
    Un paso del informe: lee documentos durante CHUNK_SECONDS y, si ya
    no queda ninguno, monta el informe. Devuelve True si hace falta otro
    paso (la tarea se vuelve a encolar).
    """
    report = InsuranceReport.objects.filter(pk=report_id).first()
    if report is None or not report.is_live:
        return False
    try:
        entries = readings.candidates(report.month_from)
        todo = readings.pending(entries)
        total = len(entries)
        if todo:
            if report.status != InsuranceReport.Status.READING:
                report.status = InsuranceReport.Status.READING
                report.save(update_fields=["status"])
                _log(report, "%d documentos de seguro; faltan por leer "
                             "%d." % (total, len(todo)))
            _read_chunk(report, todo, total)
            return True
        report.status = InsuranceReport.Status.BUILDING
        report.progress_done = report.progress_total = total
        report.save(update_fields=["status", "progress_done",
                                   "progress_total"])
        _log(report, "Documentos leídos. Montando el informe.")
        data = builder.build(
            entries, list(report.ledgers.all()), report.month_from,
            report.month_to, report.companies,
            today=timezone.localdate(),
            classify=readings.classify_ledger_groups)
        records = data["records"]
        report.data = data
        report.policy_count = len(records)
        report.premium_total = round(sum(r["premium"] or 0
                                         for r in records), 2)
        report.alert_count = sum(1 for r in records if r["alerts"])
        report.status = InsuranceReport.Status.DONE
        report.finished_at = timezone.now()
        report.save()
        _log(report, "Terminado: %d seguros, %d con avisos." % (
            report.policy_count, report.alert_count))
        return False
    except Exception as exc:  # noqa: BLE001 -- se muestra en la lista
        logger.exception("# [insurance %s] error", report_id)
        report.status = InsuranceReport.Status.ERROR
        report.error = str(exc)[:2000]
        report.finished_at = timezone.now()
        report.save(update_fields=["status", "error", "finished_at"])
        _log(report, "Error: %s" % str(exc)[:200])
        return False


def _read_chunk(report, todo, total):
    from ai_services.gemini_client import get_gemini_client
    from spare_parts.gcs_service import get_storage_client

    storage = get_storage_client()
    client = get_gemini_client()
    start = time.monotonic()
    done_now = errors = 0
    for entry in todo:
        _data, error = readings.read(entry, storage, client)
        done_now += 1
        errors += bool(error)
        if time.monotonic() - start > CHUNK_SECONDS:
            break
    left = len(todo) - done_now
    elapsed = time.monotonic() - start
    eta = timezone.localtime() + datetime.timedelta(
        seconds=elapsed / max(done_now, 1) * left * 1.1)
    report.progress_total = total
    report.progress_done = total - left
    report.save(update_fields=["progress_done", "progress_total"])
    _log(report, "Leídos %d de %d documentos (%d con error en esta tanda)"
                 "%s." % (total - left, total, errors,
                          "; fin aprox. %s" % eta.strftime("%H:%M")
                          if left else ""))


def retry(report):
    """
    Rebuild a report (same months, companies and ledgers).
    ---
    Vuelve a hacer un informe con los mismos meses, empresas y libros
    mayores (lee solo los documentos nuevos o cambiados).
    """
    from insurance.tasks import run_insurance_report_task

    report.status = InsuranceReport.Status.QUEUED
    report.error = ""
    report.data = None
    report.finished_at = None
    report.progress_done = 0
    report.save()
    _log(report, "Vuelto a lanzar.")
    transaction.on_commit(
        lambda: run_insurance_report_task.delay(report.pk))
