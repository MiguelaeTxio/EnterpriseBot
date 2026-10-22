# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_intake.py
"""
H37 (S133). Giving a service by conversation (WhatsApp, later phone).

---

H37 (S133). Dar un servicio conversando (WhatsApp; después, la
llamada al robot). Reunión con Pepe (anexo V37 6.3): los servicios
entran por foto, llamada o WhatsApp, y lanzarlos tiene que ser
automático para quitar el trabajo administrativo a quien los da.

Un supervisor de asistencia (o un administrador) escribe "voy a dar un
servicio" o manda la foto del servicio (TIREA u otra plataforma). Alia,
con Gemini y unas herramientas sobre los datos reales:
1. recoge los datos del servicio (de la foto y de lo que le digan) y
   pide de una vez lo que falte;
2. dice qué equipos, conductores y máquinas hay libres o volviendo;
3. resume y pide confirmación;
4. crea la orden y el albarán, asigna el equipo (forma el equipo si
   hace falta, o lo deja en cola si está ocupado) y envía el albarán al
   conductor.

Manda quien da el servicio: si confirma que una máquina o un conductor
sí están disponibles aunque figuren en taller o ausentes, se asigna
igual y queda anotado (`assistance_traffic.assign(force_note=...)`).
La lógica de asignación es la del panel de tráfico; aquí solo se
conversa y se traduce a sus funciones.
"""
import datetime
import json
import logging
import unicodedata
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from budgets.models import ServiceIntake, WorkOrderAssistance
from ivr_config.models import CompanyUser

logger = logging.getLogger(__name__)

# Roles that can give services by WhatsApp or phone (meeting with Pepe:
# assistance supervisors for now; administrators too).
# Roles que pueden dar servicios por WhatsApp o llamada (reunión con
# Pepe: de momento los supervisores de asistencia; y administradores).
SERVICE_GIVER_ROLES = (
    CompanyUser.ROLE_ASSIST_SUPERVISOR,
    CompanyUser.ROLE_ADMIN,
)
# An open conversation without messages for this long is abandoned: the
# next message starts a new one instead of continuing a stale service.
# Una conversación sin mensajes en este tiempo se da por abandonada.
INTAKE_IDLE_LIMIT = datetime.timedelta(hours=2)
MAX_TOOL_ROUNDS = 6
# S133, real incident: Vertex cut the reading of the photo with a 504
# (DEADLINE_EXCEEDED) at 88 s, intermittently. In the background the
# photo gets more time and one more try.
# Incidencia real S133: Vertex cortaba la lectura de la foto con un 504
# a los 88 s, de forma intermitente. En segundo plano, más plazo y un
# reintento.
PHOTO_TIMEOUT_MS = 150_000
PHOTO_ATTEMPTS = 2

# Data the agent can fill: tool argument -> order form field.
# Datos que puede rellenar el agente: argumento -> campo del formulario.
DATA_FIELDS = {
    "fecha_servicio": ("service_date", "Fecha del servicio, AAAA-MM-DD."),
    "expediente": ("expediente", "Nº de expediente de la aseguradora."),
    "matricula": ("vehicle_plate", "Matrícula del vehículo asistido."),
    "marca": ("vehicle_brand", "Marca del vehículo asistido."),
    "modelo": ("vehicle_model", "Modelo del vehículo asistido."),
    "color": ("vehicle_color", "Color del vehículo asistido."),
    "nombre_cliente": ("client_name", "Nombre del cliente o asegurado."),
    "conductor_asistido": (
        "insured_name", "Conductor del vehículo asistido.",
    ),
    "telefono_cliente": ("client_phone", "Teléfono de contacto del cliente."),
    "recogida": ("pickup_location", "Dirección o punto de recogida."),
    "localidad_recogida": ("vehicle_locality", "Localidad de recogida."),
    "provincia_recogida": ("pickup_province", "Provincia de recogida."),
    "destino": ("delivery_address", "Dirección de entrega o destino."),
    "localidad_destino": ("delivery_locality", "Localidad de destino."),
    "provincia_destino": ("delivery_province", "Provincia de destino."),
    "averia": ("breakdown_description", "Avería o motivo del servicio."),
    "comentarios": ("insurer_comments", "Comentarios de la aseguradora."),
    "notas": ("extra_notes", "Notas internas de oficina."),
}
# Important for the albarán besides the required ones.
# Importantes para el albarán además de los obligatorios.
IMPORTANT_FIELDS = (
    ("expediente", "expediente"),
    ("vehicle_plate", "matrícula"),
    ("pickup_location", "recogida"),
    ("delivery_address", "destino"),
    ("breakdown_description", "avería"),
    ("client_phone", "teléfono del cliente"),
)
CIF_HELP = (
    "CIF de la empresa del grupo que da el servicio (decide la ficha de "
    "aseguradora: Mondial / Transgrual o Mondial / Gruas Alvarez...)."
)
TEAMS_HELP = (
    "Si van varios equipos al mismo servicio (p. ej. una grúa para la "
    "tractora averiada y una cabeza tractora para el semirremolque): uno "
    "por equipo, con su conductor, su máquina y sus ayudantes. Con un "
    "solo equipo basta conductor y maquina."
)
VEHICLE_TYPE_HELP = (
    "Categoría de tarifa del vehículo ASISTIDO (el del cliente: turismo, "
    "furgoneta, camión, semirremolque...), nunca nuestra grúa o máquina."
)

# How a head of traffic thinks (Miguel Ángel, S133: "plantéatelo desde
# el punto de vista del conductor... ¿dejamos tirado al camionero con
# su camión y un manguito roto?"). Orientative: the giver prevails.
# Cómo piensa una jefa de tráfico: desde el cliente que está parado en
# la carretera. Orientativo: manda siempre quien da el servicio.
DISPATCH_CRITERIA = (
    "Ponte en el lugar del conductor que está parado en la carretera: "
    "el objetivo es que él y TODO lo que lleva (vehículo, remolque, "
    "carga) acaben resueltos. Nunca dejes a nadie tirado con parte de "
    "su vehículo. Lee los comentarios de la aseguradora antes que los "
    "campos sueltos: ahí está lo que pasa de verdad (qué está averiado, "
    "qué está bien, adónde quiere ir, el tope de importe...).\n"
    "1. ¿Se puede arreglar en el sitio? Averías pequeñas (manguito, "
    "rueda, batería, gasoil, correa, una manguera de aire...): lo "
    "primero es mandar una ASISTENCIA EN CARRETERA o un VEHÍCULO DE "
    "PERSONAL con mecánico para que siga su viaje. Si no está claro, "
    "pregúntalo a quien da el servicio en una sola frase.\n"
    "2. Si no se puede arreglar, se remolca lo averiado al taller: "
    "turismo, furgoneta o moto con ASISTENCIA EN CARRETERA (plataforma); "
    "camión, tractora o autobús con RESCATE / GRÚA MÓVIL según peso "
    "(20 TM o 30 TM). Vuelco, salida de vía o carga caída: GRÚA MÓVIL / "
    "RESCATE.\n"
    "3. Si es un camión con semirremolque y la tractora no puede seguir, "
    "son DOS cosas: la tractora averiada (reparar en el sitio o "
    "remolcarla al taller) y el semirremolque (una CABEZA TRACTORA "
    "nuestra lo lleva a su destino). Propón los dos equipos en el mismo "
    "servicio, salvo que quien lo da diga otra cosa.\n"
)


# ---------------------------------------------------------------------------
# Who can give services and which conversation is open.
# Quién puede dar servicios y qué conversación está abierta.
# ---------------------------------------------------------------------------

def service_giver(company_user):
    """
    Whether the panel user can give services by conversation.

    ---

    Si el usuario puede dar servicios por WhatsApp o llamada.
    """
    return bool(
        company_user is not None
        and company_user.is_active
        and company_user.role in SERVICE_GIVER_ROLES
    )


def open_intake(company_user, channel):
    """
    Open conversation of the user in a channel, or None.

    ---

    Conversación abierta del usuario en un canal, o None. Las que llevan
    más de INTAKE_IDLE_LIMIT sin mensajes se cancelan.
    """
    intake = ServiceIntake.objects.filter(
        requested_by=company_user, channel=channel,
        status=ServiceIntake.STATUS_OPEN,
    ).order_by("-updated_at").first()
    if intake and timezone.now() - intake.updated_at > INTAKE_IDLE_LIMIT:
        intake.status = ServiceIntake.STATUS_CANCELLED
        intake.save(update_fields=["status", "updated_at"])
        return None
    return intake


def start_intake(company_user, channel, phone_number=""):
    """
    New conversation to give a service.

    ---

    Nueva conversación para dar un servicio.
    """
    return ServiceIntake.objects.create(
        company=company_user.company,
        requested_by=company_user,
        channel=channel,
        phone_number=phone_number,
        data={"service_date": timezone.localdate().isoformat()},
    )


# ---------------------------------------------------------------------------
# Data of the service.
# Datos del servicio.
# ---------------------------------------------------------------------------

def _norm(text):
    """
    Lower case without accents, to compare names.

    ---

    Minúsculas sin tildes, para comparar nombres.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _json_value(value):
    """
    Value of the extraction stored as JSON (form format).

    ---

    Valor de la extracción guardado en JSON, en el formato que espera
    el formulario de la orden.
    """
    if isinstance(value, datetime.datetime):
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M") \
            if timezone.is_aware(value) else value.strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _insurers(company):
    """
    Active insurers of the company with their vehicle types.

    ---

    Aseguradoras activas de la empresa con sus tipos de vehículo.
    """
    from budgets.models import Insurer

    return Insurer.objects.filter(
        company=company, is_active=True,
    ).prefetch_related("vehicle_types").order_by("name")


# A document being read holds the texts that arrive meanwhile, so the
# answer covers both (S133: the PDF and "voy a dar un servicio" arrived
# together and Alia asked for the PDF she was already reading).
# Mientras se lee un documento, los textos que llegan esperan y la
# respuesta los atiende juntos.
READING_LIMIT = datetime.timedelta(minutes=5)


def _save_data(intake):
    """
    Save the data keeping the texts queued by other messages.

    ---

    Guarda los datos sin pisar los textos que otro mensaje haya dejado
    en espera mientras tanto (`pending_texts`).
    """
    with transaction.atomic():
        fresh = ServiceIntake.objects.select_for_update().get(pk=intake.pk)
        intake.data["pending_texts"] = fresh.data.get("pending_texts", [])
        if not intake.data["pending_texts"]:
            intake.data.pop("pending_texts")
        intake.save(update_fields=["data", "updated_at"])


def mark_reading(intake):
    """
    Note that a document of the conversation is being read.

    ---

    Apunta que se está leyendo un documento de la conversación (lo
    llama el webhook antes de encolar la lectura).
    """
    with transaction.atomic():
        fresh = ServiceIntake.objects.select_for_update().get(pk=intake.pk)
        fresh.data["reading_since"] = timezone.now().isoformat()
        fresh.save(update_fields=["data", "updated_at"])


def _hold_text(intake_pk, body):
    """
    Keep a text for the answer of the document being read, if any.

    ---

    Si se está leyendo un documento, guarda el texto para que lo
    atienda esa respuesta y devuelve True (no se contesta aparte).
    """
    with transaction.atomic():
        fresh = ServiceIntake.objects.select_for_update().get(pk=intake_pk)
        since = fresh.data.get("reading_since")
        if not since:
            return False
        started = datetime.datetime.fromisoformat(since)
        if timezone.now() - started > READING_LIMIT:
            return False
        fresh.data.setdefault("pending_texts", []).append(body)
        fresh.save(update_fields=["data", "updated_at"])
        return True


def _release_texts(intake):
    """
    End the reading and take the texts that waited for it.

    ---

    Termina la lectura y devuelve los textos que esperaban.
    """
    with transaction.atomic():
        fresh = ServiceIntake.objects.select_for_update().get(pk=intake.pk)
        texts = fresh.data.pop("pending_texts", [])
        fresh.data.pop("reading_since", None)
        fresh.save(update_fields=["data", "updated_at"])
    intake.data.pop("pending_texts", None)
    intake.data.pop("reading_since", None)
    return texts


def _set_insurer(intake, name):
    """
    Store the insurer named in the conversation.

    ---

    Guarda la aseguradora nombrada en la conversación. Devuelve un aviso
    si no se reconoce o hay varias candidatas.
    """
    from budgets.views_services import (
        _match_insurer,
        _match_insurer_by_tax_id,
    )

    insurer = None
    if intake.data.get("company_tax_id"):
        insurer = _match_insurer_by_tax_id(
            intake.company, intake.data["company_tax_id"], name,
        )
    if insurer is None:
        insurer = _match_insurer(intake.company, name)
    if insurer is None:
        wanted = _norm(name)
        candidates = [
            i for i in _insurers(intake.company)
            if wanted and wanted in _norm(i.name)
        ]
        if len(candidates) != 1:
            return "No reconozco la aseguradora «%s»." % name
        insurer = candidates[0]
    if intake.data.get("insurer") != insurer.pk:
        intake.data.pop("vehicle_type", None)
        intake.data.pop("vehicle_type_name", None)
    intake.data["insurer"] = insurer.pk
    intake.data["insurer_name"] = insurer.name
    return ""


def _set_tax_id(intake, tax_id):
    """
    Store the CIF of the service and resolve the insurer card with it.

    ---

    Guarda el CIF del servicio (reunión con Pepe, S133: "la aseguradora
    va por el CIF") y con él la empresa del grupo. Si ya se sabe el
    nombre de la aseguradora, elige su ficha de esa empresa ("Mondial /
    Transgrual" frente a "Mondial / Gruas Alvarez"). Devuelve un aviso
    si el CIF no es de ninguna empresa del grupo.
    """
    from budgets.views_services import own_company_for_tax_id

    profile = own_company_for_tax_id(tax_id)
    intake.data["company_tax_id"] = str(tax_id).strip()
    if profile is None:
        intake.data.pop("own_company_name", None)
        return "El CIF «%s» no es de ninguna empresa del grupo." % tax_id
    intake.data["own_company_name"] = profile.legal_name
    name = intake.data.get("insurer_name") or intake.data.get(
        "insurer_name_read",
    )
    if name:
        _set_insurer(intake, name)
    return ""


def _set_vehicle_type(intake, name):
    """
    Store the vehicle type of the insurer named in the conversation.

    ---

    Guarda el tipo de vehículo (de la aseguradora ya elegida).
    """
    from budgets.models import Insurer

    insurer = Insurer.objects.filter(pk=intake.data.get("insurer")).first()
    if insurer is None:
        return "Primero hace falta la aseguradora para el tipo de vehículo."
    wanted = _norm(name)
    types = list(insurer.vehicle_types.filter(is_active=True))
    exact = [t for t in types if _norm(t.name) == wanted]
    matches = exact or [
        t for t in types
        if wanted and (wanted in _norm(t.name) or _norm(t.name) in wanted)
    ]
    if len(matches) != 1:
        return "Tipo de vehículo «%s» no reconocido para %s. Opciones: %s." % (
            name, insurer.name, ", ".join(t.name for t in types),
        )
    intake.data["vehicle_type"] = matches[0].pk
    intake.data["vehicle_type_name"] = matches[0].name
    return ""


def apply_photo(intake, file_bytes, mime_type):
    """
    Fill the conversation data from the photo of the service.

    ---

    Rellena los datos con la foto del servicio (TIREA u otra
    plataforma), con el mismo extractor que el alta desde foto del
    panel. Devuelve un resumen de lo leído para el agente.
    """
    return apply_extracted(intake, extract_photo(file_bytes, mime_type))


def extract_photo(file_bytes, mime_type):
    """
    Read the photo with Gemini, retrying a cut call once.

    ---

    Lee la foto con Gemini (una sola llamada que además dice si es un
    servicio: `is_service_order`), con un reintento si Vertex la corta.
    """
    from budgets.tirea_extraction import extract_tirea_albaran

    for attempt in range(1, PHOTO_ATTEMPTS + 1):
        try:
            return extract_tirea_albaran(
                file_bytes, mime_type, timeout_ms=PHOTO_TIMEOUT_MS,
            )
        except Exception as exc:  # noqa: BLE001 -- 5xx de Vertex: reintento
            transient = any(
                code in str(exc)
                for code in ("500", "502", "503", "504", "DEADLINE")
            )
            if attempt == PHOTO_ATTEMPTS or not transient:
                raise
            logger.warning(
                "# [SERVICE INTAKE] Lectura de la foto cortada (%s); "
                "reintento %d.", exc, attempt + 1,
            )


def apply_extracted(intake, extracted):
    """
    Store what was read in the photo and summarise it for the agent.

    ---

    Guarda lo leído en la foto y devuelve el resumen para el agente.
    """
    from budgets.views_services import _initial_from_extraction

    initial = _initial_from_extraction(intake.company, extracted)
    for key, value in initial.items():
        if value in (None, ""):
            continue
        intake.data[key] = _json_value(value)
    if extracted.get("insurer_name") and not intake.data.get("insurer"):
        intake.data["insurer_name_read"] = extracted["insurer_name"]
    if extracted.get("company_tax_id"):
        from budgets.views_services import own_company_for_tax_id

        intake.data["company_tax_id"] = extracted["company_tax_id"]
        profile = own_company_for_tax_id(extracted["company_tax_id"])
        if profile is not None:
            intake.data["own_company_name"] = profile.legal_name
    if initial.get("insurer"):
        from budgets.models import Insurer, VehicleType

        intake.data["insurer_name"] = Insurer.objects.get(
            pk=initial["insurer"],
        ).name
        if initial.get("vehicle_type"):
            intake.data["vehicle_type_name"] = VehicleType.objects.get(
                pk=initial["vehicle_type"],
            ).name
    intake.data["photo"] = True
    intake.data["origin"] = WorkOrderAssistance.ORIGIN_PHOTO
    _save_data(intake)
    return data_summary(intake)


def data_summary(intake):
    """
    What is known and what is missing, for the agent.

    ---

    Lo que se sabe y lo que falta del servicio, para el agente.
    """
    data = intake.data
    known = []
    if data.get("own_company_name"):
        known.append(
            "empresa del grupo (por el CIF %s): %s"
            % (data.get("company_tax_id", ""), data["own_company_name"])
        )
    elif data.get("company_tax_id"):
        known.append(
            "CIF leído, no es de ninguna empresa del grupo: %s"
            % data["company_tax_id"]
        )
    if data.get("insurer_name"):
        known.append("aseguradora: %s" % data["insurer_name"])
    elif data.get("insurer_name_read"):
        known.append(
            "aseguradora leída en la foto, sin reconocer: %s"
            % data["insurer_name_read"]
        )
    if data.get("vehicle_type_name"):
        known.append("tipo de vehículo: %s" % data["vehicle_type_name"])
    for arg, (field, _help) in DATA_FIELDS.items():
        if data.get(field):
            known.append("%s: %s" % (arg, data[field]))
    missing = []
    if not data.get("insurer"):
        missing.append("aseguradora (obligatoria)")
    if not data.get("vehicle_type"):
        missing.append("tipo de vehículo (obligatorio)")
    for field, label in IMPORTANT_FIELDS:
        if not data.get(field):
            missing.append(label)
    return {"datos": known, "faltan": missing}


def save_data(intake, args):
    """
    Tool: store the data given in the conversation.

    ---

    Herramienta: guarda los datos dichos en la conversación.
    """
    warnings = []
    if args.get("cif"):
        warning = _set_tax_id(intake, args["cif"])
        if warning:
            warnings.append(warning)
    if args.get("aseguradora"):
        warning = _set_insurer(intake, args["aseguradora"])
        if warning:
            warnings.append(warning)
    if args.get("tipo_vehiculo"):
        warning = _set_vehicle_type(intake, args["tipo_vehiculo"])
        if warning:
            warnings.append(warning)
    for arg, (field, _help) in DATA_FIELDS.items():
        value = args.get(arg)
        if value not in (None, ""):
            intake.data[field] = str(value).strip()
    _save_data(intake)
    result = data_summary(intake)
    if warnings:
        result["avisos"] = warnings
    return result


# ---------------------------------------------------------------------------
# Who and what is available.
# Quién y qué está disponible.
# ---------------------------------------------------------------------------

def availability(company):
    """
    Tool: crews, drivers and machines with their state.

    ---

    Herramienta: equipos, conductores sin máquina y máquinas sin
    conductor, con su estado (los mismos del panel de tráfico).
    """
    from budgets import assistance_traffic as traffic

    drivers, machines, crews = traffic._current(company)
    crew_rows = []
    for crew in crews:
        row = "%s con %s (%s): %s" % (
            crew.driver_card.display_name, crew.machine_card.code,
            crew.machine_card.type_name or crew.machine_card.brand_model,
            crew.state_label,
        )
        if crew.current_unit is not None:
            row += " con el albarán %s" % crew.current_unit.albaran_number
        if crew.queue:
            row += "; %d en cola" % len(crew.queue)
        crew_rows.append(row)
    driver_rows = [
        "%s: %s" % (d.display_name, d.state_label)
        for d in drivers if d.crew is None
    ]
    machine_rows = [
        "%s %s (%s): %s" % (
            m.code, m.plate, m.type_name or m.brand_model, m.state_label,
        )
        for m in machines if m.crew is None
    ]
    return {
        "equipos": crew_rows,
        "conductores_sin_maquina": driver_rows,
        "maquinas_sin_conductor": machine_rows,
        "nota": (
            "Libre y Regresando se pueden asignar ya. Asignado o En "
            "servicio: el nuevo servicio queda en cola y sale solo al "
            "terminar. En taller, de baja, vacaciones o ausente: solo si "
            "quien da el servicio confirma que sí está disponible."
        ),
    }


def _find_driver(drivers, name):
    """
    Driver whose name matches what was said, or an error.

    ---

    Conductor cuyo nombre coincide con lo dicho (todas las palabras),
    o un mensaje con las candidatas.
    """
    words = _norm(name).split()
    matches = [
        d for d in drivers
        if words and all(w in _norm(d.display_name) for w in words)
    ]
    if len(matches) == 1:
        return matches[0], ""
    if not matches:
        return None, "No encuentro ningún conductor «%s»." % name
    return None, "Hay varios: %s. ¿Cuál?" % ", ".join(
        d.display_name for d in matches
    )


def _find_machine(machines, code):
    """
    Machine whose internal code or plate is the one said.

    ---

    Máquina cuyo código interno o matrícula es el dicho.
    """
    wanted = _norm(code).replace(" ", "").replace("-", "")
    for machine in machines:
        if wanted in (
            _norm(machine.code),
            _norm(machine.plate).replace(" ", "").replace("-", ""),
        ):
            return machine, ""
    return None, "No encuentro la máquina «%s»." % code


# ---------------------------------------------------------------------------
# Launching the service.
# Lanzar el servicio.
# ---------------------------------------------------------------------------

def _order_form(intake):
    """
    Order form filled with the conversation data.

    ---

    Formulario de la orden con los datos de la conversación (mismas
    validaciones que el alta del panel).
    """
    from budgets.forms_services import WorkOrderAssistanceForm

    form = WorkOrderAssistanceForm(company=intake.company)
    post = {}
    for name, field in form.fields.items():
        value = intake.data.get(name)
        if value in (None, "", False):
            continue
        post[name] = "on" if value is True else value
    return WorkOrderAssistanceForm(post, company=intake.company)


def launch(intake, args, whatsapp_sender):
    """
    Tool: create the order and the albarán, assign and send.

    ---

    Herramienta: crea la orden y su albarán, forma el equipo si hace
    falta, lo asigna (o lo deja en cola si está ocupado) y envía el
    albarán al conductor. `nota_prevalencia`: lo que ha confirmado quien
    da el servicio cuando el conductor o la máquina figuran ausentes o
    en taller.
    """
    from budgets import assistance_traffic as traffic
    from budgets.models import AssistanceCrew

    company = intake.company
    by = intake.requested_by
    force_note = (args.get("nota_prevalencia") or "").strip()
    if force_note:
        force_note = "%s (%s por %s)" % (
            force_note, intake.get_channel_display(),
            by.user.get_full_name() or by.user.username,
        )

    form = _order_form(intake)
    if not form.is_valid():
        return {"error": "Faltan o no valen estos datos: %s" % "; ".join(
            "%s: %s" % (field, " ".join(errors))
            for field, errors in form.errors.items()
        )}

    drivers, machines, _crews = traffic._current(company)
    teams = []
    for team in args.get("equipos") or [args]:
        driver, error = _find_driver(drivers, team.get("conductor", ""))
        if error:
            return {"error": error}
        if team.get("maquina"):
            machine, error = _find_machine(machines, team["maquina"])
            if error:
                return {"error": error}
        elif driver.crew is not None:
            machine = driver.crew.machine_card
        else:
            return {"error": "%s no lleva máquina: ¿con cuál va?" % (
                driver.display_name
            )}
        teams.append((driver, machine, team.get("ayudantes") or []))
    if len({d.pk for d, _m, _h in teams}) < len(teams) or len(
        {m.pk for _d, m, _h in teams}
    ) < len(teams):
        return {"error": "Hay un conductor o una máquina repetidos."}

    launched = []
    helper_errors = []
    try:
        with transaction.atomic():
            work_order = form.save(commit=False)
            work_order.company = company
            work_order.operator = by
            work_order.created_by = by
            work_order.origin = intake.data.get("origin") or (
                WorkOrderAssistance.ORIGIN_PHONE
                if intake.channel == ServiceIntake.CHANNEL_PHONE
                else WorkOrderAssistance.ORIGIN_WHATSAPP
            )
            if not work_order.destination:
                work_order.destination = (
                    work_order.delivery_address or ""
                )[:255]
            form.save()
            for driver, machine, helpers in teams:
                crew = AssistanceCrew.objects.filter(
                    driver=driver, machine=machine,
                ).first()
                if crew is None:
                    traffic.pair(
                        company, by, driver.pk, machine.pk,
                        force_note=force_note,
                    )
                    crew = AssistanceCrew.objects.get(
                        driver=driver, machine=machine,
                    )
                unit = traffic.assign(
                    company, by, crew.pk, order_pk=work_order.pk,
                    force_note=force_note,
                )
                for name in helpers:
                    helper, error = _find_driver(drivers, name)
                    if error:
                        helper_errors.append(error)
                        continue
                    try:
                        traffic.add_helper(company, by, unit.pk, helper.pk)
                    except traffic.TrafficError as exc:
                        helper_errors.append(str(exc))
                launched.append((unit, driver, machine))
    except traffic.TrafficError as exc:
        return {"error": str(exc)}

    intake.status = ServiceIntake.STATUS_LAUNCHED
    intake.work_order = work_order
    intake.save(update_fields=["status", "work_order", "updated_at"])
    albaranes = []
    for unit, driver, machine in launched:
        unit.refresh_from_db()
        row = {
            "albaran": unit.albaran_number,
            "conductor": driver.display_name,
            "maquina": machine.code,
        }
        if unit.queued_at is not None:
            row["estado"] = (
                "En cola: se enviará solo cuando %s termine el servicio "
                "en curso." % driver.display_name
            )
        else:
            try:
                traffic.send(company, by, unit.pk, whatsapp_sender)
                row["estado"] = "Enviado al conductor por WhatsApp."
            except traffic.TrafficError as exc:
                row["estado"] = (
                    "Creado y asignado, pero no se ha podido enviar: %s "
                    "Se puede enviar desde el panel de tráfico." % exc
                )
        logger.info(
            "# [SERVICE INTAKE] %s lanza %s (%s): %s.",
            by.user.username, unit.albaran_number, intake.channel,
            row["estado"],
        )
        albaranes.append(row)
    result = albaranes[0] if len(albaranes) == 1 else {
        "orden": work_order.work_order_number, "albaranes": albaranes,
    }
    if helper_errors:
        result["ayudantes_no_añadidos"] = helper_errors
    return result


def reread_photo(intake):
    """
    Tool: read again the last photo of the service.

    ---

    Herramienta: vuelve a leer la última foto del servicio que llegó por
    WhatsApp (cuando la lectura falló o la piden otra vez).
    """
    from document_explorer.worker_request_service import _download_media

    photo = intake.data.get("last_photo") or {}
    if not photo.get("url"):
        return {"error": "No ha llegado ninguna foto en este servicio."}
    try:
        return apply_photo(
            intake, _download_media(photo["url"]), photo["content_type"],
        )
    except Exception as exc:  # noqa: BLE001 -- se informa al agente
        logger.exception("# [SERVICE INTAKE] Relectura fallida: %s", exc)
        return {"error": (
            "Tampoco se ha podido leer ahora (el servicio de lectura de "
            "Google no responde a tiempo). Que la manden de nuevo más "
            "tarde, o que den los datos escritos."
        )}


def cancel(intake):
    """
    Tool: drop the service being given.

    ---

    Herramienta: abandona el servicio que se estaba dando.
    """
    intake.status = ServiceIntake.STATUS_CANCELLED
    intake.save(update_fields=["status", "updated_at"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# The agent (Gemini with function calling).
# El agente (Gemini con herramientas).
# ---------------------------------------------------------------------------

def _tool_declarations():
    """
    Tools offered to Gemini.

    ---

    Herramientas que se ofrecen a Gemini.
    """
    from google.genai import types

    string = types.Schema(type=types.Type.STRING)
    data_props = {
        "cif": types.Schema(
            type=types.Type.STRING, description=CIF_HELP,
        ),
        "aseguradora": types.Schema(
            type=types.Type.STRING, description="Nombre de la aseguradora.",
        ),
        "tipo_vehiculo": types.Schema(
            type=types.Type.STRING, description=VEHICLE_TYPE_HELP,
        ),
    }
    for arg, (_field, help_text) in DATA_FIELDS.items():
        data_props[arg] = types.Schema(
            type=types.Type.STRING, description=help_text,
        )
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="guardar_datos",
            description=(
                "Guarda los datos del servicio que te han dado. Llámala "
                "cada vez que recibas datos nuevos. Devuelve lo que se "
                "sabe y lo que falta."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT, properties=data_props,
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_disponibilidad",
            description=(
                "Equipos (conductor con su máquina), conductores sin "
                "máquina y máquinas sin conductor, con su estado actual."
            ),
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="lanzar_servicio",
            description=(
                "Crea la orden y el albarán, asigna conductor y máquina y "
                "envía el albarán al conductor (o lo deja en cola si está "
                "ocupado). Solo cuando quien da el servicio lo haya "
                "confirmado."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "equipos": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "conductor": string,
                                "maquina": string,
                                "ayudantes": types.Schema(
                                    type=types.Type.ARRAY, items=string,
                                ),
                            },
                            required=["conductor"],
                        ),
                        description=TEAMS_HELP,
                    ),
                    "conductor": types.Schema(
                        type=types.Type.STRING,
                        description="Nombre del conductor elegido.",
                    ),
                    "maquina": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Código interno de la máquina (p. ej. A49). "
                            "Vacío si va con la de su equipo."
                        ),
                    ),
                    "ayudantes": types.Schema(
                        type=types.Type.ARRAY, items=string,
                        description="Nombres de los ayudantes, si van.",
                    ),
                    "nota_prevalencia": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Solo si el conductor o la máquina figuran "
                            "ausentes o en taller y quien da el servicio "
                            "ha confirmado que sí están disponibles: lo "
                            "que ha dicho, con sus palabras."
                        ),
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="volver_a_leer_foto",
            description=(
                "Vuelve a leer la última foto o PDF del servicio que llegó "
                "por WhatsApp. Úsala si la lectura falló o te piden "
                "leerla otra vez."
            ),
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="cancelar_servicio",
            description="Abandona este servicio si lo piden.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
    ])]


def _system_prompt(intake):
    """
    Instructions of the agent.

    ---

    Instrucciones del agente.
    """
    company = intake.company
    user = intake.requested_by.user
    insurers = "\n".join(
        "- %s: %s" % (
            insurer.name,
            ", ".join(t.name for t in insurer.vehicle_types.all()
                      if t.is_active) or "sin tipos",
        )
        for insurer in _insurers(company)
    )
    return (
        "Eres Alia, la jefa de tráfico de %(company)s. Hablas por "
        "WhatsApp con %(name)s, que da un servicio de asistencia en "
        "carretera. Tu trabajo es quitarle todo el trabajo: recoger los "
        "datos, DECIDIR tú qué máquina y qué equipo van, proponerlo y "
        "lanzarlo. Piensa como una jefa de tráfico con experiencia: no "
        "preguntes lo que puedes deducir de los datos.\n\n"
        "Hoy es %(today)s.\n\n"
        "DOS COSAS QUE NO DEBES CONFUNDIR:\n"
        "- «Tipo de vehículo» es la categoría de tarifa del vehículo "
        "ASISTIDO (el del cliente). Dedúcelo tú de modelo, tipo, "
        "comentarios y avería (p. ej. un «SEMIRREMOLQUE» es el tipo "
        "semirremolque/remolque de la aseguradora) y guárdalo con "
        "guardar_datos. Pregunta solo si de verdad hay dos opciones "
        "posibles.\n"
        "- La «máquina» es NUESTRO vehículo, el que va a hacer el "
        "servicio. La eliges tú con estos criterios orientativos:\n"
        "%(criteria)s"
        "Si los comentarios corrigen o precisan los campos (punto exacto "
        "de recogida, destino real, la avería de verdad), guarda lo "
        "correcto con guardar_datos.\n\n"
        "EMPRESA Y ASEGURADORA: van por el CIF. Si guardar_datos ya "
        "devuelve la aseguradora (la ficha de la empresa del grupo del "
        "CIF), no la preguntes. Si falta, pregunta solo la empresa del "
        "grupo o el CIF (guárdalo con el argumento cif), nunca una "
        "lista de fichas.\n\n"
        "CÓMO TRABAJAS:\n"
        "1. Cada vez que te den datos (o llegue una foto ya leída), "
        "llama a guardar_datos, incluido el tipo de vehículo que hayas "
        "deducido. No inventes datos del servicio.\n"
        "2. Llama a consultar_disponibilidad y PROPÓN el equipo o los "
        "equipos concretos (conductor + máquina del tipo que toca) libres "
        "o regresando, los más adecuados, explicando en una línea qué "
        "hace cada uno. Si van varios, lánzalos juntos en el mismo "
        "servicio con el argumento equipos. Si no hay ninguno de ese "
        "tipo libre, propón el que quedará libre antes (el servicio "
        "quedará en cola) o un "
        "conductor libre con una máquina de ese tipo sin conductor. "
        "No preguntes «¿qué vehículo asigno?»: propón tú.\n"
        "3. En el mismo mensaje pide de una sola vez lo importante que "
        "falte (expediente, matrícula, recogida, destino, avería, "
        "teléfono del cliente). Si no lo tienen, sigue: solo aseguradora "
        "y tipo de vehículo son obligatorios.\n"
        "4. Antes de lanzar, resume en pocas líneas (aseguradora, "
        "vehículo asistido, recogida → destino, conductor y máquina) y "
        "pregunta si lo lanzas. Si te cambian el equipo o la máquina, "
        "obedece. Solo con un sí claro llama a lanzar_servicio.\n"
        "5. Manda quien da el servicio: si elige un conductor o una "
        "máquina que figuran en taller, de baja, de vacaciones o "
        "ausentes, avísale UNA vez. Si te confirma que sí están "
        "disponibles, lanza con nota_prevalencia con lo que te ha "
        "dicho. Si están ocupados (asignado o en servicio), dile que "
        "el servicio quedará en cola y saldrá al terminar el actual.\n"
        "Si la foto no se pudo leer y te piden intentarlo otra vez, "
        "usa volver_a_leer_foto.\n"
        "6. Tras lanzar, di el nº de albarán y si se ha enviado o queda "
        "en cola. Si una herramienta devuelve un error, explícalo y "
        "pregunta lo necesario.\n\n"
        "ESTILO: mensajes cortos de WhatsApp, en español, sin "
        "formularios ni listas largas. Tutea. Formato de WhatsApp: "
        "negrita con UN asterisco a cada lado (*así*), nunca dos; sin "
        "almohadillas ni viñetas con asterisco (usa guiones).\n\n"
        "ASEGURADORAS Y SUS TIPOS DE VEHÍCULO (ASISTIDO):\n%(insurers)s\n"
    ) % {
        "company": company.name,
        "name": user.get_full_name() or user.username,
        "today": timezone.localdate().strftime("%A %d/%m/%Y"),
        "criteria": DISPATCH_CRITERIA,
        "insurers": insurers or "(ninguna dada de alta)",
    }


def _history(intake):
    """
    Conversation as Gemini contents.

    ---

    Conversación como contenidos de Gemini.
    """
    from google.genai import types

    return [
        types.Content(
            role="user" if turn["role"] == "user" else "model",
            parts=[types.Part(text=turn["text"])],
        )
        for turn in intake.conversation
        if turn.get("text")
    ]


def _run_tool(intake, name, args, whatsapp_sender):
    """
    Execute one tool call of the agent.

    ---

    Ejecuta una llamada a herramienta del agente.
    """
    if name == "guardar_datos":
        return save_data(intake, args)
    if name == "consultar_disponibilidad":
        return availability(intake.company)
    if name == "lanzar_servicio":
        return launch(intake, args, whatsapp_sender)
    if name == "volver_a_leer_foto":
        return reread_photo(intake)
    if name == "cancelar_servicio":
        return cancel(intake)
    return {"error": "Herramienta desconocida."}


def reply(intake, user_text, whatsapp_sender):
    """
    Answer one message of the person giving the service.

    ---

    Contesta un mensaje de quien da el servicio: llama a Gemini con las
    herramientas, ejecuta las que pida (hasta MAX_TOOL_ROUNDS vueltas) y
    guarda los dos turnos en la conversación. Devuelve el texto de la
    respuesta.
    """
    from google.genai import types

    from whatsapp.services import BreakdownAgentService, _build_genai_client

    client = _build_genai_client()
    config = types.GenerateContentConfig(
        system_instruction=_system_prompt(intake),
        tools=_tool_declarations(),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
        temperature=0.2,
    )
    contents = _history(intake) + [
        types.Content(role="user", parts=[types.Part(text=user_text)]),
    ]
    text = ""
    for _round in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=BreakdownAgentService.GEMINI_MODEL,
            contents=contents,
            config=config,
        )
        calls = response.function_calls or []
        if not calls:
            text = (response.text or "").strip()
            break
        contents.append(response.candidates[0].content)
        parts = []
        for call in calls:
            args = dict(call.args or {})
            try:
                result = _run_tool(intake, call.name, args, whatsapp_sender)
            except Exception as exc:  # noqa: BLE001 -- se informa al agente
                logger.exception(
                    "# [SERVICE INTAKE] Error en %s: %s", call.name, exc,
                )
                result = {"error": "Error interno: %s" % exc}
            logger.info(
                "# [SERVICE INTAKE] %s(%s) -> %s", call.name,
                json.dumps(args, ensure_ascii=False)[:300],
                json.dumps(result, ensure_ascii=False, default=str)[:300],
            )
            parts.append(types.Part.from_function_response(
                name=call.name, response={"result": result},
            ))
        contents.append(types.Content(role="user", parts=parts))
    if not text:
        text = "Perdona, no he podido terminar. ¿Me lo repites?"

    intake.refresh_from_db()
    intake.conversation = intake.conversation + [
        {"role": "user", "text": user_text},
        {"role": "model", "text": text},
    ]
    intake.save(update_fields=["conversation", "updated_at"])
    return text


# ---------------------------------------------------------------------------
# WhatsApp entry point.
# Entrada desde WhatsApp.
# ---------------------------------------------------------------------------

# "voy a dar un servicio", "tengo otro servicio", "servicio: ...".
def claim_whatsapp(company, contact, from_number):
    """
    Open service conversation of the sender, or None.

    ---

    Conversación de servicio abierta de quien escribe, o None. Decidir
    si un mensaje NUEVO es dar un servicio no se hace aquí ni con
    palabras clave (Miguel Ángel, S133: "tiene que ser que Gemini lea el
    mensaje y sepa qué es lo que le estamos diciendo"): el texto lo
    decide el asistente general (marcador SERVICE_MARKER, ver
    whatsapp/views.py) y un documento lo mira Gemini en segundo plano
    (`process_whatsapp` con `decide`).
    """
    company_user = getattr(contact, "company_user", None)
    if not service_giver(company_user):
        return None
    return open_intake(company_user, ServiceIntake.CHANNEL_WHATSAPP)


# Marker the general assistant answers with when the person wants to
# give a service; the message is handed over to the service agent.
# Marcador con el que contesta el asistente general cuando la persona
# quiere dar un servicio: el mensaje pasa al agente de servicios.
SERVICE_MARKER = "[DAR_SERVICIO]"


def general_assistant_instruction():
    """
    Line added to the general assistant for those who give services.

    ---

    Línea que se añade al asistente general de WhatsApp cuando quien
    escribe puede dar servicios: Gemini decide por el sentido del
    mensaje, no por palabras.
    """
    return (
        "- Esta persona puede DAR servicios de asistencia en carretera. "
        "Si por lo que dice quiere dar, pasar, meter o lanzar un servicio "
        "(que salga una grúa o una asistencia a por un vehículo, un "
        "servicio de una aseguradora, de TIREA...), sea como sea que lo "
        "diga, responde ÚNICAMENTE con %s y nada más: otra compañera "
        "se encarga.\n" % SERVICE_MARKER
    )


def start_from_assistant(company_user, from_number):
    """
    Open the service conversation the general assistant handed over.

    ---

    Abre la conversación de servicio que el asistente general ha pasado.
    """
    return open_intake(
        company_user, ServiceIntake.CHANNEL_WHATSAPP,
    ) or start_intake(
        company_user, ServiceIntake.CHANNEL_WHATSAPP, from_number,
    )


def _is_document(content_type):
    """
    Whether the attachment is a photo or a PDF.

    ---

    Si el adjunto es una foto o un PDF.
    """
    return content_type.startswith("image/") or (
        content_type == "application/pdf"
    )


def process_whatsapp(intake_pk, body, media_url, content_type,
                     whatsapp_sender, from_number="", decide=False):
    """
    Prepare the answer to a WhatsApp message of a service (Celery).

    ---

    Prepara la respuesta a un mensaje de servicio (en Celery): lee la
    foto si la hay y llama al agente. Devuelve el texto de la respuesta,
    o None si no hay que contestar: un texto que llega mientras se lee
    un documento espera a esa respuesta, y un documento que resulta no
    ser un servicio va a Documentación.

    `decide`: el documento llegó sin conversación abierta, así que puede
    no ser un servicio. Lo dice la misma lectura de Gemini
    (`is_service_order`), sin una llamada aparte (S133: tardaba dos
    minutos).
    """
    intake = ServiceIntake.objects.select_related(
        "company", "requested_by__user",
    ).get(pk=intake_pk)
    if not (media_url and _is_document(content_type)):
        if _hold_text(intake_pk, body):
            return None
        return reply(intake, body, whatsapp_sender)

    from document_explorer.worker_request_service import _download_media

    intake.data["last_photo"] = {
        "url": media_url, "content_type": content_type,
    }
    _save_data(intake)
    extracted = None
    try:
        extracted = extract_photo(_download_media(media_url), content_type)
    except Exception as exc:  # noqa: BLE001 -- se le dice al usuario
        logger.exception("# [SERVICE INTAKE] Foto ilegible: %s", exc)
    if decide and extracted is not None and (
        extracted.get("is_service_order") is False
    ):
        return _not_a_service(intake, body, media_url, content_type,
                              from_number, whatsapp_sender)
    if extracted is None:
        note = "[Llegó una foto del servicio pero no se ha podido leer.]"
    else:
        note = "[Foto del servicio leída: %s]" % json.dumps(
            apply_extracted(intake, extracted), ensure_ascii=False,
        )
    texts = [text for text in [body] + _release_texts(intake) if text]
    return reply(intake, "\n".join(texts + [note]), whatsapp_sender)


def _not_a_service(intake, body, media_url, content_type, from_number,
                   whatsapp_sender):
    """
    A document that is not a service: to Documentación.

    ---

    El documento no es un servicio: pasa a Documentación como cualquier
    adjunto. La conversación abierta solo para él se cancela; si
    mientras tanto escribieron algo, Alia lo atiende.
    """
    from document_explorer.person_phone_service import (
        resolve_person_by_phone,
    )
    from document_explorer.worker_request_service import (
        expects_media,
        register_incoming_media,
    )

    person = resolve_person_by_phone(intake.company, from_number)
    if person is not None and expects_media(person):
        register_incoming_media(person, from_number, {
            "MediaUrl0": media_url, "MediaContentType0": content_type,
        })
    intake.data.pop("last_photo", None)
    _save_data(intake)
    texts = [text for text in [body] + _release_texts(intake) if text]
    if texts:
        return reply(intake, "\n".join(texts), whatsapp_sender)
    if not intake.conversation:
        intake.status = ServiceIntake.STATUS_CANCELLED
        intake.save(update_fields=["status", "updated_at"])
    return None


# ---------------------------------------------------------------------------
# Phone call to the robot (Gemini Live, vox_bridge).
# Llamada al robot (Gemini Live, vox_bridge).
# ---------------------------------------------------------------------------

VOICE_TOOL_PREFIX = "servicio_"


def service_giver_for_call(twilio_number, caller_number):
    """
    Panel user calling who can give services, or None.

    ---

    Usuario del panel que llama y puede dar servicios (supervisor de
    asistencia o administrador), por el número del que llama y la
    empresa del número llamado; None si no.
    """
    from ivr_config.models import Contact, PhoneNumber

    if not caller_number:
        return None
    phone = PhoneNumber.objects.filter(
        number=twilio_number, is_active=True,
    ).select_related("company").first()
    if phone is None:
        return None
    contact = Contact.objects.filter(
        company=phone.company, phone_number=caller_number,
    ).select_related("company_user__user").first()
    company_user = getattr(contact, "company_user", None)
    return company_user if service_giver(company_user) else None


def voice_instruction(company_user):
    """
    Block of the call instructions for giving a service.

    ---

    Bloque de instrucciones de la llamada para dar un servicio: se
    añade a las de siempre cuando quien llama puede darlos.
    """
    from budgets.models import Insurer

    user = company_user.user
    insurers = ", ".join(
        Insurer.objects.filter(
            company=company_user.company, is_active=True,
        ).order_by("name").values_list("name", flat=True)
    )
    return (
        "\n\nDAR UN SERVICIO DE ASISTENCIA POR TELÉFONO:\n"
        "Quien llama es %(name)s, que puede dar servicios de asistencia "
        "(grúa). Si dice que va a dar un servicio, actúa como su jefa de "
        "tráfico y encárgate tú de todo, sin preguntar lo que puedas "
        "deducir:\n"
        "1. Pregunta los datos de forma natural y guárdalos con "
        "servicio_guardar_datos cada vez que te den alguno: empresa del "
        "grupo o CIF (decide la ficha de aseguradora), aseguradora, "
        "expediente, matrícula, marca y modelo, recogida, destino, "
        "avería y teléfono del cliente. Las matrículas y expedientes, "
        "repítelos para confirmar.\n"
        "2. El tipo de vehículo es la tarifa del vehículo ASISTIDO (el "
        "del cliente): dedúcelo tú (un semirremolque es tipo "
        "semirremolque o remolque) y guárdalo; pregunta solo si hay "
        "duda real. No lo confundas con nuestra máquina.\n"
        "3. Lo que se manda lo decides tú, como jefa de tráfico:\n"
        "%(criteria)s"
        "Consulta servicio_disponibilidad y PROPÓN el equipo o los "
        "equipos concretos, libres o regresando. Nunca preguntes qué "
        "vehículo asignar. Si van varios, lánzalos juntos con el "
        "argumento equipos.\n"
        "4. Antes de lanzar, resume (aseguradora, vehículo, de dónde a "
        "dónde, conductor y máquina) y pregunta si lo lanzas. Si te "
        "cambia el equipo, obedece. Solo con un sí claro llama a "
        "servicio_lanzar.\n"
        "5. Manda quien llama: si elige un conductor o una máquina que "
        "figuran en taller, de baja, de vacaciones o ausentes, avísale "
        "una vez; si confirma que sí están disponibles, lanza con "
        "nota_prevalencia con lo que te ha dicho. Si están ocupados, el "
        "servicio queda en cola y sale solo al terminar el actual.\n"
        "6. Al lanzar, di el número de albarán y si se ha enviado o queda "
        "en cola. Si una herramienta da error, explícalo y pregunta.\n"
        "Frases cortas: quien llama puede ir conduciendo.\n"
        "Aseguradoras: %(insurers)s."
    ) % {
        "name": user.get_full_name() or user.username,
        "criteria": DISPATCH_CRITERIA,
        "insurers": insurers or "ninguna dada de alta",
    }


def voice_tool_declarations():
    """
    Tools of the call, as plain dictionaries for vox_bridge.

    ---

    Herramientas de la llamada, como diccionarios para que vox_bridge
    construya sus FunctionDeclaration (mismo formato que sus otras
    herramientas).
    """
    data_props = {
        "cif": {"type": "string", "description": CIF_HELP},
        "aseguradora": {
            "type": "string", "description": "Nombre de la aseguradora.",
        },
        "tipo_vehiculo": {
            "type": "string", "description": VEHICLE_TYPE_HELP,
        },
    }
    for arg, (_field, help_text) in DATA_FIELDS.items():
        data_props[arg] = {"type": "string", "description": help_text}
    return [
        {
            "name": VOICE_TOOL_PREFIX + "guardar_datos",
            "description": (
                "Guarda los datos del servicio que te han dado. Devuelve lo "
                "que se sabe, lo que falta y, si hace falta, las opciones "
                "de tipo de vehículo."
            ),
            "parameters": {"type": "object", "properties": data_props},
        },
        {
            "name": VOICE_TOOL_PREFIX + "disponibilidad",
            "description": (
                "Equipos (conductor con su máquina), conductores sin "
                "máquina y máquinas sin conductor, con su estado."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": VOICE_TOOL_PREFIX + "lanzar",
            "description": (
                "Crea la orden y el albarán, asigna conductor y máquina y "
                "envía el albarán al conductor (o lo deja en cola). Solo "
                "con la confirmación de quien llama."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "equipos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "conductor": {"type": "string"},
                                "maquina": {"type": "string"},
                                "ayudantes": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["conductor"],
                        },
                        "description": TEAMS_HELP,
                    },
                    "conductor": {
                        "type": "string",
                        "description": "Nombre del conductor elegido.",
                    },
                    "maquina": {
                        "type": "string",
                        "description": (
                            "Código de la máquina (p. ej. A49); vacío si va "
                            "con la de su equipo."
                        ),
                    },
                    "ayudantes": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Nombres de los ayudantes, si van.",
                    },
                    "nota_prevalencia": {
                        "type": "string",
                        "description": (
                            "Solo si figuran ausentes o en taller y quien "
                            "llama confirma que sí están disponibles: lo "
                            "que ha dicho."
                        ),
                    },
                },
            },
        },
        {
            "name": VOICE_TOOL_PREFIX + "cancelar",
            "description": "Abandona el servicio si lo piden.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]


def run_voice_tool(company_user_pk, caller_number, name, args):
    """
    Execute a tool of the call.

    ---

    Ejecuta una herramienta de la llamada sobre la conversación de
    servicio abierta de quien llama (la crea con la primera). Devuelve
    el resultado para Gemini.
    """
    import os

    company_user = CompanyUser.objects.select_related(
        "company", "user",
    ).get(pk=company_user_pk)
    channel = ServiceIntake.CHANNEL_PHONE
    intake = open_intake(company_user, channel) or start_intake(
        company_user, channel, caller_number,
    )
    tool = name[len(VOICE_TOOL_PREFIX):]
    args = dict(args or {})
    intake.conversation = intake.conversation + [{
        "role": "tool",
        "text": "%s %s" % (tool, json.dumps(args, ensure_ascii=False)),
    }]
    intake.save(update_fields=["conversation", "updated_at"])
    if tool == "guardar_datos":
        return save_data(intake, args)
    if tool == "disponibilidad":
        return availability(intake.company)
    if tool == "lanzar":
        return launch(
            intake, args, os.environ.get("TWILIO_WHATSAPP_SENDER", ""),
        )
    if tool == "cancelar":
        return cancel(intake)
    return {"error": "Herramienta desconocida."}
