# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_albaranes.py
"""
Upload of the workers' albaranes compared with their clock-ins, new UI.

---

Carga de albaranes cotejados con los fichajes por la IA en la nueva
interfaz (S163), copiado de panel/views_clock_albaranes.py (S149): el
navegador sube la carpeta archivo a archivo (`start`, `file`, `finish`)
y la lectura va en segundo plano (Celery, Gemini); `status` dice cómo
va. Una sola carga para los dos casos de la antigua: de la persona
abierta (person_pk) o de varios (cada albarán va al trabajador del
nombre leído, entre los marcados o, sin marcados, entre los que fichan
por tipos). `batches`: las cargas recientes; `sheet`: el archivo de un
albarán, para comprobar lo que leyó la IA.
"""
import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.models import AlbaranBatch, AlbaranSheet, ClockEvent
from new_ui import clock_core
from new_ui.mixins import SuperuserRequiredMixin

MAX_FILES = 200
RECENT = 8


def uses_albaranes(person):
    """Whether the worker clocks by types (the albaranes are for them)."""
    from hr_calendar.clock_settings import uses_types

    company_user = person.company_user
    return company_user is not None and uses_types(
        company_user, datetime.date.today())


def albaranes_by_day(person, date_from, date_to):
    """
    {day: [read albaranes]} of a worker between two dates.

    ---

    Los albaranes leídos de cada día (el último leído de cada número,
    por si se cargó dos veces), para la tabla de jornadas.
    """
    result, seen = {}, set()
    for sheet in AlbaranSheet.objects.filter(
            person=person, day__gte=date_from, day__lte=date_to,
            status=AlbaranSheet.Status.READ,
    ).order_by("-batch__created_at", "pk"):
        key = (sheet.day, sheet.number or "#%d" % sheet.pk)
        if key in seen:
            continue
        seen.add(key)
        result.setdefault(sheet.day, []).append(sheet)
    for items in result.values():
        items.sort(key=lambda s: (s.base_out or s.work_in
                                  or datetime.time.min))
    return result


def _error(message):
    return JsonResponse({"error": message}, status=400)


def _batch(request, batch_id):
    batch = AlbaranBatch.objects.filter(
        pk=batch_id, company=request.user.company_user.company).first()
    if batch is None:
        raise Http404("Carga de albaranes no encontrada.")
    return batch


def _candidates(request):
    """
    The marked people (General) or the people of the marked presses.

    ---

    Las personas marcadas (General y demás vistas de personas) o las de
    los fichajes marcados (vista Fichajes).
    """
    company = request.user.company_user.company
    ids = [int(v) for v in request.POST.get("selected", "").split(",")
           if v.isdigit()]
    if not ids:
        return []
    if request.POST.get("tab") == "fichajes":
        users = set(ClockEvent.objects.filter(
            company=company, pk__in=ids).values_list(
            "company_user_id", flat=True))
        return list(PersonIdentity.objects.filter(
            company=company, company_user_id__in=users).values_list(
            "pk", flat=True))
    return list(PersonIdentity.objects.filter(
        company=company, pk__in=ids).values_list("pk", flat=True))


class AlbaranStartView(SuperuserRequiredMixin, View):
    """
    POST `count`, `folder`, `mode` (person | many): start an upload.

    ---

    POST: crea la carga. «person»: de la persona abierta (person_pk),
    que tiene que fichar por tipos. «many»: de varios, entre los
    marcados o, sin marcados, entre los que fichan por tipos.
    """

    def post(self, request):
        try:
            count = int(request.POST.get("count") or 0)
        except ValueError:
            count = 0
        if not 0 < count <= MAX_FILES:
            return _error("Elige una carpeta con entre 1 y %d archivos."
                          % MAX_FILES)
        company = request.user.company_user.company
        folder = (request.POST.get("folder") or "")[:255]
        if request.POST.get("mode") == "person":
            person = PersonIdentity.objects.filter(
                pk=request.POST.get("person_pk") or 0).select_related(
                "company_user").first()
            if person is None:
                return _error("Abre primero a la persona.")
            if not uses_albaranes(person):
                return _error("Este trabajador no ficha por tipos: los "
                              "albaranes no se cotejan.")
            batch = AlbaranBatch.objects.create(
                company=company, person=person, folder_name=folder,
                created_by=request.user.company_user)
        else:
            batch = AlbaranBatch.objects.create(
                company=company, person=None,
                candidate_ids=_candidates(request), folder_name=folder,
                created_by=request.user.company_user)
        return JsonResponse({"batch": batch.pk})


class AlbaranFileView(SuperuserRequiredMixin, View):
    """POST: one file of the folder (not PDF nor photo: skipped)."""

    def post(self, request, batch_id):
        from hr_calendar.albaran_check import AlbaranError, stage_file

        batch = _batch(request, batch_id)
        if batch.status != AlbaranBatch.Status.UPLOADING:
            return _error("Esta carga ya se ha cerrado.")
        upload = request.FILES.get("file")
        if upload is None:
            return _error("No ha llegado el archivo.")
        try:
            stage_file(batch, upload.name, upload.read())
        except AlbaranError as exc:
            return JsonResponse({"skipped": str(exc)})
        return JsonResponse({"ok": True})


class AlbaranFinishView(SuperuserRequiredMixin, View):
    """POST: the upload is complete; read it in the background."""

    def post(self, request, batch_id):
        from hr_calendar.tasks import read_albaran_batch_task

        batch = _batch(request, batch_id)
        if not batch.sheets.exists():
            batch.status = AlbaranBatch.Status.CANCELLED
            batch.error = "Ningún archivo válido."
            batch.save(update_fields=["status", "error"])
            return _error("Ningún archivo era un PDF o una foto.")
        updated = AlbaranBatch.objects.filter(
            pk=batch.pk, status=AlbaranBatch.Status.UPLOADING,
        ).update(status=AlbaranBatch.Status.READING)
        if updated:
            transaction.on_commit(
                lambda: read_albaran_batch_task.delay(batch.pk))
        return JsonResponse({"ok": True})


class AlbaranStatusView(SuperuserRequiredMixin, View):
    """
    GET: how an upload is going (worker by worker if it is of many).

    ---

    GET: cómo va una carga; si es de varios, trabajador a trabajador y
    los albaranes que no se pudieron dar a nadie.
    """

    def get(self, request, batch_id):
        batch = _batch(request, batch_id)
        sheets = list(batch.sheets.all())
        first_files = [s for s in sheets if s.position == 1]
        data = {
            "status": batch.status,
            "status_label": batch.get_status_display(),
            "files": len(first_files),
            "read": sum(1 for s in first_files
                        if s.status != AlbaranSheet.Status.PENDING),
            "albaranes": sum(1 for s in sheets
                             if s.status == AlbaranSheet.Status.READ),
            "unreadable": [
                "%s: %s" % (s.original_name,
                            s.note or s.get_status_display())
                for s in sheets if s.status in (
                    AlbaranSheet.Status.UNREADABLE,
                    AlbaranSheet.Status.ERROR)],
            "mismatch": sorted({s.operator_name for s in sheets
                                if s.name_mismatch}),
            "days": batch.day_checks.count(),
            "corrected": batch.day_checks.filter(corrected=True).count(),
            "error": batch.error,
            "people": [],
            "no_person": [],
        }
        if batch.person_id is None:
            people = {}
            for sheet in batch.sheets.filter(
                    status=AlbaranSheet.Status.READ,
                    person__isnull=False).select_related("person"):
                item = people.setdefault(sheet.person_id, {
                    "name": clock_core._person_label(sheet.person),
                    "albaranes": 0})
                item["albaranes"] += 1
            checks = {}
            for check in batch.day_checks.all():
                entry = checks.setdefault(check.company_user_id, [0, 0])
                entry[0] += 1
                entry[1] += int(check.corrected)
            users = dict(PersonIdentity.objects.filter(
                pk__in=people).values_list("pk", "company_user_id"))
            for pk, item in people.items():
                item["days"], item["corrected"] = checks.get(
                    users.get(pk), [0, 0])
            data["people"] = sorted(people.values(),
                                    key=lambda i: i["name"])
            data["no_person"] = [
                "%s: %s" % (s.original_name, s.note)
                for s in batch.sheets.filter(
                    status=AlbaranSheet.Status.NO_PERSON)]
        return JsonResponse(data)


class AlbaranBatchesView(SuperuserRequiredMixin, View):
    """
    GET: the recent uploads (of one person, or all) with their progress.

    ---

    GET: las cargas recientes (de la persona abierta, o todas) con su
    avance o su resultado; el bloque las vuelve a pedir cada poco
    mientras haya alguna leyéndose.
    """

    def get(self, request):
        Status = AlbaranSheet.Status
        batches = AlbaranBatch.objects.filter(
            company=request.user.company_user.company,
        ).exclude(status=AlbaranBatch.Status.CANCELLED)
        person_pk = request.GET.get("person_pk") or ""
        if person_pk.isdigit():
            batches = batches.filter(person_id=int(person_pk))
        batches = list(batches.annotate(
            files=Count("sheets", distinct=True,
                        filter=Q(sheets__position=1)),
            pending=Count("sheets", distinct=True,
                          filter=Q(sheets__position=1,
                                   sheets__status=Status.PENDING)),
            read_count=Count("sheets", distinct=True,
                             filter=Q(sheets__status=Status.READ)),
            no_person=Count("sheets", distinct=True, filter=Q(
                sheets__status=Status.NO_PERSON)),
            failed=Count("sheets", distinct=True,
                         filter=Q(sheets__status__in=(
                             Status.UNREADABLE, Status.ERROR))),
            days=Count("day_checks", distinct=True),
            corrected=Count("day_checks", distinct=True,
                            filter=Q(day_checks__corrected=True)),
        ).select_related("created_by__user", "person").order_by(
            "-created_at")[:RECENT])
        for batch in batches:
            batch.done = batch.files - batch.pending
            batch.by = (clock_core._user_label(batch.created_by)
                        if batch.created_by else "")
            batch.who = (clock_core._person_label(batch.person)
                         if batch.person else "Varios")
        return render(request, "new_ui/_albaran_batches.html", {
            "batches": batches,
            "busy": any(b.status in (AlbaranBatch.Status.UPLOADING,
                                     AlbaranBatch.Status.READING)
                        for b in batches),
        })


class AlbaranSheetFileView(SuperuserRequiredMixin, View):
    """GET: the file an albarán came in (to check what the AI read)."""

    def get(self, request, sheet_id):
        from hr_calendar.albaran_check import (
            AlbaranError, _staged_abs, mime_of,
        )

        sheet = AlbaranSheet.objects.filter(
            pk=sheet_id,
            batch__company=request.user.company_user.company,
        ).first()
        if sheet is None:
            raise Http404("Albarán no encontrado.")
        try:
            handle = open(_staged_abs(sheet.staged_path), "rb")
        except (AlbaranError, OSError):
            raise Http404("El archivo del albarán ya no está.")
        mime = mime_of(handle.read(8)) or "application/octet-stream"
        handle.seek(0)
        response = FileResponse(handle, content_type=mime)
        response["Content-Disposition"] = 'inline; filename="%s"' % (
            sheet.original_name.replace('"', ""))
        response["X-Content-Type-Options"] = "nosniff"
        return response
