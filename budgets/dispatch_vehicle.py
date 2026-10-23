# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/dispatch_vehicle.py
"""
Which of our vehicles fits the job of an assistance service.

Alia (WhatsApp and phone) proposes the crew; this module gives her,
from the data of the service, the kind of job (tow, lift, tyre or
wheel, battery, fuel, small repair, semi-trailer) and the machine
types of the assistance fleet that do it, and tells for every machine
type what it is for. Orientative: the service giver prevails.

---

Qué vehículo nuestro va a cada trabajo de asistencia.

H37-S134, punto 3. Miguel Ángel (S133): Alia tiene que elegir el
vehículo según haya que remolcar, levantar vehículos o sustituir
neumáticos, ruedas, baterías, etc. Este módulo saca de los datos del
servicio qué trabajo hay que hacer y qué tipos de máquina de la flota
de asistencia lo hacen, y dice de cada tipo de máquina para qué sirve.
Es orientativo: manda siempre quien da el servicio. Los tipos son los
`type_name` reales de la familia ASISTENCIA (los mismos de
`MachineDriverRequirement`, migraciones 0043 y 0044).
"""
import re
import unicodedata

PERSONAL = "VEHICULOS DE PERSONAL"
ROAD_ASSISTANCE = "ASISTENCIA EN CARRETERA"
RESCUE = "RESCATE CON GRUA MOVIL ASISTENCIA"
CRANE_20 = "GRUA MOVIL DE 20 TM"
CRANE_30 = "GRUA MOVIL DE 30 TM"
TRACTOR = "CABEZA TRACTORA"
TRACTOR_ASSISTANCE = "CABEZA TRACTORA ASISTENCIA"

# What each machine type of the assistance fleet is for.
# Para qué sirve cada tipo de máquina de la flota de asistencia.
MACHINE_USES = {
    PERSONAL: (
        "va el mecánico a arreglarlo en el sitio: cambio de rueda o "
        "neumático, batería, combustible y averías pequeñas (manguito, "
        "correa, manguera de aire...); no remolca"
    ),
    ROAD_ASSISTANCE: (
        "plataforma: remolca turismos, furgonetas y motos"
    ),
    RESCUE: (
        "remolca camiones, tractoras y autobuses, y rescata vehículos "
        "pesados (vuelco, salida de vía)"
    ),
    CRANE_20: (
        "levanta vehículos: vuelcos, salidas de vía, vehículos caídos "
        "y carga caída, hasta 20 TM"
    ),
    CRANE_30: (
        "levanta vehículos: vuelcos, salidas de vía, vehículos caídos "
        "y carga caída, los más pesados (hasta 30 TM)"
    ),
    TRACTOR: "lleva el semirremolque a su destino",
    TRACTOR_ASSISTANCE: "lleva el semirremolque a su destino",
}

# Kinds of job, in the order they are told to Alia: key, label,
# machine types that do it, and words that point to it.
# Tipos de trabajo, en el orden en que se le dicen a Alia: clave,
# etiqueta, tipos de máquina que lo hacen y palabras que lo señalan.
JOB_KINDS = (
    (
        "lift", "levantar el vehículo (vuelco, salida de vía, caída)",
        (CRANE_20, CRANE_30, RESCUE),
        ("volc", "vuelc", "salida de via", "salido de la via",
         "fuera de la via", "cuneta", "terraplen", "barranco",
         "desnivel", "caido", "caida", "precipit", "atrapad",
         "encallad", "levantar", "izar", "elevar", "carga derramada",
         "perdida de carga"),
    ),
    (
        "tyre", "cambio de rueda o neumático",
        (PERSONAL,),
        ("pinch", "reventon", "reventad", "neumatic", "rueda",
         "cubierta", "llanta"),
    ),
    (
        "battery", "batería",
        (PERSONAL,),
        ("bateria", "no arranca", "sin arranque", "arrancar",
         "pinzas", "descargad"),
    ),
    (
        "fuel", "combustible",
        (PERSONAL,),
        ("sin combustible", "sin gasoil", "sin gasolina",
         "falta de combustible", "falta combustible",
         "combustible equivocado", "error de combustible",
         "repostar", "se ha quedado sin"),
    ),
    (
        "repair", "reparación pequeña en el sitio",
        (PERSONAL,),
        ("manguito", "correa", "manguera", "fusible", "reparar en el",
         "reparacion en el", "reparacion in situ", "en el sitio",
         "in situ", "latiguillo", "abrazadera"),
    ),
    (
        "semitrailer", "llevar el semirremolque a su destino",
        (TRACTOR_ASSISTANCE, TRACTOR),
        ("semirremolque", "semi-remolque", "semi remolque"),
    ),
)
JOB_LABELS = {key: label for key, label, _types, _words in JOB_KINDS}
JOB_TYPES = {key: types for key, _label, types, _words in JOB_KINDS}

# On-site jobs: the personal vehicle with the mechanic, never a crane.
# Trabajos en el sitio: vehículo de personal con mecánico, nunca grúa.
ON_SITE_KINDS = ("tyre", "battery", "fuel", "repair")
# Words that say the vehicle has to be towed anyway.
# Palabras que dicen que el vehículo hay que remolcarlo de todos modos.
TOW_WORDS = (
    "remolc", "trasladar al taller", "llevar al taller", "al taller",
    "arrastr", "no se puede reparar", "no puede seguir",
    "no puede continuar", "inmoviliz",
)
# Heavy assisted vehicles (towed with rescue or mobile crane).
# Vehículos asistidos pesados (se remolcan con rescate o grúa móvil).
HEAVY_WORDS = (
    "camion", "tractora", "cabeza tractora", "autobus", "autocar",
    "semirremolque", "trailer", "articulado", "hormigonera",
    "volquete", "rigido",
)
HEAVY_KG = 3500

# Towing, decided by the weight of the assisted vehicle.
# Remolcar, según el peso del vehículo asistido.
TOW_TYPES = {
    "tow_light": (ROAD_ASSISTANCE,),
    "tow_heavy": (RESCUE, CRANE_20, CRANE_30),
}
JOB_LABELS.update({
    "tow_light": "remolcar un vehículo ligero (turismo, furgoneta, moto)",
    "tow_heavy": "remolcar un vehículo pesado (camión, tractora, autobús)",
})


def _norm(text):
    """
    Lowercase text without accents.

    ---

    Texto en minúsculas y sin tildes.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _has(text, words):
    """
    True if any of the words is in the text.

    ---

    True si alguna de las palabras está en el texto.
    """
    return any(word in text for word in words)


def _weight_kg(data):
    """
    Heaviest of weight, PMA and tare said for the assisted vehicle.

    ---

    El mayor de peso, PMA y tara del vehículo asistido, o None.
    """
    values = []
    for field in ("vehicle_weight", "vehicle_pma", "vehicle_tare"):
        raw = str(data.get(field) or "").replace(",", ".").strip()
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return max(values) if values else None


def machine_use(type_name):
    """
    What a machine type is for, or "" if it is not an assistance type.

    ---

    Para qué sirve un tipo de máquina, o "" si no es de asistencia.
    """
    return MACHINE_USES.get(_norm(type_name).upper(), "")


def job_for(data):
    """
    Kind of job and machine types that fit, from the service data.

    `data` is the data of the intake (`ServiceIntake.data`, the fields
    of the order). Returns a dict with `trabajos` (kinds), `pesado`
    (heavy assisted vehicle) and `tipos_de_maquina` (in order of
    preference), or None if the data say nothing yet.

    ---

    Trabajo y tipos de máquina adecuados según los datos del servicio
    (los de `ServiceIntake.data`). Lee la avería, el código de avería,
    los comentarios y las observaciones de la aseguradora, las notas y
    el vehículo asistido. Devuelve `trabajos` (claves de JOB_KINDS),
    `pesado` y `tipos_de_maquina` por orden de preferencia; None si
    los datos todavía no dicen nada del trabajo.
    """
    job_text = _norm(" ".join(str(data.get(field) or "") for field in (
        "breakdown_description", "breakdown_code", "insurer_comments",
        "company_observations", "extra_notes",
    )))
    vehicle_text = _norm(" ".join(str(data.get(field) or "") for field in (
        "vehicle_type_name", "vehicle_brand", "vehicle_model",
        "vehicle_type_label", "vehicle_subtype_label",
    )))
    if not job_text and not vehicle_text:
        return None
    weight = _weight_kg(data)
    heavy = _has(vehicle_text + " " + job_text, HEAVY_WORDS) or (
        weight is not None and weight > HEAVY_KG
    )
    found = [
        key for key, _label, _types, words in JOB_KINDS
        if _has(job_text + " " + vehicle_text, words)
    ]
    must_tow = _has(job_text, TOW_WORDS)
    on_site = [
        k for k in found if k in ON_SITE_KINDS
    ] if "lift" not in found and not must_tow else []
    if on_site:
        # Repaired on the spot: the personal vehicle, nothing else.
        # Se arregla en el sitio: el vehículo de personal, nada más.
        kinds = on_site
    else:
        kinds = ["lift" if "lift" in found else (
            "tow_heavy" if heavy else "tow_light"
        )]
        if "semitrailer" in found:
            # Criterion 3: tractor and semi-trailer always together.
            # Criterio 3: tractora y semirremolque siempre juntos.
            kinds.append("semitrailer")
    types = []
    for kind in kinds:
        for type_name in TOW_TYPES.get(kind) or JOB_TYPES[kind]:
            if type_name not in types:
                types.append(type_name)
    return {
        "trabajos": kinds,
        "pesado": heavy,
        "tipos_de_maquina": types,
    }


def job_hint(data):
    """
    One line for Alia with the job and the vehicle that fits, or "".

    ---

    Una línea para Alia con el trabajo y el vehículo adecuado, o "".
    """
    job = job_for(data)
    if job is None:
        return ""
    parts = [
        "%s → %s" % (
            JOB_LABELS[kind],
            " o ".join(TOW_TYPES.get(kind) or JOB_TYPES[kind]),
        )
        for kind in job["trabajos"]
    ]
    # Several kinds are several crews in the same service.
    # Varios trabajos son varios equipos en el mismo servicio.
    joiner = "; y en otro equipo del mismo servicio, "
    return "%s (orientativo: manda quien da el servicio)" % (
        joiner.join(parts)
    )
