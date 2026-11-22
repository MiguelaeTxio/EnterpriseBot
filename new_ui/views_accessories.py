# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_accessories.py
"""
Lifting accessories actions, new interface.

---

Acciones de los accesorios de elevación en la nueva interfaz (S163),
copiado de panel/views_lifting_accessories.py y de sus formularios
(panel/forms_lifting_accessories.py), en Centros de gasto ›
Accesorios:
- Alta de un accesorio NUEVO con su certificado obligatorio (sin
  entrega: entregar es un acto aparte, S121).
- Sobre los marcados: retirar o reactivar, registrar la misma
  revisión, entregar a un centro de gasto y a un responsable,
  devolverlos y subir otro certificado (uno solo marcado).
"""
from datetime import date

from django.db import transaction
from django.http import JsonResponse
from django.views import View

from document_explorer import lifting_accessory_service as service
from document_explorer.models import (
    LiftingAccessory, LiftingAccessoryAssignment, LiftingAccessoryModel,
    LiftingAccessoryType, PersonIdentity,
)
from fleet.cost_center_search import resolve_cost_center
from fleet.models import MachineAsset
from new_ui.mixins import SuperuserRequiredMixin

ACCEPTED_EXTENSIONS = ("pdf", "jpg", "jpeg", "png")


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _date(raw):
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _upload_ok(upload):
    return upload is not None and (
        upload.name.rsplit(".", 1)[-1].lower() in ACCEPTED_EXTENSIONS)


def _company(request):
    return request.user.company_user.company


def _selected(request):
    """
    Accessories of the user's company among the marked ids.

    ---

    Accesorios de la empresa del usuario entre los marcados (nunca de
    otra empresa, aunque se manipule el id).
    """
    ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
    return LiftingAccessory.objects.filter(
        company=_company(request), pk__in=ids)


def _person_label(person):
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p)
    return "%s, %s" % (surnames, person.given_name)


def accessories_context(section):
    """
    Context of the accessories actions (models, types and workers).

    ---

    Modelos y tipos activos para el alta y trabajadores en activo para
    la entrega, como listas filtrables (sin desplegables).
    """
    if section != "cdg":
        return {}
    return {
        "acc_models": [
            (m.pk, "%s · %s" % (m.accessory_type.label, m.name))
            for m in LiftingAccessoryModel.objects.filter(
                is_active=True).select_related("accessory_type").order_by(
                "accessory_type__display_order", "display_order", "name")
        ],
        "acc_types": list(LiftingAccessoryType.objects.filter(
            is_active=True).order_by("display_order", "label").values_list(
            "pk", "label")),
        "acc_people": [
            (p.pk, _person_label(p))
            for p in PersonIdentity.objects.filter(
                is_active_employee=True).order_by(
                "first_surname", "second_surname", "given_name")
        ],
    }


class AccessoryCreateView(SuperuserRequiredMixin, View):
    """
    POST: create one NEW accessory with its mandatory certificate.

    ---

    POST: alta de un accesorio nuevo. Con modelo, el tipo, las medidas,
    la carga y la norma salen del modelo si se dejan en blanco. Único
    por (empresa, tipo, nº). El certificado se sube ya tipado.
    """

    def post(self, request):
        company = _company(request)
        post = request.POST
        model = LiftingAccessoryModel.objects.filter(
            pk=post.get("model") or 0, is_active=True).select_related(
            "accessory_type").first()
        accessory_type = LiftingAccessoryType.objects.filter(
            pk=post.get("accessory_type") or 0).first()
        if model is not None:
            if accessory_type is not None and (
                    accessory_type != model.accessory_type):
                return _error("El tipo no coincide con el del modelo "
                              "elegido.")
            accessory_type = model.accessory_type
        elif accessory_type is None:
            return _error("Elige un modelo o, si no hay, un tipo.")
        identifier = (post.get("identifier") or "").strip()
        if not identifier:
            return _error("Escribe el nº del accesorio.")
        if LiftingAccessory.objects.filter(
                company=company, accessory_type=accessory_type,
                identifier__iexact=identifier).exists():
            return _error("Ya existe un accesorio de este tipo con ese nº.")
        load = (post.get("working_load_kg") or "").strip()
        if load and not load.isdigit():
            return _error("La carga de trabajo es un número de kg.")
        upload = request.FILES.get("certificate_file")
        if not _upload_ok(upload):
            return _error("Sube el certificado del fabricante (PDF o "
                          "foto).")
        values = {
            "dimensions": (post.get("dimensions") or "").strip(),
            "working_load_kg": int(load) if load else None,
            "standard": (post.get("standard") or "").strip(),
        }
        if model is not None:
            for field in values:
                if values[field] in (None, ""):
                    values[field] = getattr(model, field)
        with transaction.atomic():
            accessory = LiftingAccessory.objects.create(
                company=company, model=model, accessory_type=accessory_type,
                identifier=identifier,
                traceability=(post.get("traceability") or "").strip(),
                description=(post.get("description") or "").strip(),
                manufacturer=(post.get("manufacturer") or "").strip(),
                supply_date=_date(post.get("supply_date")),
                **values,
            )
            service.upload_certificate(accessory, upload)
        return _ok("Accesorio %s dado de alta." % accessory.identifier)


class AccessoryStatusView(SuperuserRequiredMixin, View):
    """
    POST `action` (retire | reactivate): status of the marked.

    ---

    POST: retirar del servicio o reactivar los marcados. Retirar cierra
    su entrega abierta con fecha de hoy.
    """

    def post(self, request):
        action = request.POST.get("action")
        if action not in ("retire", "reactivate"):
            return _error("Acción no válida.")
        changed = service.set_active(
            _selected(request), is_active=(action == "reactivate"))
        if not changed:
            return _error("Marca primero los accesorios.")
        return _ok("%d accesorio(s) %s." % (
            changed, "retirados" if action == "retire" else "reactivados"))


class AccessoryReviewView(SuperuserRequiredMixin, View):
    """
    POST: record the same review on each marked accessory.

    ---

    POST: registra la misma revisión (fecha y caducidad opcional, que
    prevalece sobre revisión + 12 meses) en cada marcado; su documento,
    opcional, solo con un accesorio marcado.
    """

    def post(self, request):
        review_date = _date(request.POST.get("review_date"))
        expiry = _date(request.POST.get("explicit_expiry_date"))
        if review_date is None:
            return _error("Indica la fecha de la revisión.")
        if expiry and expiry < review_date:
            return _error("La caducidad no puede ser anterior a la "
                          "revisión.")
        accessories = list(_selected(request))
        if not accessories:
            return _error("Marca primero los accesorios.")
        upload = request.FILES.get("review_file")
        if upload is not None:
            if not _upload_ok(upload):
                return _error("El documento debe ser un PDF o una imagen.")
            if len(accessories) > 1:
                return _error("El documento de la revisión se sube con un "
                              "solo accesorio marcado.")
        with transaction.atomic():
            for accessory in accessories:
                service.register_review(
                    accessory, review_date, expiry, upload)
        return _ok("Revisión registrada en %d accesorio(s)." % len(
            accessories))


class AccessoryDeliverView(SuperuserRequiredMixin, View):
    """
    POST: deliver the marked to one cost centre and one responsible.

    ---

    POST: entrega los marcados (activos) a un mismo centro de gasto (el
    código escrito o, si no, la máquina abierta) y a una persona
    responsable, con la misma fecha. Cada uno cierra su entrega
    anterior (historial).
    """

    def post(self, request):
        company = _company(request)
        code = (request.POST.get("cost_center") or "").strip()
        if code:
            machine = resolve_cost_center(company, code)
            if machine is None:
                return _error("No existe ningún centro de gasto activo con "
                              "ese código.")
        else:
            machine = MachineAsset.objects.filter(
                pk=request.POST.get("machine_pk") or 0).first()
            if machine is None:
                return _error("Escribe el código del centro de gasto o "
                              "abre uno.")
        person = PersonIdentity.objects.filter(
            pk=request.POST.get("responsible_person") or 0,
            is_active_employee=True).first()
        if person is None:
            return _error("Elige a quién se entrega (responsable).")
        start = _date(request.POST.get("start_date"))
        if start is None:
            return _error("Indica la fecha de entrega.")
        accessories = list(_selected(request).filter(is_active=True))
        if not accessories:
            return _error("Marca accesorios en servicio.")
        with transaction.atomic():
            for accessory in accessories:
                service.assign_accessory(
                    accessory, person, machine, start,
                    notes=(request.POST.get("notes") or "").strip())
        return _ok("%d accesorio(s) entregados a %s (%s)." % (
            len(accessories), machine.code, _person_label(person)))


class AccessoryReturnView(SuperuserRequiredMixin, View):
    """
    POST: return the marked (closes their open delivery).

    ---

    POST: devolución de los marcados: cierra su entrega abierta. La
    fecha no puede ser anterior a la entrega.
    """

    def post(self, request):
        end = _date(request.POST.get("end_date"))
        if end is None:
            return _error("Indica la fecha de devolución.")
        accessories = list(_selected(request))
        open_ones = {
            a.accessory_id: a for a in LiftingAccessoryAssignment.objects
            .filter(accessory__in=accessories, end_date__isnull=True)}
        if not open_ones:
            return _error("Ninguno de los marcados está entregado.")
        early = [a.accessory.identifier for a in open_ones.values()
                 if end < a.start_date]
        if early:
            return _error("La devolución no puede ser anterior a la "
                          "entrega (%s)." % ", ".join(early))
        for accessory in accessories:
            if accessory.pk in open_ones:
                service.return_accessory(accessory, end)
        return _ok("%d devolución(es) registrada(s)." % len(open_ones))


class AccessoryCertificateView(SuperuserRequiredMixin, View):
    """
    POST: upload one more certificate of the only marked accessory.

    ---

    POST: sube otro certificado (p. ej. uno renovado), ya tipado y
    enlazado, al único accesorio marcado.
    """

    def post(self, request):
        accessories = list(_selected(request))
        if len(accessories) != 1:
            return _error("Marca un solo accesorio.")
        upload = request.FILES.get("certificate_file")
        if not _upload_ok(upload):
            return _error("Elige el certificado (PDF o foto).")
        service.upload_certificate(accessories[0], upload)
        return _ok("Certificado subido a %s." % accessories[0].identifier)
