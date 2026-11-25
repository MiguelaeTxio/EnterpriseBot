# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_partes.py
"""
Digital partes review in the new interface (Horas y pagos › Partes).

---

Revisión de los partes digitales en la nueva interfaz (S163, 23/11),
copia de lo que hace Partes digitales (panel/views_workorders.py) sin
depender de ella: marcar y desmarcar revisados, eliminar y exportar por
plantilla los partes marcados. Miguel Ángel: "cuando migremos, Carolina
tendrá que utilizar esta parte".
"""
import io

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _marked(request):
    """Los partes digitales marcados, de la empresa de quien mira."""
    from work_order_processor.models import WorkOrder

    ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
    return WorkOrder.objects.filter(
        pk__in=ids, company=request.user.company_user.company,
        source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED])


def _templates(company_user):
    from django.db.models import Q

    from work_order_processor.models import ExportTemplate

    return ExportTemplate.objects.filter(
        Q(company_user=company_user, is_global=False)
        | Q(company=company_user.company, is_global=True)).order_by(
        "-is_default", "name")


def partes_context(section, company_user):
    """Contexto de las acciones de Horas y pagos › Partes."""
    if section != "per":
        return {}
    return {"parte_templates": list(_templates(company_user))}


class PartesReviewView(SuperuserRequiredMixin, View):
    """
    POST `what` = review | unreview | delete on the marked partes.

    ---

    POST: marca como revisados, desmarca o elimina los partes marcados
    (como las acciones en masa de Partes digitales).
    """

    def post(self, request):
        what = request.POST.get("what", "")
        partes = _marked(request)
        if not partes.exists():
            return _error("Marca primero los partes.")
        cu = request.user.company_user
        if what == "review":
            count = partes.filter(reviewed=False).update(
                reviewed=True, reviewed_by=cu, reviewed_at=timezone.now())
            return _ok("%d parte(s) marcado(s) como revisado(s)." % count)
        if what == "unreview":
            count = partes.filter(reviewed=True).update(
                reviewed=False, reviewed_by=None, reviewed_at=None)
            return _ok("%d parte(s) desmarcado(s)." % count)
        if what == "delete":
            count = partes.count()
            partes.delete()
            return _ok("%d parte(s) eliminado(s)." % count)
        return _error("Acción no válida.")


class PartesExportView(SuperuserRequiredMixin, View):
    """
    POST `template`, `fmt` (xlsx | pdf): the marked partes by template.

    ---

    POST: los partes marcados con una plantilla de exportación de Partes
    digitales (las del usuario y las globales), en Excel o PDF. Con una
    plantilla "por selección de operarios", van los de los partes
    marcados.
    """

    def post(self, request):
        from new_ui.xlsx_style import colorize_workbook
        from work_order_processor.services import (
            build_export_from_template, build_pdf_from_template,
        )

        cu = request.user.company_user
        template = _templates(cu).filter(
            pk=request.POST.get("template") or 0).first()
        if template is None:
            return _error("Elige la plantilla.")
        partes = _marked(request).order_by(
            "uploaded_by__user__last_name", "uploaded_by__user__first_name",
            "pk")
        if not partes.exists():
            return _error("Marca primero los partes.")
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        if request.POST.get("fmt") == "pdf":
            response = HttpResponse(build_pdf_from_template(template, partes),
                                    content_type="application/pdf")
            response["Content-Disposition"] = (
                'attachment; filename="partes_digitales_%s.pdf"' % stamp)
            return response
        book = build_export_from_template(template, partes)
        colorize_workbook(book)
        buffer = io.BytesIO()
        book.save(buffer)
        response = HttpResponse(buffer.getvalue(),
                                content_type=XLSX_CONTENT_TYPE)
        response["Content-Disposition"] = (
            'attachment; filename="partes_digitales_%s.xlsx"' % stamp)
        return response


def _photo_entries(photos):
    """
    Each task photo with its signed GCS URL (or None).

    ---

    Cada foto de la tarea con su URL firmada de GCS (copia de
    panel/views_task_photos._build_photo_entries); las antiguas de Drive
    llevan su enlace.
    """
    import logging

    from spare_parts.gcs_service import (
        TASK_PHOTOS_BUCKET, generate_signed_url,
    )

    entries = []
    for photo in photos:
        url = None
        if photo.gcs_blob_name:
            try:
                url = generate_signed_url(TASK_PHOTOS_BUCKET,
                                          photo.gcs_blob_name)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Sin URL firmada para la foto %s", photo.pk)
        entries.append({"photo": photo, "signed_url": url})
    return entries


class ParteSheetView(SuperuserRequiredMixin, View):
    """
    GET: the document of one digital parte (read only), for the viewer.

    ---

    GET: el documento del parte (como en la ficha antigua: "como si
    fuera el documento del parte digital"): datos del día, cada tarea
    con máquina, horas, avería, reparación, repuestos y fotos; arriba,
    el resumen (horas, extra, festivas, dieta, revisado) y los botones
    de revisar. Miguel Ángel (23/11): "yo quiero llegar, pinchar un
    parte y verlo".
    """

    def get(self, request, pk):
        from decimal import Decimal

        from work_order_processor.festive import is_festive, split_hours
        from work_order_processor.models import (
            WorkOrder, WorkOrderEntry, WorkOrderEntryLine,
        )

        parte = WorkOrder.objects.filter(
            pk=pk, company=request.user.company_user.company,
        ).select_related("uploaded_by__user", "uploaded_by__base",
                         "uploaded_by__person_identity",
                         "reviewed_by__user").first()
        if parte is None:
            raise Http404
        entries = list(WorkOrderEntry.objects.filter(
            work_order=parte).order_by("page_number", "pk"))
        lines = WorkOrderEntryLine.objects.filter(
            entry__in=entries,
        ).exclude(vacation_period__isnull=False).select_related(
            "machine_asset").prefetch_related(
            "spare_parts", "photos").order_by("line_number", "pk")
        by_entry = {}
        total = Decimal("0")
        for line in lines:
            line.photo_entries = _photo_entries(line.photos.all())
            by_entry.setdefault(line.entry_id, []).append(line)
            total += line.delta_hours or Decimal("0")
        day = entries[0].work_date if entries else None
        festive = is_festive(day, parte.uploaded_by)
        extra, festive_hours = split_hours(total, festive)
        cu = parte.uploaded_by
        person = getattr(cu, "person_identity", None) if cu else None
        from new_ui.lists import person_name

        reviewer = parte.reviewed_by
        return render(request, "new_ui/_parte_sheet.html", {
            "parte": parte,
            "worker": person_name(person) if person else (
                cu.user.get_full_name() if cu else ""),
            "day": day, "festive": festive, "total": total,
            "extra": extra, "festive_hours": festive_hours,
            "diet": any(e.has_diet for e in entries),
            "reviewed_by": (reviewer.user.get_full_name()
                            or reviewer.user.username) if reviewer else "",
            "blocks": [{"entry": e, "lines": by_entry.get(e.pk, [])}
                       for e in entries],
        })


class PartesSummaryView(SuperuserRequiredMixin, View):
    """
    GET: the period summary of one worker's partes (?pk=&periodo...).

    ---

    S163 (25/11), como el resumen de la ficha antigua (S77, Miguel
    Ángel: «quiero saber las horas que ha echado, en qué máquina ha
    estado trabajando, el parte del día resumen con toda la hora del
    periodo»): horas totales, horas por máquina (de más a menos) y por
    día; al pulsar un día, su parte. Las horas son las de las líneas
    del parte, sin la hora fantasma de vacaciones. Periodo: el del
    filtro; sin periodo, el de pago en curso (del 21 al 20).
    """

    def get(self, request):
        from decimal import Decimal

        from document_explorer.models import PersonIdentity
        from new_ui.lists import person_name
        from new_ui.views_pay import pay_period
        from work_order_processor.models import WorkOrderEntryLine

        person = PersonIdentity.objects.filter(
            pk=request.GET.get("pk") or 0).select_related(
            "company_user").first()
        if person is None:
            raise Http404
        start, end = pay_period(request.GET)
        machines, days = {}, {}
        total = Decimal("0")
        if person.company_user_id:
            lines = WorkOrderEntryLine.objects.filter(
                entry__work_order__company=request.user.company_user.company,
                entry__work_order__uploaded_by_id=person.company_user_id,
                entry__work_date__gte=start, entry__work_date__lte=end,
            ).exclude(vacation_period__isnull=False).select_related(
                "machine_asset", "entry")
            for line in lines:
                hours = line.delta_hours or Decimal("0")
                total += hours
                if line.machine_asset_id:
                    asset = line.machine_asset
                    label = ("%s — %s" % (asset.code, asset.brand_model)
                             if asset.brand_model else asset.code)
                else:
                    label = line.machine_raw or "Sin máquina"
                machines[label] = machines.get(label, Decimal("0")) + hours
                day = days.setdefault(line.entry.work_date, {
                    "hours": Decimal("0"), "partes": set()})
                day["hours"] += hours
                day["partes"].add(line.entry.work_order_id)
        return render(request, "new_ui/_partes_summary.html", {
            "name": person_name(person),
            "start": start, "end": end, "total": total,
            "has_account": bool(person.company_user_id),
            "machines": sorted(machines.items(), key=lambda x: -x[1]),
            "days": [(d, v["hours"], sorted(v["partes"]))
                     for d, v in sorted(days.items())],
        })
