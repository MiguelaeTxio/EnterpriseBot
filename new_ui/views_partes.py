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

from django.http import HttpResponse, JsonResponse
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
