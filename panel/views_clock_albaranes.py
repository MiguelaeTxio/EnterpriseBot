# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_clock_albaranes.py
"""
Upload of a worker's albaranes, compared with his clock-ins by AI (S149).

---

Carga de albaranes desde la página de fichajes del trabajador (H24,
S149, sesión invasora). El navegador sube la carpeta archivo a archivo
(barra de progreso): `start` crea la carga, `file` guarda cada PDF o
foto, `finish` la manda a leer a Celery (Gemini) y `status` dice cómo
va. `sheet` enseña el archivo de un albarán, para comprobar lo que leyó
la IA al visar. Solo para trabajadores que fichan por tipos.
"""
import datetime

from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.views import View

from panel.mixins import SupervisorAccessMixin

MAX_FILES = 200


def _person(pk):
    from panel.views_clock_events import _person_or_404

    return _person_or_404(pk)


def uses_albaranes(person):
    """Whether the worker clocks by types (the albaranes are for them)."""
    from hr_calendar.clock_settings import uses_types

    company_user = person.company_user
    return company_user is not None and uses_types(
        company_user, datetime.date.today())


def _batch(request, person, batch_id):
    from hr_calendar.models import AlbaranBatch

    batch = AlbaranBatch.objects.filter(
        pk=batch_id, person=person,
        company=request.user.company_user.company,
    ).first()
    if batch is None:
        raise Http404("Carga de albaranes no encontrada.")
    return batch


class AlbaranStartView(SupervisorAccessMixin, View):
    """POST: start an upload (returns its id)."""

    def post(self, request, pk):
        from hr_calendar.models import AlbaranBatch

        person = _person(pk)
        if not uses_albaranes(person):
            return JsonResponse({"error": "Este trabajador no ficha por "
                                 "tipos: los albaranes no se cotejan."},
                                status=400)
        try:
            count = int(request.POST.get("count") or 0)
        except ValueError:
            count = 0
        if not 0 < count <= MAX_FILES:
            return JsonResponse({"error": "Elija una carpeta con entre 1 y "
                                 "%d archivos." % MAX_FILES}, status=400)
        batch = AlbaranBatch.objects.create(
            company=request.user.company_user.company, person=person,
            created_by=request.user.company_user,
            folder_name=(request.POST.get("folder") or "")[:255],
        )
        return JsonResponse({"batch": batch.pk})


class AlbaranFileView(SupervisorAccessMixin, View):
    """POST: one file of the folder."""

    def post(self, request, pk, batch_id):
        from hr_calendar.albaran_check import AlbaranError, stage_file
        from hr_calendar.models import AlbaranBatch

        person = _person(pk)
        batch = _batch(request, person, batch_id)
        if batch.status != AlbaranBatch.Status.UPLOADING:
            return JsonResponse({"error": "Esta carga ya se ha cerrado."},
                                status=400)
        upload = request.FILES.get("file")
        if upload is None:
            return JsonResponse({"error": "No ha llegado el archivo."},
                                status=400)
        try:
            stage_file(batch, upload.name, upload.read())
        except AlbaranError as exc:
            # Un archivo que no es PDF ni foto se salta, sin parar.
            return JsonResponse({"skipped": str(exc)})
        return JsonResponse({"ok": True})


class AlbaranFinishView(SupervisorAccessMixin, View):
    """POST: the upload is complete; read it in the background."""

    def post(self, request, pk, batch_id):
        from hr_calendar.models import AlbaranBatch
        from hr_calendar.tasks import read_albaran_batch_task

        person = _person(pk)
        batch = _batch(request, person, batch_id)
        if not batch.sheets.exists():
            batch.status = AlbaranBatch.Status.CANCELLED
            batch.error = "Ningún archivo válido."
            batch.save(update_fields=["status", "error"])
            return JsonResponse({"error": "Ningún archivo era un PDF o una "
                                 "foto."}, status=400)
        updated = AlbaranBatch.objects.filter(
            pk=batch.pk, status=AlbaranBatch.Status.UPLOADING,
        ).update(status=AlbaranBatch.Status.READING)
        if updated:
            transaction.on_commit(
                lambda: read_albaran_batch_task.delay(batch.pk))
        return JsonResponse({"ok": True})


class AlbaranStatusView(SupervisorAccessMixin, View):
    """GET: how an upload is going."""

    def get(self, request, pk, batch_id):
        from hr_calendar.models import AlbaranSheet

        person = _person(pk)
        batch = _batch(request, person, batch_id)
        sheets = list(batch.sheets.all())
        first_files = [s for s in sheets if s.position == 1]
        done = sum(1 for s in first_files
                   if s.status != AlbaranSheet.Status.PENDING)
        days = batch.day_checks.count()
        corrected = batch.day_checks.filter(corrected=True).count()
        return JsonResponse({
            "status": batch.status,
            "status_label": batch.get_status_display(),
            "files": len(first_files),
            "read": done,
            "albaranes": sum(1 for s in sheets
                             if s.status == AlbaranSheet.Status.READ),
            "unreadable": [
                "%s: %s" % (s.original_name, s.note or s.get_status_display())
                for s in sheets if s.status in (
                    AlbaranSheet.Status.UNREADABLE,
                    AlbaranSheet.Status.ERROR)],
            "mismatch": sorted({s.operator_name for s in sheets
                                if s.name_mismatch}),
            "days": days,
            "corrected": corrected,
            "error": batch.error,
        })


class AlbaranSheetFileView(SupervisorAccessMixin, View):
    """GET: the file an albarán came in (to check what the AI read)."""

    def get(self, request, pk, sheet_id):
        from hr_calendar.albaran_check import AlbaranError, _staged_abs
        from hr_calendar.albaran_check import mime_of
        from hr_calendar.models import AlbaranSheet

        person = _person(pk)
        sheet = AlbaranSheet.objects.filter(
            pk=sheet_id, batch__person=person,
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


def albaranes_by_day(person, date_from, date_to):
    """
    {day: [read albaranes]} of a worker between two dates.
    ---
    Los albaranes leídos de cada día (el último leído de cada número,
    por si se cargó dos veces), para la tabla de jornadas.
    """
    from hr_calendar.models import AlbaranSheet

    result, seen = {}, set()
    for sheet in AlbaranSheet.objects.filter(
            batch__person=person, day__gte=date_from, day__lte=date_to,
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
