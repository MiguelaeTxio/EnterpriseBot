# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_logbook.py
"""
Periodic reviews of the A/H cranes' logbook, new interface.

---

Revisiones del libro historial de las grúas A y H en la nueva interfaz
(S163), copiado de panel/views_machine_logbook.py (S154):
- Centros de gasto › Libro historial: subir el escaneo de una revisión
  que faltaba, anotar una reconstrucción, enviar las reconstrucciones
  marcadas a la firma digital y quitar las pendientes marcadas.
- Revisiones que faltan: los huecos sin revisión de todas las grúas.
"""
import logging
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from fleet.models import MachineAsset, MachineLogbookEntry
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)

MAX_SCAN_BYTES = 25 * 1024 * 1024
SCAN_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _date(raw):
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _crane(request):
    """
    The open machine if it is an A/H crane, else (None, error message).

    ---

    La máquina abierta si es grúa A/H; si no, el aviso que se devuelve.
    """
    from fleet.logbook_service import is_logbook_machine

    machine = MachineAsset.objects.filter(
        pk=request.POST.get("machine_pk") or 0).first()
    if machine is None:
        return None, "Abre primero la grúa."
    if not is_logbook_machine(machine):
        return None, "Solo las grúas móviles A y H llevan libro historial."
    return machine, ""


def _selected(request):
    return [v for v in request.POST.getlist("selected") if v.isdigit()]


def review_gaps(machine):
    """
    Gaps without reviews of the crane, for «Del centro de gasto».

    ---

    Huecos sin revisión de la grúa: cada uno es una revisión que hay
    que buscar en su libro y escanear (o reconstruir si se perdió).
    """
    from fleet.logbook_service import review_gaps as gaps_of, review_rows

    reviews = review_rows(machine)
    return gaps_of(reviews), len(reviews)


def logbook_context():
    """
    Context of the logbook actions block.

    ---

    Contexto del bloque de acciones del libro: las firmas de empresa
    con certificado (para enviar a la firma digital).
    """
    from document_explorer.models import CompanySignature

    return {
        "logbook_signatures": CompanySignature.objects.exclude(
            certificate_cif="", certificate_alias="",
        ).select_related("company").order_by("company__pk", "label"),
    }


class ReviewScanUploadView(SuperuserRequiredMixin, View):
    """
    POST: upload the scan of a missing review; it is read on its own.

    ---

    POST: sube el escaneo de la hoja del libro con la revisión que
    faltaba. Se guarda como documento «Libro historial» de la grúa con
    la fecha de la revisión y se lee enseguida: el hueco desaparece
    cuando la revisión queda leída.
    """

    def post(self, request):
        from document_explorer.models import DocumentTypeCatalog
        from document_explorer.subject_upload_service import (
            SubjectUploadError, upload_subject_document,
        )
        from fleet.logbook_service import (
            LOGBOOK_TYPE_CODE, _machine_content_type,
        )
        from fleet.tasks import logbook_pipeline_task

        machine, error = _crane(request)
        if machine is None:
            return _error(error)
        upload = request.FILES.get("scan")
        review_date = _date(request.POST.get("review_date"))
        if upload is None or not upload.name.lower().endswith(
                SCAN_EXTENSIONS):
            return _error("Elige el escaneo (PDF, JPG o PNG).")
        if upload.size > MAX_SCAN_BYTES:
            return _error("El escaneo pasa de 25 MB.")
        if review_date is None or review_date > date.today():
            return _error("Escribe la fecha de la revisión que aparece en "
                          "el escaneo (no puede ser futura).")
        try:
            result = upload_subject_document(
                subject=machine,
                domain_content_type=_machine_content_type(),
                document_type=DocumentTypeCatalog.objects.get(
                    code=LOGBOOK_TYPE_CODE),
                data=upload.read(),
                original_filename=upload.name,
                typed_date=None,
                subject_label=machine.code,
                uploaded_by=request.user.company_user,
                typed_issue_date=review_date,
                filename_date=review_date,
            )
        except SubjectUploadError as exc:
            return _error(str(exc))
        entry = result["entry"]
        logbook_pipeline_task.delay(document_id=entry.pk)
        logger.info("# [new_ui reviews] %s: escaneo subido (documento %s) "
                    "por %s", machine.code, entry.pk, request.user.username)
        return _ok("Escaneo subido. Se está leyendo: en unos minutos sus "
                   "revisiones aparecen en la lista.")


class ReviewReconstructView(SuperuserRequiredMixin, View):
    """
    POST: record a review whose record was lost (pending signature).

    ---

    POST: anota la reconstrucción de una revisión que se hizo pero cuyo
    registro se perdió. Queda pendiente de la firma digital; hasta
    entonces no cuenta como firmada.
    """

    def post(self, request):
        from fleet.logbook_service import (
            LogbookReadError, create_reconstruction,
        )

        machine, error = _crane(request)
        if machine is None:
            return _error(error)
        try:
            create_reconstruction(
                machine, request.user.company_user,
                entry_date=_date(request.POST.get("entry_date")),
                result=request.POST.get("result", ""),
                entity=request.POST.get("entity", ""),
                next_date=_date(request.POST.get("next_date")),
                concept=request.POST.get("concept", ""),
            )
        except LogbookReadError as exc:
            return _error(str(exc))
        return _ok("Reconstrucción anotada. Queda pendiente de la firma "
                   "digital con el certificado de la empresa.")


class ReviewSendToSignView(SuperuserRequiredMixin, View):
    """
    POST: queue the marked reconstructions for the digital signature.

    ---

    POST: envía las reconstrucciones pendientes marcadas a la cola del
    agente de firmas con la firma de empresa elegida.
    """

    def post(self, request):
        from document_explorer.models import CompanySignature
        from fleet.logbook_service import (
            LogbookReadError, reconstructed_rows, send_to_sign,
        )

        machine, error = _crane(request)
        if machine is None:
            return _error(error)
        pks = {int(v) for v in _selected(request)}
        rows = [row for row in reconstructed_rows(machine) if row.pk in pks]
        if not rows:
            return _error("Marca las reconstrucciones pendientes de esta "
                          "grúa que quieres enviar a la firma.")
        signature = CompanySignature.objects.filter(
            pk=request.POST.get("signature") or 0).first()
        if signature is None:
            return _error("Elige la firma de empresa.")
        try:
            job = send_to_sign(rows, signature, request.user.company_user)
        except LogbookReadError as exc:
            return _error(str(exc))
        return _ok("Enviadas a la firma digital: %d, con «%s». El lote "
                   "aparece en Documentación › Firmas." % (
                       job.files.count(), signature.label))


class ReviewRemoveView(SuperuserRequiredMixin, View):
    """
    POST: remove the marked pending reconstructions.

    ---

    POST: quita las reconstrucciones marcadas que aún no se han enviado
    a la firma. Ni las escaneadas ni las firmadas se tocan.
    """

    def post(self, request):
        ids = _selected(request)
        if not ids:
            return _error("Marca primero las reconstrucciones a quitar.")
        removed, _detail = MachineLogbookEntry.objects.filter(
            pk__in=ids, source__isnull=True, is_reconstructed=True,
            signed_at__isnull=True, signing_file__isnull=True,
        ).delete()
        return _ok("Reconstrucciones pendientes quitadas: %d (solo se "
                   "quitan las que no se han enviado a la firma)." % removed)


class MissingReviewsView(SuperuserRequiredMixin, View):
    """
    GET: gaps without reviews of every A/H crane.

    ---

    GET: las revisiones que faltan en todas las grúas A y H (cada hueco
    de más de seis meses y las grúas sin ninguna revisión leída).
    """

    def get(self, request):
        from fleet.logbook_service import missing_reviews

        cranes = missing_reviews()
        return render(request, "new_ui/missing_reviews.html", {
            "cranes": cranes,
            "gaps_total": sum(len(item["gaps"]) for item in cranes),
        })
