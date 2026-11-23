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

from django.db.models import Q
from django.http import JsonResponse
from django.views import View

from document_explorer.models import EpiDelivery, EpiItemCatalog
from document_explorer.models import PersonIdentity
from fleet.models import MachineAsset
from new_ui.mixins import SuperuserRequiredMixin

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
    return (Q(**{prefix + "epi__label__icontains": "extint"})
            | Q(**{prefix + "epi__label__icontains": "botiqu"})
            | Q(**{prefix + "epi__family__icontains": "extint"})
            | Q(**{prefix + "epi__family__icontains": "botiqu"})
            | Q(**{prefix + "epi__code__in": [c for c, _l in BASE_ITEMS]}))


def safety_context(section):
    """Contexto de Centros de gasto › Seguridad."""
    if section != "cdg":
        return {}
    return {"nui_safety_items": list(safety_items())}


def _find_person(company, text):
    """La persona por DNI exacto o por un nombre que solo case con una."""
    text = (text or "").strip()
    if not text:
        return None, "Escribe a quién se entrega (DNI o nombre y apellido)."
    found = PersonIdentity.objects.filter(company=company,
                                          dni__iexact=text).first()
    if found is not None:
        return found, ""
    qs = PersonIdentity.objects.filter(company=company)
    for word in text.split():
        qs = qs.filter(Q(given_name__icontains=word)
                       | Q(first_surname__icontains=word)
                       | Q(second_surname__icontains=word)
                       | Q(nickname__icontains=word))
    people = list(qs[:3])
    if len(people) == 1:
        return people[0], ""
    if not people:
        return None, "No hay nadie con «%s»." % text
    return None, "«%s» es más de una persona: escribe su DNI." % text


class SafetyDeliverView(SuperuserRequiredMixin, View):
    """
    POST: deliver a fire extinguisher or a kit for the marked machines.

    ---

    POST: entrega un extintor o botiquín para cada centro de gasto
    marcado (o el abierto), a la persona indicada, con su número de
    serie y sus fechas.
    """

    def post(self, request):
        company = request.user.company_user.company
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        machines = list(MachineAsset.objects.filter(company=company,
                                                    pk__in=ids))
        if not machines:
            return _error("Marca primero los centros de gasto.")
        epi = safety_items().filter(
            pk=request.POST.get("epi_id") or 0).first()
        if epi is None:
            return _error("Elige si es un extintor o un botiquín.")
        person, problem = _find_person(company, request.POST.get("person"))
        if problem:
            return _error(problem)
        delivered = _date(request.POST.get("delivery_date"))
        if delivered is None:
            return _error("Indica la fecha de entrega.")
        serial = (request.POST.get("serial_number") or "").strip()[:100]
        if serial and len(machines) > 1:
            return _error("Con número de serie, marca un solo centro de "
                          "gasto (cada extintor tiene el suyo).")
        for machine in machines:
            EpiDelivery.objects.create(
                person=person, epi=epi, delivery_date=delivered,
                destination_machine=machine, serial_number=serial,
                expiry_date=_date(request.POST.get("expiry_date")),
                review_date=_date(request.POST.get("review_date")),
                retimbrado_date=_date(request.POST.get("retimbrado_date")),
                extraction_method=EpiDelivery.METHOD_MANUAL)
        return _ok("%s entregado a %s %s para %d centro(s) de gasto." % (
            epi.label, person.given_name, person.first_surname,
            len(machines)))


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
        rows = list(EpiDelivery.objects.filter(
            safety_q(), pk__in=ids,
            destination_machine__company=company))
        if not rows:
            return _error("Marca primero los extintores o botiquines.")
        if request.POST.get("action") == "delete":
            for row in rows:
                row.delete()
            return _ok("%d quitado(s)." % len(rows))
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
