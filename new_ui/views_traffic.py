# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_traffic.py
"""
Traffic section of the new interface: planning, notices, worksites.

---

Sección Tráfico de la nueva interfaz (S165, invasora sobre H11): cargar
el planning de las grúas (el Excel real, una hoja por día), enviar a
los gruistas la ubicación de la obra y la hora, asignar los nombres que
no se reconocen solos, y modificar, activar o unir obras y clientes.
La lógica es de la app de dominio (crane_albaranes.traffic); aquí solo
la pantalla.
"""
import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)
MAX_FAILURES_SHOWN = 6


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _date(raw):
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _ids(request):
    return [v for v in request.POST.getlist("selected") if v.isdigit()]


def traffic_context(section, company):
    """
    Context of the Traffic actions (new_ui/actions/tra.html).
    ---
    Lo que necesitan las acciones de Tráfico: las fechas por defecto de
    la carga y del envío y los trabajadores activos para asignar
    nombres.
    """
    if section != "tra":
        return {}
    from crane_albaranes.traffic import DEFAULT_DAYS_AHEAD
    from document_explorer.models import PersonIdentity
    from new_ui.lists import person_name

    today = timezone.localdate()
    people = PersonIdentity.objects.filter(
        company=company, is_active_employee=True).order_by(
        "first_surname", "second_surname", "given_name")
    return {
        "tra_today": today.isoformat(),
        "tra_tomorrow": (today + datetime.timedelta(1)).isoformat(),
        "tra_until": (today + datetime.timedelta(
            DEFAULT_DAYS_AHEAD)).isoformat(),
        "tra_people": [(p.pk, person_name(p)) for p in people],
    }


class PlanningUploadView(SuperuserRequiredMixin, View):
    """
    POST: load the planning Excel between two days.

    ---

    POST: carga el planning (el Excel tal cual, una hoja por día) entre
    «desde» y «hasta». Dice cuántos servicios son nuevos, cuántos han
    cambiado y cuántos se han quitado, y cuántos avisos hay (en Cargas).
    """

    def post(self, request):
        from crane_albaranes.traffic import import_planning

        upload = request.FILES.get("planning")
        if upload is None:
            return _error("Elige el Excel del planning.")
        if not upload.name.lower().endswith((".xlsx", ".xlsm")):
            return _error("El planning tiene que ser un Excel (.xlsx).")
        date_from = _date(request.POST.get("date_from"))
        date_to = _date(request.POST.get("date_to"))
        cu = request.user.company_user
        try:
            planning = import_planning(cu.company, upload, date_from,
                                       date_to, created_by=cu)
        except ValueError as exc:
            return _error(str(exc))
        except Exception as exc:  # noqa: BLE001 -- Excel ilegible
            logger.exception("# [TRÁFICO] Planning no cargado")
            return _error("No se ha podido leer el Excel: %s" % exc)
        logger.info("# [TRÁFICO] %s carga el planning %s", cu,
                    planning.file_name)
        parts = [
            "Planning cargado: %d día(s) del %s al %s." % (
                planning.days_loaded,
                planning.date_from.strftime("%d/%m/%Y"),
                planning.date_to.strftime("%d/%m/%Y")),
            "%d servicio(s) nuevo(s), %d cambiado(s) y %d quitado(s)." % (
                planning.rows_created, planning.rows_updated,
                planning.rows_removed),
        ]
        if planning.created_clients or planning.created_sites:
            parts.append("Alta de %d cliente(s) y %d obra(s)." % (
                planning.created_clients, planning.created_sites))
        if planning.problems:
            parts.append("%d aviso(s): míralos en Planning › Cargas." % len(
                planning.problems))
        return _ok(" ".join(parts))


class TrafficSendView(SuperuserRequiredMixin, View):
    """
    POST: send the location and time to the crane operators.

    ---

    POST: envía a cada gruista la ubicación de la obra y la hora de sus
    servicios: los marcados (`selected`) o los de un día (`day`). Con
    `only_pending`, solo los que no se han avisado y los que han
    cambiado después del aviso. Siempre solo ubicación y hora (casilla
    fija mientras la dirección no ordene implantar el albarán).
    """

    def post(self, request):
        from crane_albaranes.models import PlanningService
        from crane_albaranes.traffic import send_notices

        cu = request.user.company_user
        services = PlanningService.objects.filter(
            company=cu.company, kind=PlanningService.KIND_SERVICE,
            removed_from_planning=False).select_related(
            "person", "worksite", "client", "company")
        ids = _ids(request)
        day = _date(request.POST.get("day"))
        if ids:
            services = services.filter(pk__in=ids)
        elif day:
            services = services.filter(day=day)
        else:
            return _error("Marca los servicios o elige el día.")
        if request.POST.get("only_pending") == "1":
            from django.db.models import Q

            services = services.filter(
                Q(notice_status=PlanningService.Notice.PENDING)
                | Q(notice_status=PlanningService.Notice.FAILED)
                | Q(changed_after_notice=True))
        services = list(services.order_by("day", "position"))
        if not services:
            return _error("No hay servicios que avisar con eso (las "
                          "anotaciones y lo quitado del planning no se "
                          "avisan).")
        sent, failures = send_notices(services, sent_by=cu)
        message = "%d aviso(s) enviado(s) de %d." % (sent, len(services))
        if failures:
            shown = "; ".join("%s: %s" % f for f in
                              failures[:MAX_FAILURES_SHOWN])
            more = len(failures) - MAX_FAILURES_SHOWN
            message += " Sin enviar: %s%s." % (
                shown, " y %d más" % more if more > 0 else "")
        logger.info("# [TRÁFICO] %s envía %d de %d avisos", cu, sent,
                    len(services))
        if failures and not sent:
            return _error(message)
        return _ok(message)


class NamesAssignView(SuperuserRequiredMixin, View):
    """
    POST: say who the marked planning names are.

    ---

    POST: a los nombres marcados (Tráfico › Nombres) se les asigna el
    trabajador elegido (`person`), se marcan «no es un trabajador»
    (`action=not_worker`) o se dejan sin asignar (`action=clear`). Se
    aplica en el acto a los servicios ya cargados.
    """

    def post(self, request):
        from crane_albaranes.models import PlanningName
        from crane_albaranes.traffic import relink_names
        from document_explorer.models import PersonIdentity

        cu = request.user.company_user
        names = list(PlanningName.objects.filter(company=cu.company,
                                                 pk__in=_ids(request)))
        if not names:
            return _error("Marca primero los nombres.")
        action = request.POST.get("action", "")
        person = None
        if action == "assign":
            person = PersonIdentity.objects.filter(
                company=cu.company, pk=request.POST.get("person") or 0
            ).first()
            if person is None:
                return _error("Elige el trabajador.")
        elif action not in ("not_worker", "clear"):
            return _error("Acción desconocida.")
        for name in names:
            name.person = person
            name.not_a_worker = action == "not_worker"
            name.updated_by = cu
            name.save()
        changed = relink_names(cu.company, {n.key for n in names})
        what = {"assign": "asignado(s) a %s" % (
            person.given_name if person else ""),
            "not_worker": "marcado(s) «no es un trabajador»",
            "clear": "sin asignar"}[action]
        return _ok("%d nombre(s) %s; %d servicio(s) del planning "
                   "cambiado(s)." % (len(names), what, changed))


class ImportSheetView(SuperuserRequiredMixin, View):
    """
    GET: one planning load in the viewer, with its problems.
    ---
    GET: una carga del planning en la ventana, con lo que no se pudo
    reconocer.
    """

    def get(self, request, pk):
        from crane_albaranes.models import PlanningImport

        planning = PlanningImport.objects.filter(
            pk=pk, company=request.user.company_user.company).first()
        if planning is None:
            raise Http404
        return render(request, "new_ui/_traffic_import.html",
                      {"planning": planning})


def _decimal(raw, limit):
    try:
        value = Decimal((raw or "").strip().replace(",", "."))
    except InvalidOperation:
        return None
    if abs(value) > limit:
        return None
    return value.quantize(Decimal("0.000001"))


WORKSITE_FIELDS = ("name", "address", "locality", "province",
                   "project_number", "order_number", "contact_name",
                   "contact_phone", "notes")


class WorksiteSheetView(SuperuserRequiredMixin, View):
    """
    GET: one worksite in the viewer (0 = new). POST: save it.

    ---

    GET: una obra en la ventana, para crearla (0) o modificarla. POST:
    la guarda; sin coordenadas escritas y con «Buscar coordenadas», las
    pide a Google con la ubicación (nunca se inventan al cargar el
    planning).
    """

    def get(self, request, pk):
        from worksites.models import Client, Worksite

        site = Worksite.objects.filter(pk=pk).select_related(
            "client").first() if pk else None
        if pk and site is None:
            raise Http404
        return render(request, "new_ui/_traffic_worksite.html", {
            "site": site,
            "clients": Client.objects.filter(is_active=True).order_by(
                "name").values_list("pk", "name"),
            "map_url": "https://www.google.com/maps/search/?api=1&query="
                       "%s,%s" % (site.latitude, site.longitude)
            if site and site.latitude is not None
            and site.longitude is not None else "",
        })

    def post(self, request, pk):
        from worksites.models import Client, Worksite

        data = request.POST
        site = Worksite.objects.filter(pk=pk).first() if pk else Worksite()
        if site is None:
            raise Http404
        name = (data.get("name") or "").strip()
        if not name:
            return _error("La obra necesita un nombre.")
        client = Client.objects.filter(pk=data.get("client") or 0).first()
        for field in WORKSITE_FIELDS:
            max_length = Worksite._meta.get_field(field).max_length
            value = (data.get(field) or "").strip()
            setattr(site, field, value[:max_length] if max_length
                    else value)
        site.client = client
        site.client_name = client.name if client else site.client_name
        site.latitude = _decimal(data.get("latitude"), 90)
        site.longitude = _decimal(data.get("longitude"), 180)
        found = ""
        if (site.latitude is None or site.longitude is None) and \
                data.get("geocode") == "1":
            from budgets.service_geocode import geocode

            point = geocode(", ".join(p for p in (
                site.address, site.locality, site.province) if p))
            if point:
                site.latitude, site.longitude = point
                found = " Coordenadas puestas por la ubicación (Google)."
            else:
                found = (" Google no ha encontrado esa ubicación: pon las "
                         "coordenadas a mano.")
        site.save()
        if not site.code:
            site.code = "OBRA-%04d" % site.pk
            site.save(update_fields=["code"])
        return _ok("Obra %s guardada.%s" % (site.code, found), id=site.pk)


CLIENT_FIELDS = ("name", "tax_id", "address", "locality", "province",
                 "phone", "email", "notes")


class ClientSheetView(SuperuserRequiredMixin, View):
    """
    GET: one client in the viewer (0 = new). POST: save it.
    ---
    GET: un cliente en la ventana, para crearlo (0) o modificarlo.
    POST: lo guarda.
    """

    def get(self, request, pk):
        from worksites.models import Client

        client = Client.objects.filter(pk=pk).first() if pk else None
        if pk and client is None:
            raise Http404
        return render(request, "new_ui/_traffic_client.html", {
            "client": client,
            "sites": client.worksites.order_by("name")[:50] if client
            else [],
        })

    def post(self, request, pk):
        from worksites.models import Client

        data = request.POST
        client = Client.objects.filter(pk=pk).first() if pk else Client()
        if client is None:
            raise Http404
        if not (data.get("name") or "").strip():
            return _error("El cliente necesita un nombre.")
        for field in CLIENT_FIELDS:
            max_length = Client._meta.get_field(field).max_length
            value = (data.get(field) or "").strip()
            setattr(client, field, value[:max_length] if max_length
                    else value)
        client.save()
        client.worksites.update(client_name=client.name)
        return _ok("Cliente %s guardado." % client.name, id=client.pk)


class SitesMassView(SuperuserRequiredMixin, View):
    """
    POST `what` (obras | clientes), `action` (merge | active | inactive).

    ---

    POST: con las obras o los clientes marcados: unirlos (se queda el
    que tiene más servicios; los nombres de los otros quedan como alias
    para las siguientes cargas del planning) o activarlos/darlos de
    baja.
    """

    def post(self, request):
        from django.db.models import Count

        from crane_albaranes.traffic import merge_clients, merge_worksites
        from worksites.models import Client, Worksite

        cu = request.user.company_user
        what = request.POST.get("what", "")
        action = request.POST.get("action", "")
        model = {"obras": Worksite, "clientes": Client}.get(what)
        if model is None:
            return _error("Acción desconocida.")
        rows = list(model.objects.filter(pk__in=_ids(request)).annotate(
            nui_n=Count("planning_services")).order_by("-nui_n", "pk"))
        if not rows:
            return _error("Marca primero las %s." % (
                "obras" if what == "obras" else "clientes"))
        if action in ("active", "inactive"):
            model.objects.filter(pk__in=[r.pk for r in rows]).update(
                is_active=action == "active")
            return _ok("%d %s %s." % (len(rows), what, "activado(s)"
                                      if action == "active"
                                      else "dado(s) de baja"))
        if action != "merge":
            return _error("Acción desconocida.")
        if len(rows) < 2:
            return _error("Marca al menos dos para unirlos.")
        target, others = rows[0], rows[1:]
        if what == "clientes":
            done = merge_clients(cu.company, target, others)
            label = target.name
        else:
            done = merge_worksites(cu.company, target, others)
            label = "%s %s" % (target.code, target.name)
        logger.info("# [TRÁFICO] %s une %d %s en %s", cu, done, what,
                    label)
        return _ok("%d unido(s) en «%s» (el que más servicios tenía). Las "
                   "siguientes cargas del planning ya no los repiten." % (
                       done, label))
