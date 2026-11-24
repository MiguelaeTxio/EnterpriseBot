# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_safety.py
"""
Fire extinguishers and first-aid kits (Centros de gasto › Seguridad).

---

Extintores y botiquines (S163, 23/11, Miguel Ángel): van para un centro
de gasto (una dependencia o una máquina) y se entregan a una persona
concreta ("a Antonio el guarda, este botiquín para estas
dependencias"). Son entregas de EPI (document_explorer.EpiDelivery)
con su número de serie o matrícula y tres fechas opcionales:
caducidad, próxima revisión y retimbrado. Avisan 30 días antes
(lists.py, Seguridad).
"""
import datetime
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import EpiDelivery, EpiItemCatalog
from document_explorer.models import PersonIdentity
from document_explorer.safety_notice_service import (
    item_label, safety_q as _safety_q,
)
from fleet.models import MachineAsset
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)

# Los dos de serie; además, cualquier EPI del catálogo que lo sea.
BASE_ITEMS = (("EXTINTOR", "Extintor"), ("BOTIQUIN", "Botiquín"))
WARN_DAYS = 30


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _date(value):
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def safety_items():
    """
    Los EPI de seguridad del catálogo (extintores y botiquines).

    ---

    Crea los dos de serie si aún no están (códigos EXTINTOR y BOTIQUIN,
    familia «Seguridad») y devuelve todos los activos que sean extintor
    o botiquín por su nombre o su familia.
    """
    for code, label in BASE_ITEMS:
        EpiItemCatalog.objects.get_or_create(
            code=code, defaults={"label": label, "family": "Seguridad",
                                 "is_active": True})
    return EpiItemCatalog.objects.filter(is_active=True).filter(
        Q(label__icontains="extint") | Q(label__icontains="botiqu")
        | Q(family__icontains="extint") | Q(family__icontains="botiqu")
        | Q(code__in=[code for code, _l in BASE_ITEMS])).order_by(
        "family", "label")


def safety_q(prefix=""):
    """Q de las entregas que son de seguridad (por su EPI)."""
    return _safety_q(prefix)


def safety_context(section):
    """Contexto de Centros de gasto › Seguridad."""
    if section != "cdg":
        return {}
    return {"nui_safety_items": list(safety_items())}


def _person_by_dni(company, dni):
    """La persona por su DNI exacto (Miguel Ángel, 24/11: «DNI es
    inequívoco»)."""
    dni = (dni or "").strip().upper().replace(" ", "").replace("-", "")
    if not dni:
        return None, "Escribe el DNI de a quién se entrega."
    person = PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True),
        dni__iexact=dni).first()
    if person is None:
        return None, "No hay nadie con el DNI %s." % dni
    return person, ""


def _machines(request, ids):
    company = request.user.company_user.company
    return list(MachineAsset.objects.filter(
        company=company, pk__in=[v for v in ids if str(v).isdigit()]
    ).order_by("code"))


class SafetyDeliverFormView(SuperuserRequiredMixin, View):
    """
    GET ?ids=: the delivery window for the marked cost centres.

    ---

    GET: la ventana «Entregar» (S163, 24/11): el destino (los centros de
    gasto marcados), a quién (DNI con autocompletar) y una línea por
    cada extintor o botiquín, con su número de serie y sus fechas.
    """

    def get(self, request):
        machines = _machines(request, request.GET.get("ids", "").split(","))
        if not machines:
            return HttpResponse('<p class="small text-danger mb-0">Marca '
                                'primero los centros de gasto.</p>')
        company = request.user.company_user.company
        people = PersonIdentity.objects.filter(
            Q(company=company) | Q(company__isnull=True),
            is_active_employee=True).exclude(dni="").order_by(
            "first_surname", "second_surname", "given_name").only(
            "dni", "given_name", "first_surname", "second_surname")
        return render(request, "new_ui/_safety_deliver.html", {
            "machines": machines,
            "people": people,
            "items": list(safety_items()),
            "today": datetime.date.today().isoformat(),
        })


def _lines(post):
    """Las líneas del formulario: (índice, epi_id, serie, 3 fechas)."""
    indexes = sorted({key.rsplit("_", 1)[1] for key in post
                      if key.startswith("epi_id_")},
                     key=lambda v: int(v) if v.isdigit() else 0)
    return [{
        "epi_id": post.get("epi_id_" + i),
        "serial": (post.get("serial_" + i) or "").strip()[:100],
        "expiry_date": _date(post.get("expiry_" + i)),
        "review_date": _date(post.get("review_" + i)),
        "retimbrado_date": _date(post.get("retimbrado_" + i)),
    } for i in indexes]


class SafetyDeliverView(SuperuserRequiredMixin, View):
    """
    POST: one real delivery of one or more safety items.

    ---

    POST: una entrega real (S163, 24/11): a una persona (por DNI), para
    uno o varios centros de gasto, de uno o más extintores o botiquines
    (cada uno con su número de serie y sus fechas). Como los EPIs: una
    EpiDelivery por elemento y centro de gasto, un solo documento de
    entrega para firmar (PDF, tipo EPIS) en los documentos de la persona
    y enlazado a todas, y la confirmación por WhatsApp al trabajador.
    """

    def post(self, request):
        from document_explorer.epi_delivery_document_service import (
            build_epi_delivery_pdf_bytes, resolve_company_fiscal_profile,
        )
        from document_explorer.models import DocumentTypeCatalog
        from document_explorer.subject_upload_service import (
            SubjectUploadError, upload_subject_document,
        )
        from whatsapp.services import send_epi_delivery_whatsapp_confirmation

        company = request.user.company_user.company
        machines = _machines(request, request.POST.getlist("machine_ids"))
        if not machines:
            return _error("No hay centro de gasto de destino.")
        person, problem = _person_by_dni(company, request.POST.get("dni"))
        if problem:
            return _error(problem)
        delivered = _date(request.POST.get("delivery_date"))
        if delivered is None:
            return _error("Indica la fecha de entrega.")
        items = {str(i.pk): i for i in safety_items()}
        lines = _lines(request.POST)
        if not lines:
            return _error("Añade al menos un extintor o botiquín.")
        for number, line in enumerate(lines, 1):
            if line["epi_id"] not in items:
                return _error("Línea %d: elige si es extintor o botiquín."
                              % number)
            if line["serial"] and len(machines) > 1:
                return _error("Línea %d: con número de serie, un solo "
                              "centro de gasto (cada extintor tiene el "
                              "suyo)." % number)
        deliveries, labels = [], []
        for line in lines:
            epi = items[line["epi_id"]]
            for machine in machines:
                delivery = EpiDelivery.objects.create(
                    person=person, epi=epi, delivery_date=delivered,
                    destination_machine=machine,
                    serial_number=line["serial"],
                    expiry_date=line["expiry_date"],
                    review_date=line["review_date"],
                    retimbrado_date=line["retimbrado_date"],
                    extraction_method=EpiDelivery.METHOD_MANUAL)
                deliveries.append(delivery)
                labels.append("%s - destino: %s %s" % (
                    item_label(delivery), machine.code,
                    machine.brand_model or ""))
        message = "Entregado a %s %s: %d elemento(s)." % (
            person.given_name, person.first_surname, len(deliveries))
        epis_type = DocumentTypeCatalog.objects.filter(code="EPIS").first()
        try:
            if epis_type is None:
                raise SubjectUploadError("falta el tipo documental EPIS")
            pdf = build_epi_delivery_pdf_bytes(
                person, labels, delivered,
                resolve_company_fiscal_profile(person.employer_company))
            entry = upload_subject_document(
                subject=person,
                domain_content_type=ContentType.objects.get_for_model(
                    PersonIdentity),
                document_type=epis_type, data=pdf,
                original_filename="entrega_extintores_botiquines_%s.pdf"
                % delivered.isoformat(),
                typed_date=None,
                subject_label="%s %s, %s" % (
                    person.first_surname, person.second_surname,
                    person.given_name),
                uploaded_by=request.user.company_user)["entry"]
            EpiDelivery.objects.filter(
                pk__in=[d.pk for d in deliveries]).update(source_entry=entry)
            message += " Documento de entrega generado en su ficha, para " \
                       "firmar."
        except SubjectUploadError as exc:
            message += " Ojo: el documento de entrega no se pudo generar " \
                       "(%s)." % exc
        # Una confirmación por elemento entregado (no una por centro de
        # gasto): la plantilla dice qué EPI y en qué fecha.
        sent, seen = 0, set()
        for delivery in deliveries:
            key = (delivery.epi_id, delivery.serial_number)
            if key in seen:
                continue
            seen.add(key)
            try:
                sent += bool(send_epi_delivery_whatsapp_confirmation(
                    delivery))
            except Exception:  # noqa: BLE001 -- nunca deshace la entrega
                logger.exception("# [SEGURIDAD] WhatsApp de la entrega")
        if sent:
            message += " Confirmación enviada por WhatsApp (%d)." % sent
        else:
            message += " No se pudo mandar la confirmación por WhatsApp."
        return _ok(message)


class SafetyRowsView(SuperuserRequiredMixin, View):
    """
    POST on the marked items: change their dates or delete them.

    ---

    POST sobre los marcados: `dates` cambia las fechas que se escriban
    (las vacías no se tocan); `delete` los quita.
    """

    def post(self, request):
        company = request.user.company_user.company
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        if not ids and request.POST.get("pk", "").isdigit():
            ids = [request.POST["pk"]]
        rows = list(EpiDelivery.objects.filter(
            safety_q(), pk__in=ids,
            destination_machine__company=company))
        if not rows:
            return _error("Marca primero los extintores o botiquines.")
        action = request.POST.get("action")
        if action == "delete":
            for row in rows:
                row.delete()
            return _ok("%d borrado(s) (entrega registrada por error)."
                       % len(rows))
        if action == "retire":
            when = _date(request.POST.get("retired_at")) or (
                datetime.date.today())
            note = (request.POST.get("retired_note") or "").strip()[:200]
            for row in rows:
                row.retired_at = when
                row.retired_note = note
                row.save(update_fields=["retired_at", "retired_note"])
            return _ok("%d retirado(s) el %s: quedan en el historial y ya "
                       "no avisan." % (len(rows), when.strftime("%d/%m/%Y")))
        if action == "unretire":
            for row in rows:
                row.retired_at = None
                row.retired_note = ""
                row.save(update_fields=["retired_at", "retired_note"])
            return _ok("%d vuelve(n) a estar en uso." % len(rows))
        fields = ("expiry_date", "review_date", "retimbrado_date")
        changes = {}
        for field in fields:
            raw = (request.POST.get(field) or "").strip()
            if raw:
                value = _date(raw)
                if value is None:
                    return _error("Fecha no válida.")
                changes[field] = value
        if not changes:
            return _error("Escribe alguna fecha.")
        for row in rows:
            for field, value in changes.items():
                setattr(row, field, value)
            row.save(update_fields=list(changes))
        return _ok("Fechas guardadas en %d." % len(rows))
