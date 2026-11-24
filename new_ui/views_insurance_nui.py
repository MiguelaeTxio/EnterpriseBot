# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_insurance_nui.py
"""
Insurance renewal reports in the new interface (Empresa › Seguros).

---

Informes de seguros en la nueva interfaz (S163, 24/11), copia de
panel/views_insurance.py sin depender de ella: nuevo informe (meses de
vencimiento, empresas, título y libros mayores de la cuenta 625: subir
y elegir su empresa), ver y exportar a HTML, Excel, PDF o Word, volver
a generar y borrar. Solo para quien tiene `CompanyUser.insurance_access`
(«visible solo para Yolanda y Alejandro (y yo)»). La lógica está en
insurance/service.py, insurance/builder.py e insurance/exports.py.
"""
import datetime
import logging
from urllib.parse import quote

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from insurance import companies
from insurance import service
from insurance.models import InsuranceLedger
from insurance.models import InsuranceReport
from insurance.models import InsuranceReportExport
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)

MAX_LEDGER_BYTES = 20 * 1024 * 1024
FORMATS = (("html", "HTML", "bi-filetype-html"),
           ("xlsx", "Excel", "bi-file-earmark-excel"),
           ("pdf", "PDF", "bi-file-earmark-pdf"),
           ("docx", "Word", "bi-file-earmark-word"))


def can_use_insurance(company_user):
    """Solo quien tiene acceso a los seguros (como en la antigua)."""
    return bool(company_user is not None
                and getattr(company_user, "insurance_access", False))


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


class InsuranceMixin(SuperuserRequiredMixin):
    """Superusuario de la nueva interfaz y, además, acceso a los seguros."""

    def dispatch(self, request, *args, **kwargs):
        cu = getattr(request.user, "company_user", None)
        if request.user.is_authenticated and not can_use_insurance(cu):
            return HttpResponse("Los informes de seguros no son para tu "
                                "usuario.", status=403)
        return super().dispatch(request, *args, **kwargs)


def _month(raw):
    try:
        return datetime.date.fromisoformat((raw or "") + "-01")
    except ValueError:
        return None


def user_label(company_user):
    if company_user is None:
        return ""
    user = company_user.user
    return user.get_full_name() or user.username


def ledger_label(ledger):
    """Periodo, apuntes, importe y fecha de impresión del libro."""
    return "%s a %s · %d apuntes · %s €%s" % (
        ledger.date_from.strftime("%d/%m/%Y") if ledger.date_from else "?",
        ledger.date_to.strftime("%d/%m/%Y") if ledger.date_to else "?",
        ledger.entry_count,
        "{:,.2f}".format(ledger.total).replace(",", "X").replace(
            ".", ",").replace("X", "."),
        " · impreso el %s" % ledger.printed_at.strftime("%d/%m/%Y")
        if ledger.printed_at else "")


def decorate(report):
    """Lo que se enseña de un informe (lista y ventana)."""
    report.supervisor_label = user_label(report.created_by)
    report.due_label = service.due_label(report)
    report.companies_label = ", ".join(
        companies.label(c) for c in report.companies or []) or "Todas"
    ledgers = list(report.ledgers.all())
    report.ledger_count = len(ledgers)
    report.ledgers_label = "; ".join(
        "%s %s–%s" % (
            companies.label(item.company_code) or "Sin empresa",
            item.date_from.strftime("%m/%Y") if item.date_from else "?",
            item.date_to.strftime("%m/%Y") if item.date_to else "?")
        for item in ledgers)
    formats = []
    exports = list(report.exports.all())
    for export in exports:
        name = export.get_fmt_display()
        if name not in formats:
            formats.append(name)
    report.export_list = exports[:12]
    report.exported_label = ", ".join(formats)
    report.progress_pct = (round(100 * report.progress_done
                                 / report.progress_total)
                           if report.progress_total else 0)
    return report


# --------------------------------------------------------------- ventanas
class InsuranceSheetView(InsuranceMixin, View):
    """
    GET: one report in the viewer.

    ---

    GET: un informe en el visor (al pulsarlo): meses, empresas, libros
    mayores, estado (se actualiza solo mientras se hace), ver y
    exportar, volver a generar y borrar.
    """

    def get(self, request, pk):
        report = InsuranceReport.objects.select_related(
            "created_by__user").filter(pk=pk).first()
        if report is None:
            return HttpResponse('<p class="small text-muted mb-0">Ese '
                                'informe ya no existe.</p>')
        return render(request, "new_ui/_insurance_sheet.html", {
            "report": decorate(report),
            "formats": FORMATS,
            "is_done": report.status == InsuranceReport.Status.DONE,
        })


class InsuranceNewFormView(InsuranceMixin, View):
    """
    GET: «Nuevo informe» in the viewer.

    ---

    GET: la ventana «Nuevo informe»: meses de vencimiento, empresas
    (botones), título y los libros mayores (marcar, subir otros y
    elegir la empresa de cada uno con botones, sin desplegable).
    """

    def get(self, request):
        ledgers = [{
            "pk": ledger.pk, "company": ledger.company_code,
            "company_label": companies.label(ledger.company_code),
            "label": ledger_label(ledger),
        } for ledger in InsuranceLedger.objects.order_by(
            "company_code", "-date_to")]
        return render(request, "new_ui/_insurance_new.html", {
            "companies": companies.CHOICES,
            "ledgers": ledgers,
            "this_month": timezone.localdate().strftime("%Y-%m"),
        })


# ---------------------------------------------------------------- acciones
class InsuranceLedgerUploadView(InsuranceMixin, View):
    """
    POST: one or more ledger PDFs (account 625); read at once.

    ---

    POST: uno o varios PDF del libro mayor de la cuenta 625. Se leen al
    momento: empresa detectada, periodo y apuntes; si ya estaba subido,
    se queda el que había.
    """

    def post(self, request):
        files = request.FILES.getlist("file")
        if not files:
            return _error("Falta el PDF.")
        lines = []
        for upload in files:
            if upload.size > MAX_LEDGER_BYTES:
                lines.append("%s: pesa más de 20 MB." % upload.name)
                continue
            try:
                ledger, created = service.save_ledger(
                    upload.name, upload.read(), request.user.company_user)
            except service.InsuranceError as exc:
                lines.append("%s: %s" % (upload.name, exc))
                continue
            lines.append("%s %s (%s)." % (
                "Leído" if created else "Ya estaba subido",
                ledger_label(ledger),
                companies.label(ledger.company_code)
                or "sin empresa: elígela"))
        return _ok(" ".join(lines))


class InsuranceLedgerCompanyView(InsuranceMixin, View):
    """POST: la empresa de un libro mayor (de la lista, nunca a mano)."""

    def post(self, request, pk):
        ledger = InsuranceLedger.objects.filter(pk=pk).first()
        code = request.POST.get("company", "")
        if ledger is None or code not in companies.LABELS:
            return _error("Elige la empresa de la lista.")
        ledger.company_code = code
        ledger.save(update_fields=["company_code"])
        return _ok("Libro mayor de %s." % companies.label(code))


class InsuranceReportCreateView(InsuranceMixin, View):
    """
    POST: create a report and start it in the background.

    ---

    POST: crea un informe (meses, empresas, libros mayores y título) y
    lo lanza en segundo plano; la ventana pasa a enseñarlo.
    """

    def post(self, request):
        month_from = _month(request.POST.get("month_from"))
        if month_from is None:
            return _error("Pon el mes de vencimiento «desde».")
        month_to = _month(request.POST.get("month_to"))
        codes = [c for c in request.POST.getlist("company")
                 if c in companies.LABELS]
        if len(codes) == len(companies.LABELS):
            codes = []
        ledger_ids = [v for v in request.POST.getlist("ledger")
                      if v.isdigit()]
        try:
            report = service.create_report(
                request.user.company_user, month_from, month_to, codes,
                ledger_ids, request.POST.get("title", ""))
        except service.InsuranceError as exc:
            return _error(str(exc))
        return _ok("Informe «%s» en marcha: se hace en segundo plano."
                   % report.title, id=report.pk)


class InsuranceActionView(InsuranceMixin, View):
    """POST: volver a generar o borrar los informes marcados."""

    def post(self, request):
        action = request.POST.get("action", "")
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        reports = list(InsuranceReport.objects.filter(pk__in=ids))
        if not reports:
            return _error("Marca algún informe.")
        if action == "retry":
            busy = [r for r in reports if r.is_live]
            for report in reports:
                if not report.is_live:
                    service.retry(report)
            message = "%d informe(s) en marcha otra vez." % (
                len(reports) - len(busy))
            if busy:
                message += " %d ya se estaba(n) haciendo." % len(busy)
            return _ok(message)
        if action == "delete":
            for report in reports:
                report.delete()
            return _ok("%d informe(s) borrado(s)." % len(reports))
        return _error("Acción desconocida.")


class InsuranceExportView(InsuranceMixin, View):
    """
    GET: one report as HTML (view), HTML, Excel, PDF or Word.

    ---

    GET: un informe para verlo en el navegador (view=1) o descargado en
    HTML, Excel, PDF o Word. Cada descarga queda anotada («Exportado a»).
    """

    def get(self, request, pk, fmt):
        from insurance.exports import EXPORTERS

        report = InsuranceReport.objects.filter(
            pk=pk, status=InsuranceReport.Status.DONE).select_related(
            "created_by__user").first()
        if report is None or fmt not in EXPORTERS:
            raise Http404
        function, content_type, extension = EXPORTERS[fmt]
        try:
            data = function(report)
        except Exception:  # noqa: BLE001 -- se informa al usuario
            logger.exception("# [insurance export] %s %s", pk, fmt)
            return HttpResponse("No se ha podido generar el %s. Avisa a "
                                "Miguel Ángel." % fmt.upper(), status=500)
        response = HttpResponse(data, content_type=content_type)
        if request.GET.get("view") == "1" and fmt == "html":
            return response
        InsuranceReportExport.objects.create(
            report=report, fmt=fmt, exported_by=request.user.company_user)
        name = "Informe_seguros_%s_%s.%s" % (
            report.pk, timezone.localtime(
                report.finished_at or report.created_at).strftime(
                "%Y%m%d"), extension)
        response["Content-Disposition"] = (
            "attachment; filename*=UTF-8''%s" % quote(name))
        response["Cache-Control"] = "private, no-store"
        return response
