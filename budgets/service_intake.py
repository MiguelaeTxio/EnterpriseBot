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
import re
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


def _set_insurer(intake, name):
    """
    Store the insurer named in the conversation.

    ---

    Guarda la aseguradora nombrada en la conversación. Devuelve un aviso
    si no se reconoce o hay varias candidatas.
    """
    from budgets.views_services import _match_insurer

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
    from budgets.tirea_extraction import extract_tirea_albaran
    from budgets.views_services import _initial_from_extraction

    extracted = extract_tirea_albaran(file_bytes, mime_type)
    initial = _initial_from_extraction(intake.company, extracted)
    for key, value in initial.items():
        if value in (None, ""):
            continue
        intake.data[key] = _json_value(value)
    if extracted.get("insurer_name") and not intake.data.get("insurer"):
        intake.data["insurer_name_read"] = extracted["insurer_name"]
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
    intake.save(update_fields=["data", "updated_at"])
    return data_summary(intake)


def data_summary(intake):
    """
    What is known and what is missing, for the agent.

    ---

    Lo que se sabe y lo que falta del servicio, para el agente.
    """
    data = intake.data
    known = []
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
    intake.save(update_fields=["data", "updated_at"])
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
    driver, error = _find_driver(drivers, args.get("conductor", ""))
    if error:
        return {"error": error}
    machine = None
    if args.get("maquina"):
        machine, error = _find_machine(machines, args["maquina"])
        if error:
            return {"error": error}
    elif driver.crew is not None:
        machine = driver.crew.machine_card
    else:
        return {"error": "%s no lleva máquina: ¿con cuál va?" % (
            driver.display_name
        )}

    try:
        with transaction.atomic():
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
            unit = traffic.assign(
                company, by, crew.pk, order_pk=work_order.pk,
                force_note=force_note,
            )
            helper_errors = []
            for name in args.get("ayudantes") or []:
                helper, error = _find_driver(drivers, name)
                if error:
                    helper_errors.append(error)
                    continue
                try:
                    traffic.add_helper(company, by, unit.pk, helper.pk)
                except traffic.TrafficError as exc:
                    helper_errors.append(str(exc))
    except traffic.TrafficError as exc:
        return {"error": str(exc)}

    intake.status = ServiceIntake.STATUS_LAUNCHED
    intake.work_order = work_order
    intake.save(update_fields=["status", "work_order", "updated_at"])
    unit.refresh_from_db()
    result = {
        "albaran": unit.albaran_number,
        "conductor": driver.display_name,
        "maquina": machine.code,
    }
    if unit.queued_at is not None:
        result["estado"] = (
            "En cola: se enviará solo cuando %s termine el servicio en "
            "curso." % driver.display_name
        )
    else:
        try:
            traffic.send(company, by, unit.pk, whatsapp_sender)
            result["estado"] = "Enviado al conductor por WhatsApp."
        except traffic.TrafficError as exc:
            result["estado"] = (
                "Creado y asignado, pero no se ha podido enviar: %s "
                "Se puede enviar desde el panel de tráfico." % exc
            )
    if helper_errors:
        result["ayudantes_no_añadidos"] = helper_errors
    logger.info(
        "# [SERVICE INTAKE] %s lanza %s (%s): %s.",
        by.user.username, unit.albaran_number, intake.channel,
        result["estado"],
    )
    return result


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
        "aseguradora": types.Schema(
            type=types.Type.STRING, description="Nombre de la aseguradora.",
        ),
        "tipo_vehiculo": types.Schema(
            type=types.Type.STRING,
            description="Tipo de vehículo según la tarifa de la aseguradora.",
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
                required=["conductor"],
            ),
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
        "Eres Alia, de %(company)s. Hablas por WhatsApp con %(name)s, que "
        "da un servicio de asistencia en carretera (grúa). Tu trabajo es "
        "quitarle todo el trabajo administrativo: recoger los datos, "
        "proponer quién va y lanzar el servicio.\n\n"
        "Hoy es %(today)s.\n\n"
        "CÓMO TRABAJAS:\n"
        "1. Cada vez que te den datos (o llegue una foto ya leída), "
        "llama a guardar_datos. No inventes nada.\n"
        "2. Pide de una sola vez todo lo que falte de lo importante "
        "(aseguradora, tipo de vehículo, expediente, matrícula, "
        "recogida, destino, avería, teléfono del cliente). Si no lo "
        "tienen, sigue: solo aseguradora y tipo de vehículo son "
        "obligatorios.\n"
        "3. Llama a consultar_disponibilidad y di brevemente quién está "
        "libre o volviendo (equipos y conductores), para que elijan.\n"
        "4. Antes de lanzar, resume en pocas líneas (aseguradora, "
        "vehículo, recogida → destino, conductor y máquina) y pregunta "
        "si lo lanzas. Solo con un sí claro llama a lanzar_servicio.\n"
        "5. Manda quien da el servicio: si elige un conductor o una "
        "máquina que figuran en taller, de baja, de vacaciones o "
        "ausentes, avísale UNA vez. Si te confirma que sí están "
        "disponibles, lanza con nota_prevalencia con lo que te ha "
        "dicho. Si están ocupados (asignado o en servicio), dile que "
        "el servicio quedará en cola y saldrá al terminar el actual.\n"
        "6. Tras lanzar, di el nº de albarán y si se ha enviado o queda "
        "en cola. Si una herramienta devuelve un error, explícalo y "
        "pregunta lo necesario.\n\n"
        "ESTILO: mensajes cortos de WhatsApp, en español, sin "
        "formularios ni listas largas. Tutea.\n\n"
        "ASEGURADORAS Y SUS TIPOS DE VEHÍCULO:\n%(insurers)s\n"
    ) % {
        "company": company.name,
        "name": user.get_full_name() or user.username,
        "today": timezone.localdate().strftime("%A %d/%m/%Y"),
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
START_RE = re.compile(
    r"\b(dar|doy|dame|damos|meter|meto|nuevo|nueva|otro|tengo|hay|lanza|"
    r"lanzar|lanzame|mandar|mando|manda|apunta|apuntar|apuntame|sacar)\b"
    r".{0,30}\bservicio"
    r"|^\s*servicio\b"
)


def claim_whatsapp(company, contact, from_number, body, post, num_media):
    """
    Whether a WhatsApp message belongs to giving a service.

    ---

    Decide al momento (dentro del webhook) si un mensaje de WhatsApp es
    de dar un servicio y devuelve su conversación (abierta o nueva); si
    no lo es, None y el mensaje sigue su camino de siempre (averías,
    ayuda, documentos). Lo es cuando quien escribe puede darlos
    (supervisor de asistencia o administrador) y: ya tiene una
    conversación de servicio abierta, o dice que va a dar un servicio, o
    manda una foto o un PDF sin tener documentos pendientes de enviar
    (la foto del servicio de TIREA u otra plataforma). La respuesta se
    prepara después, en segundo plano (`process_whatsapp`).
    """
    company_user = getattr(contact, "company_user", None)
    if not service_giver(company_user):
        return None
    channel = ServiceIntake.CHANNEL_WHATSAPP
    intake = open_intake(company_user, channel)
    if intake is not None:
        return intake
    starts = bool(START_RE.search(_norm(body)))
    content_type = post.get("MediaContentType0", "") if num_media else ""
    if not starts and _is_document(content_type):
        from document_explorer.person_phone_service import (
            resolve_person_by_phone,
        )
        from document_explorer.worker_request_service import expects_media

        person = resolve_person_by_phone(company, from_number)
        starts = person is None or not expects_media(person)
    if not starts:
        return None
    return start_intake(company_user, channel, from_number)


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
                     whatsapp_sender):
    """
    Prepare the answer to a WhatsApp message of a service (Celery).

    ---

    Prepara la respuesta a un mensaje de servicio (en Celery): lee la
    foto si la hay y llama al agente. Devuelve el texto de la respuesta.
    """
    intake = ServiceIntake.objects.select_related(
        "company", "requested_by__user",
    ).get(pk=intake_pk)
    user_text = body
    if media_url and _is_document(content_type):
        from document_explorer.worker_request_service import _download_media

        try:
            summary = apply_photo(
                intake, _download_media(media_url), content_type,
            )
            note = "[Foto del servicio leída: %s]" % json.dumps(
                summary, ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001 -- se le dice al usuario
            logger.exception("# [SERVICE INTAKE] Foto ilegible: %s", exc)
            note = "[Llegó una foto del servicio pero no se ha podido leer.]"
        user_text = "%s\n%s" % (body, note) if body else note
    return reply(intake, user_text, whatsapp_sender)
