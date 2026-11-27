# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/traffic.py
"""
Real cranes planning (one sheet per day) and the notices to the crane
operators (S165).

---

Tráfico (S165, sesión invasora sobre H11). El planning real de Carlos
Núñez es un Excel con una hoja por día (nombre «25-11-2026», título
«MIERCOLES 25 NOVIEMBRE 2026») y las columnas PERSONAL, VEHICULO, TONS,
EMPRESA, LUGAR DE TRABAJO, HORA, OBSERVACIONES, PRECIO, CONTRATADO,
OFERT. ECON. y CONTACTO; debajo de los servicios va el cuadro de estado
de la flota («Gruas Moviles»...), que no se carga. Aquí:

- Se lee tal cual, por rango de días, y cada día se actualiza sin
  duplicar (PlanningService). Lo que ya se avisó y cambia de hora o de
  lugar queda «cambiado después del aviso»; lo que se quita del
  planning después de avisarlo se conserva marcado.
- Los nombres se reconocen solos (DNI, mote, palabras del nombre con
  abreviaturas e iniciales) o por la tabla PlanningName, que la
  oficina rellena una vez en Tráfico › Nombres.
- Clientes (EMPRESA) y obras (LUGAR DE TRABAJO) se dan de alta solos,
  sin coordenadas inventadas.
- Al gruista solo se le envía la ubicación de la obra y la hora
  (services.LOCATION_ONLY_NOTICE), cada envío queda en PlanningNotice
  con su estado de entrega de Twilio.
"""
import datetime
import io
import logging
import os
import re
import unicodedata

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from crane_albaranes.models import (
    PlanningAlias,
    PlanningImport,
    PlanningName,
    PlanningNotice,
    PlanningService,
)

logger = logging.getLogger(__name__)

STATUS_SALT = "crane-planning-notice-status"
DEFAULT_DAYS_AHEAD = 14
# Columnas del planning, en su orden real (por si la cabecera de alguna
# hoja viene cambiada: en dos hojas LUGAR DE TRABAJO lleva la fecha).
COLUMNS = (
    ("person", ("personal",)),
    ("vehicle", ("vehiculo",)),
    ("tonnage", ("tons", "toneladas", "tonelaje")),
    ("client", ("empresa",)),
    ("place", ("lugar de trabajo", "lugar")),
    ("time", ("hora",)),
    ("observations", ("observaciones",)),
    ("price", ("precio",)),
    ("contracted_by", ("contratado",)),
    ("offer_ref", ("ofert econ", "oferta economica", "oferta")),
    ("contact", ("contacto",)),
)
# Donde empieza el cuadro de estado de la flota: ahí acaba el planning.
FLEET_TABLE_MARKERS = ("gruas moviles", "camion grua", "tractoras")
MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
# Abreviaturas de nombres que se usan en el planning y el cuadrante.
NAME_ABBREVIATIONS = {
    "fco": "francisco", "fran": "francisco", "ant": "antonio",
    "jav": "javier", "manolo": "manuel", "pepe": "jose",
    "paco": "francisco", "juanjo": "juan jose", "rafa": "rafael",
}


# ---------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------
def plain(text):
    """
    Lowercase ASCII words separated by one space.
    ---
    El texto sin tildes, en minúsculas y con solo letras y cifras
    separadas por un espacio (clave de nombres, clientes y obras).
    """
    text = unicodedata.normalize("NFKD", str(text or "")).encode(
        "ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean(value, size):
    """
    Cell value as a trimmed one-line text of at most `size` chars.
    ---
    Valor de una celda como texto de una línea, sin espacios de más y
    cortado a `size` caracteres.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())[:size]


def parse_time(value):
    """
    Planned time from the HORA cell, or None.
    ---
    La hora del servicio a partir de la celda HORA, que viene como
    texto («8.00», «8´00», «7'30», «16 H», «7 A 19 H») o, a veces, como
    hora de Excel. Sin una hora clara («X LA TARDE», «NOCHE»), None.
    """
    if isinstance(value, datetime.datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, datetime.time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, float) and 0 < value < 1:
        minutes = int(round(value * 24 * 60))
        return datetime.time(minutes // 60 % 24, minutes % 60)
    text = str(value or "").strip().lstrip(".,;:´'’` ")
    match = re.match(r"^(\d{1,2})\s*[.:,´'’`hH]+\s*(\d{1,2})\b", text)
    if match:
        hour, minute = int(match.group(1)), match.group(2)
        # «8.3» es 8:30, como «8.30».
        minute = int(minute) * (10 if len(minute) == 1 else 1)
    else:
        match = re.match(r"^(\d{1,2})(?:\s*[hH])?(?:\s|$|-|[aA]\b)", text)
        if not match:
            return None
        hour, minute = int(match.group(1)), 0
    if hour > 23 or minute > 59:
        return None
    return datetime.time(hour, minute)


def sheet_day(name, title=""):
    """
    Day of a planning sheet from its name («25-11-2026») or title.
    ---
    El día de una hoja: por su nombre («25-11-2026», con o sin espacios
    o «(2)» detrás) o, si no, por su título («MIERCOLES 25 NOVIEMBRE
    2026»).
    """
    match = re.match(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b",
                     name or "")
    if match:
        day, month, year = (int(g) for g in match.groups())
        year += 2000 if year < 100 else 0
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    words = plain(title).split()
    for index, word in enumerate(words):
        if word in MONTHS and index and index + 1 < len(words):
            if words[index - 1].isdigit() and words[index + 1].isdigit():
                try:
                    return datetime.date(int(words[index + 1]),
                                         MONTHS[word],
                                         int(words[index - 1]))
                except ValueError:
                    return None
    return None


# ---------------------------------------------------------------------
# Lectura del Excel
# ---------------------------------------------------------------------
def _header_columns(row):
    """
    {key: column index} from the header row (by name, else by order).
    ---
    Columnas de la cabecera: por su nombre y, la que no se reconozca, en
    su posición de siempre (A..K).
    """
    found = {}
    for index, value in enumerate(row):
        label = plain(value)
        for key, aliases in COLUMNS:
            if key not in found and label in aliases:
                found[key] = index
    for position, (key, _aliases) in enumerate(COLUMNS):
        found.setdefault(key, position)
    return found


def read_planning(data, date_from=None, date_to=None):
    """
    Read the planning workbook: ({day: [row dicts]}, [problems]).

    ---

    Lee el Excel del planning (bytes) y devuelve las filas de cada día
    entre `date_from` y `date_to` (incluidos; None = sin límite) y los
    problemas de las hojas que no se han podido leer. Cada fila trae
    su número de fila en la hoja y los textos de sus columnas. Las filas
    sin nada más que el nombre (el trabajador libre ese día) no se
    devuelven. Si hay dos hojas del mismo día («06-09-2026» y
    «06-09-2026 (2)»), vale la de nombre limpio.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), data_only=True,
                             read_only=True)
    days, problems, origin = {}, [], {}
    try:
        for sheet in workbook.worksheets:
            name = sheet.title.strip()
            rows = list(sheet.iter_rows(max_col=11, values_only=True))
            title = " ".join(str(v) for v in (rows[0] if rows else ())
                             if v not in (None, ""))
            day = sheet_day(name, title)
            if day is None:
                problems.append({"row": "Hoja «%s»" % name, "reasons": [
                    "no se sabe de qué día es"]})
                continue
            if date_from and day < date_from or date_to and day > date_to:
                continue
            duplicate = "(" in name
            if day in origin:
                if duplicate or not origin[day][1]:
                    problems.append({"row": "Hoja «%s»" % name, "reasons": [
                        "repetida: vale la hoja «%s»" % origin[day][0]]})
                    continue
                problems.append({"row": "Hoja «%s»" % origin[day][0],
                                 "reasons": ["repetida: vale la hoja «%s»"
                                             % name]})
            header = next((i for i, row in enumerate(rows)
                           if row and plain(row[0]) == "personal"), None)
            if header is None:
                problems.append({"row": "Hoja «%s»" % name, "reasons": [
                    "sin la fila de cabecera PERSONAL"]})
                continue
            columns = _header_columns(rows[header])
            items = []
            for number, row in enumerate(rows[header + 1:],
                                         start=header + 2):
                row = tuple(row) + (None,) * (11 - len(row))
                if any(plain(v) in FLEET_TABLE_MARKERS for v in row):
                    break
                item = {key: row[index] for key, index in columns.items()}
                item["row"] = number
                if all(item[key] in (None, "") or not str(
                        item[key]).strip() for key, _a in COLUMNS
                        if key != "person"):
                    continue
                items.append(item)
            days[day] = items
            origin[day] = (name, duplicate)
    finally:
        workbook.close()
    return days, problems


# ---------------------------------------------------------------------
# Reconocer trabajadores, vehículos, clientes y obras
# ---------------------------------------------------------------------
def _expand(word):
    """Name word with the abbreviations expanded (may be several)."""
    return NAME_ABBREVIATIONS.get(word, word).split() or [word]


def _close(word, token):
    """
    True if two name words are the same written slightly differently.
    ---
    Dos palabras de nombre son la misma escrita algo distinto: una
    empieza por la otra («PETRUS»/«PETRU») o, con 5 letras o más, solo
    cambia, sobra o falta una («ALEXANDRO»/«ALEXANDRU»).
    """
    short, long_ = sorted((word, token), key=len)
    if len(short) >= 4 and long_.startswith(short):
        return True
    if len(short) < 5 or len(long_) - len(short) > 1:
        return False
    if len(short) == len(long_):
        return sum(a != b for a, b in zip(short, long_)) == 1
    return any(long_[:i] + long_[i + 1:] == short
               for i in range(len(long_)))


def _word_matches(word, tokens, used):
    """
    Index of the name token a planning word matches, or None.
    ---
    Índice de la palabra del nombre con la que casa una del planning:
    igual, por su abreviatura (FCO = Francisco), si es una inicial
    («A.», «J») por su primera letra, y si no, escrita algo distinto
    (_close). Primero la igual, después la parecida.
    """
    for index, token in enumerate(tokens):
        if index in used:
            continue
        if token == word:
            return index
        if len(word) == 1 and token.startswith(word):
            return index
    for index, token in enumerate(tokens):
        if index not in used and _close(word, token):
            return index
    return None


class NameResolver:
    """
    Who each planning name is, with memory of the office's choices.

    ---

    Reconoce a los trabajadores por el texto del planning o del
    cuadrante. Primero la tabla PlanningName (lo que ya asignó la
    oficina, o «no es un trabajador»); si no, DNI, mote exacto o que
    todas las palabras escritas (con abreviaturas e iniciales) estén en
    su nombre y apellidos, primero entre los activos y luego entre los
    de baja. Lo que no casa con uno solo se deja sin reconocer, nunca
    se adivina.
    """

    def __init__(self, company):
        from document_explorer.models import PersonIdentity

        self.company = company
        self.names = {n.key: n for n in PlanningName.objects.filter(
            company=company)}
        self.people = []
        # También las fichas sin empresa (muchos antiguos y gruistas).
        for person in PersonIdentity.objects.filter(
                Q(company=company) | Q(company__isnull=True)).only(
                "pk", "dni", "given_name", "first_surname",
                "second_surname", "nickname", "is_active_employee"):
            tokens = plain(" ".join((
                person.given_name or "", person.first_surname or "",
                person.second_surname or ""))).split()
            self.people.append((person, tokens,
                                plain(person.nickname or "")))
        self._cache = {}

    def resolve(self, text):
        """
        (person or None, reason) for a planning text.
        ---
        (trabajador o None, motivo). Motivo vacío si se ha reconocido o
        si la tabla dice que no es un trabajador.
        """
        key = plain(text)
        if not key:
            return None, ""
        if key in self._cache:
            return self._cache[key]
        result = self._resolve(key, text)
        self._cache[key] = result
        return result

    def is_ignored(self, text):
        """True if the office marked this text as not a worker."""
        name = self.names.get(plain(text))
        return bool(name and name.not_a_worker)

    def _resolve(self, key, text):
        name = self.names.get(key)
        if name is not None:
            if name.not_a_worker:
                return None, ""
            if name.person_id:
                return name.person, ""
        person, why = self._auto(key, text)
        if person is not None and name is not None:
            # Apuntado «Sin asignar» en una carga anterior y ahora
            # reconocido solo: queda asignado en la lista de nombres.
            PlanningName.objects.filter(pk=name.pk, person__isnull=True,
                                        not_a_worker=False).update(
                person=person)
            name.person = person
        return person, why

    def _auto(self, key, text):
        dni = re.sub(r"[^0-9A-Za-z]", "", str(text)).upper()
        if re.match(r"^[0-9XYZ]\d{7}[A-Z]$", dni):
            found = [p for p, _t, _n in self.people
                     if (p.dni or "").upper() == dni]
            if len(found) == 1:
                return found[0], ""
        for active in (True, False):
            found = [p for p, _t, nick in self.people
                     if nick and nick == key
                     and bool(p.is_active_employee) == active]
            if len(found) == 1:
                return found[0], ""
        words = []
        for word in key.split():
            words.extend(_expand(word))
        for active in (True, False):
            matches = []
            for person, tokens, nick in self.people:
                if bool(person.is_active_employee) != active:
                    continue
                pool = tokens + nick.split()
                used = set()
                for word in words:
                    index = _word_matches(word, pool, used)
                    if index is None:
                        break
                    used.add(index)
                else:
                    matches.append(person)
            if len(matches) == 1:
                return matches[0], ""
            if len(matches) > 1:
                return None, "«%s» puede ser %d trabajadores" % (
                    text.strip(), len(matches))
        return None, "«%s» sin reconocer" % text.strip()


def _vehicle_key(text):
    """
    «A-56», «a56», «H-08» -> "A56", "A56", "H8"; "" if not a code.
    ---
    Clave de un código de vehículo: letras y número sin guion ni ceros a
    la izquierda.
    """
    match = re.match(r"^\s*([A-Za-z]{1,3})\s*-?\s*0*(\d{1,4})\b",
                     str(text or ""))
    if not match:
        return ""
    return "%s%s" % (match.group(1).upper(), match.group(2))


class MachineResolver:
    """
    Machine of a VEHICULO cell («A-56», «A-64/67»: the first one).

    ---

    El centro de gasto de la celda VEHICULO: el primer código que traiga
    («A-64/67» -> A-64), entre los activos primero.
    """

    def __init__(self, company):
        from fleet.models import MachineAsset

        self.by_key = {}
        for machine in MachineAsset.objects.filter(
                company=company).order_by("-is_active", "pk").only(
                "pk", "code", "is_active"):
            self.by_key.setdefault(_vehicle_key(machine.code), machine)
        self.by_key.pop("", None)

    def resolve(self, text):
        return self.by_key.get(_vehicle_key(text))


class SiteResolver:
    """
    Client (EMPRESA) and worksite (LUGAR DE TRABAJO), created if new.

    ---

    Cliente por su nombre sin tildes ni signos y obra por cliente y
    lugar, mirando antes los alias guardados al unir duplicados
    (PlanningAlias); si no existen se dan de alta (obra con su código
    OBRA-0001, sin coordenadas: el mapa solo va cuando la oficina las
    pone).
    """

    def __init__(self, company):
        from worksites.models import Client, Worksite

        self.Client, self.Worksite = Client, Worksite
        self.clients = {}
        for client in Client.objects.order_by("-is_active", "pk"):
            self.clients.setdefault(plain(client.name), client)
        self.sites = {}
        for site in Worksite.objects.order_by("-is_active", "pk"):
            self.sites.setdefault(site_key(site.client_id, site.name), site)
        for alias in PlanningAlias.objects.filter(
                company=company).select_related("client", "worksite"):
            if alias.kind == PlanningAlias.KIND_CLIENT and alias.client:
                self.clients[alias.key] = alias.client
            elif alias.worksite:
                self.sites[alias.key] = alias.worksite
        self.created_clients = 0
        self.created_sites = 0

    def client(self, text):
        key = plain(text)
        if not key:
            return None
        client = self.clients.get(key)
        if client is None:
            client = self.Client.objects.create(
                name=clean(text, 200),
                notes="Dado de alta al cargar el planning.")
            self.clients[key] = client
            self.created_clients += 1
        return client

    def site(self, client, text):
        if not plain(text):
            return None
        key = site_key(client.pk if client else None, text)
        site = self.sites.get(key)
        if site is None:
            site = self.Worksite.objects.create(
                name=clean(text, 200), address=clean(text, 300),
                client=client, client_name=client.name if client else "",
                notes="Dada de alta al cargar el planning.")
            site.code = "OBRA-%04d" % site.pk
            site.save(update_fields=["code"])
            self.sites[key] = site
            self.created_sites += 1
        return site


def site_key(client_id, place):
    """«12|nave antequera»: key of a worksite by client and place."""
    return "%s|%s" % (client_id or "", plain(place))


def merge_clients(company, target, others):
    """
    Move everything of `others` to `target`, remember their names, delete.
    ---
    Une clientes repetidos (erratas del planning) en `target`: sus obras,
    servicios del planning y albaranes pasan a él, sus nombres quedan
    como alias para las siguientes cargas, y se borran. Si al pasar una
    obra ya hay otra igual en `target`, se unen también.
    """
    from crane_albaranes.models import CraneAlbaran
    from worksites.models import Worksite

    moved = 0
    with transaction.atomic():
        for other in others:
            if other.pk == target.pk:
                continue
            PlanningAlias.objects.update_or_create(
                company=company, kind=PlanningAlias.KIND_CLIENT,
                key=plain(other.name), defaults={"client": target})
            PlanningAlias.objects.filter(client=other).update(client=target)
            PlanningService.objects.filter(client=other).update(
                client=target)
            CraneAlbaran.objects.filter(client=other).update(client=target)
            for site in Worksite.objects.filter(client=other):
                twin = Worksite.objects.filter(client=target).exclude(
                    pk=site.pk)
                twin = next((w for w in twin if plain(w.name) == plain(
                    site.name)), None)
                if twin is not None:
                    merge_worksites(company, twin, [site])
                else:
                    site.client = target
                    site.client_name = target.name
                    site.save(update_fields=["client", "client_name",
                                             "updated_at"])
            other.delete()
            moved += 1
    return moved


def merge_worksites(company, target, others):
    """
    Move everything of `others` to `target`, remember their keys, delete.
    ---
    Une obras repetidas en `target`: servicios del planning y albaranes
    pasan a ella, su lugar queda como alias y se borran (salvo las que
    tienen circulares, que se dejan finalizadas).
    """
    from crane_albaranes.models import CraneAlbaran

    moved = 0
    with transaction.atomic():
        for other in others:
            if other.pk == target.pk:
                continue
            PlanningAlias.objects.update_or_create(
                company=company, kind=PlanningAlias.KIND_WORKSITE,
                key=site_key(other.client_id, other.name),
                defaults={"worksite": target})
            PlanningAlias.objects.filter(worksite=other).update(
                worksite=target)
            PlanningService.objects.filter(worksite=other).update(
                worksite=target)
            CraneAlbaran.objects.filter(worksite=other).update(
                worksite=target)
            try:
                with transaction.atomic():
                    other.delete()
            except Exception:  # noqa: BLE001 -- protegida (circulares)
                other.is_active = False
                other.notes = ("%s\nUnida a %s." % (
                    other.notes, target.code or target.name)).strip()
                other.save(update_fields=["is_active", "notes",
                                          "updated_at"])
            moved += 1
    return moved


# ---------------------------------------------------------------------
# Cargar el planning
# ---------------------------------------------------------------------
def _is_service(item):
    """
    A row is a service if it has a client, a vehicle or a clear time.
    ---
    Una fila es un servicio si trae empresa, vehículo o una hora clara;
    si solo trae una nota (BAJA, «SOLIC VAC...»), es una anotación.
    """
    return bool(clean(item.get("client"), 200)
                or clean(item.get("vehicle"), 60)
                or parse_time(item.get("time")))


def _match_key(raw_person, raw_client, raw_place):
    return (plain(raw_person), plain(raw_client), plain(raw_place))


NOTICE_FIELDS = ("planned_time", "raw_time", "raw_place", "worksite_id",
                 "person_id")
COPY_FIELDS = ("position", "kind", "raw_person", "person_id",
               "raw_vehicle", "machine_id", "tonnage", "raw_client",
               "client_id", "raw_place", "worksite_id", "raw_time",
               "planned_time", "observations", "price", "contracted_by",
               "offer_ref", "contact")


def _service_values(item, people, machines, sites):
    """
    Field values of a PlanningService from one planning row.
    ---
    Los campos de un servicio a partir de su fila; devuelve también lo
    que no se ha podido reconocer.
    """
    raw_person = clean(item.get("person"), 120)
    kind = (PlanningService.KIND_SERVICE if _is_service(item)
            else PlanningService.KIND_NOTE)
    person, why = people.resolve(raw_person)
    raw_vehicle = clean(item.get("vehicle"), 60)
    machine = machines.resolve(raw_vehicle) if raw_vehicle else None
    raw_client = clean(item.get("client"), 200)
    raw_place = clean(item.get("place"), 300)
    client = site = None
    if kind == PlanningService.KIND_SERVICE:
        client = sites.client(raw_client)
        site = sites.site(client, raw_place)
    reasons = []
    if why and kind == PlanningService.KIND_SERVICE:
        reasons.append(why)
    if raw_vehicle and machine is None and _vehicle_key(raw_vehicle):
        reasons.append("vehículo «%s» no encontrado" % raw_vehicle)
    raw_time = clean(item.get("time"), 60)
    return {
        "position": item["row"], "kind": kind, "raw_person": raw_person,
        "person_id": person.pk if person else None,
        "raw_vehicle": raw_vehicle,
        "machine_id": machine.pk if machine else None,
        "tonnage": clean(item.get("tonnage"), 40),
        "raw_client": raw_client,
        "client_id": client.pk if client else None,
        "raw_place": raw_place,
        "worksite_id": site.pk if site else None,
        "raw_time": raw_time,
        "planned_time": parse_time(item.get("time")),
        "observations": " ".join(str(item.get("observations") or "")
                                 .split()),
        "price": clean(item.get("price"), 200),
        "contracted_by": clean(item.get("contracted_by"), 60),
        "offer_ref": clean(item.get("offer_ref"), 60),
        "contact": clean(item.get("contact"), 200),
    }, reasons


def _apply_day(company, planning, day, items, people, machines, sites,
               counters, problems):
    """
    Write one day: update matching services, create new, drop the rest.
    ---
    Escribe un día del planning: cada fila casa con el servicio que ya
    había del mismo trabajador, empresa y lugar (se actualiza); las
    nuevas se crean; los que ya no vienen se borran si no se avisaron
    y, si se avisaron, se quedan marcados «quitado del planning».
    """
    existing = list(PlanningService.objects.filter(
        company=company, day=day, removed_from_planning=False))
    pool = {}
    for service in existing:
        pool.setdefault(_match_key(service.raw_person, service.raw_client,
                                   service.raw_place), []).append(service)
    for item in items:
        values, reasons = _service_values(item, people, machines, sites)
        for reason in reasons:
            problems.append({"row": "%s fila %d" % (
                day.strftime("%d/%m/%Y"), item["row"]), "reasons": [reason]})
        counters["total"] += 1
        candidates = pool.get(_match_key(values["raw_person"],
                                         values["raw_client"],
                                         values["raw_place"]))
        if candidates:
            service = candidates.pop(0)
            changed = [f for f in COPY_FIELDS
                       if getattr(service, f) != values[f]]
            if not changed:
                continue
            if (service.notice_status != PlanningService.Notice.PENDING
                    and set(changed) & set(NOTICE_FIELDS)):
                service.changed_after_notice = True
            for field in changed:
                setattr(service, field, values[field])
            service.planning = planning
            service.save()
            counters["updated"] += 1
            continue
        PlanningService.objects.create(company=company, planning=planning,
                                       day=day, **values)
        counters["created"] += 1
    for leftovers in pool.values():
        for service in leftovers:
            counters["removed"] += 1
            if service.notice_status == PlanningService.Notice.PENDING \
                    and not service.notices.exists():
                service.delete()
            else:
                service.removed_from_planning = True
                service.save(update_fields=["removed_from_planning",
                                            "updated_at"])


def import_planning(company, uploaded, date_from=None, date_to=None,
                    created_by=None):
    """
    Load the real planning between two days; return the PlanningImport.

    ---

    Carga el planning real (el Excel tal cual, una hoja por día) entre
    `date_from` y `date_to`. Sin fechas, de hoy a DEFAULT_DAYS_AHEAD
    días. Devuelve la carga con sus contadores y los problemas (hojas
    sin cabecera o repetidas, nombres y vehículos sin reconocer).
    """
    today = timezone.localdate()
    date_from = date_from or today
    date_to = date_to or today + datetime.timedelta(DEFAULT_DAYS_AHEAD)
    if date_to < date_from:
        raise ValueError("La fecha «hasta» es anterior a «desde».")
    days, problems = read_planning(uploaded.read(), date_from, date_to)
    if not days:
        raise ValueError(
            "El Excel no trae ninguna hoja de día entre el %s y el %s." % (
                date_from.strftime("%d/%m/%Y"),
                date_to.strftime("%d/%m/%Y")))
    people = NameResolver(company)
    machines = MachineResolver(company)
    counters = {"total": 0, "created": 0, "updated": 0, "removed": 0}
    with transaction.atomic():
        sites = SiteResolver(company)
        planning = PlanningImport.objects.create(
            company=company, file_name=getattr(uploaded, "name", "")[:255],
            uploaded_by=created_by, date_from=date_from, date_to=date_to)
        for day in sorted(days):
            _apply_day(company, planning, day, days[day], people, machines,
                       sites, counters, problems)
        planning.rows_total = counters["total"]
        planning.rows_created = counters["created"]
        planning.rows_updated = counters["updated"]
        planning.rows_removed = counters["removed"]
        planning.days_loaded = len(days)
        planning.problems = _group_problems(problems)
        planning.save()
        remember_unknown(company, [
            s.raw_person for s in PlanningService.objects.filter(
                company=company, day__gte=date_from, day__lte=date_to,
                person__isnull=True,
                kind=PlanningService.KIND_SERVICE).exclude(raw_person="")],
            people)
    logger.info(
        "# [TRÁFICO] Planning %s: %d días, %d filas (%d nuevas, %d "
        "cambiadas, %d quitadas), %d clientes y %d obras nuevos.",
        planning.file_name, len(days), counters["total"],
        counters["created"], counters["updated"], counters["removed"],
        sites.created_clients, sites.created_sites)
    planning.created_clients = sites.created_clients
    planning.created_sites = sites.created_sites
    return planning


def _group_problems(problems):
    """
    Same reason on many rows -> one line with the count.
    ---
    Junta los problemas repetidos («PETRUS» sin reconocer en 40 filas)
    en una línea con cuántas veces y la primera fila.
    """
    grouped = {}
    order = []
    for problem in problems:
        for reason in problem["reasons"]:
            if reason not in grouped:
                grouped[reason] = [problem["row"], 0]
                order.append(reason)
            grouped[reason][1] += 1
    return [{"row": grouped[r][0], "reasons": [
        r if grouped[r][1] == 1 else "%s (%d filas)" % (r, grouped[r][1])]}
        for r in order]


def remember_unknown(company, texts, people=None):
    """
    Add the names not recognised to the names table, «Sin asignar».
    ---
    Apunta en Tráfico › Nombres los textos que no se han reconocido (y
    que no estaban ya), para asignarlos una vez. Devuelve cuántos.
    """
    people = people or NameResolver(company)
    known = set(PlanningName.objects.filter(company=company).values_list(
        "key", flat=True))
    new = {}
    for text in texts:
        key = plain(text)
        if key and key not in known and key not in new:
            person, _why = people.resolve(text)
            if person is None:
                new[key] = PlanningName(company=company, key=key[:120],
                                        text=clean(text, 120))
    PlanningName.objects.bulk_create(new.values(), ignore_conflicts=True)
    return len(new)


def relink_names(company, keys=None):
    """
    Apply the names table to the services already loaded.
    ---
    Tras asignar nombres en Tráfico › Nombres, pone el trabajador en los
    servicios ya cargados con ese texto (o lo quita si se marcó «no es
    un trabajador»). Devuelve cuántos servicios han cambiado.
    """
    people = NameResolver(company)
    services = PlanningService.objects.filter(company=company).exclude(
        raw_person="")
    changed = 0
    for service in services.only("pk", "raw_person", "person_id"):
        key = plain(service.raw_person)
        if keys is not None and key not in keys:
            continue
        person, _why = people.resolve(service.raw_person)
        person_id = person.pk if person else None
        if person_id != service.person_id:
            PlanningService.objects.filter(pk=service.pk).update(
                person_id=person_id)
            changed += 1
    return changed


def unknown_names(company):
    """
    [(text, rows, first day)] of planning names not recognised.
    ---
    Los textos de PERSONAL de servicios sin trabajador y que no están
    marcados «no es un trabajador», con cuántas filas y desde cuándo.
    """
    from django.db.models import Count, Min

    people = NameResolver(company)
    out = []
    rows = PlanningService.objects.filter(
        company=company, person__isnull=True,
        kind=PlanningService.KIND_SERVICE).exclude(raw_person="").values(
        "raw_person").annotate(n=Count("pk"), first=Min("day"))
    seen = set()
    for row in rows:
        key = plain(row["raw_person"])
        if key in seen or people.is_ignored(row["raw_person"]):
            continue
        seen.add(key)
        out.append((row["raw_person"], row["n"], row["first"]))
    return sorted(out, key=lambda r: -r[1])


def assign_name(company, text, person=None, not_a_worker=False,
                updated_by=None):
    """
    Remember who a planning text is (or that it is not a worker).
    ---
    Guarda en la tabla de nombres quién es un texto del planning (o que
    no es un trabajador) y lo aplica a los servicios ya cargados.
    """
    key = plain(text)
    if not key:
        raise ValueError("Falta el texto del planning.")
    name, _created = PlanningName.objects.update_or_create(
        company=company, key=key, defaults={
            "text": clean(text, 120), "person": person,
            "not_a_worker": bool(not_a_worker and person is None),
            "updated_by": updated_by})
    relink_names(company, {key})
    return name


# ---------------------------------------------------------------------
# Aviso al gruista: solo la ubicación de la obra y la hora
# ---------------------------------------------------------------------
def map_url(service):
    """
    Google Maps link of the worksite, if it has coordinates.
    ---
    Enlace de Google Maps de la obra, solo si tiene coordenadas.
    """
    site = service.worksite
    if site is None or site.latitude is None or site.longitude is None:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=%s,%s" % (
        site.latitude, site.longitude)


def notice_parts(service):
    """
    (when, worksite, location) of the location-only notice.
    ---
    Cuándo («25/11/2026 a las 08:00»), la obra («NAVE ANTEQUERA
    (ARTEPREF)») y la ubicación (la de la obra si la tiene, si no el
    lugar del planning).
    """
    when = service.day.strftime("%d/%m/%Y")
    if service.planned_time:
        when += " a las %s" % service.planned_time.strftime("%H:%M")
    elif service.raw_time:
        when += " (%s)" % service.raw_time
    site = service.worksite
    name = site.name if site else (service.raw_place or "sin indicar")
    client = service.client.name if service.client_id else (
        service.raw_client)
    if client:
        name = "%s (%s)" % (name, client)
    location = ""
    if site is not None:
        location = ", ".join(p for p in (site.address, site.locality,
                                         site.province) if p)
    return when, name, location or service.raw_place or "sin indicar"


def notice_text(service):
    """
    Free WhatsApp text of the location-only notice.
    ---
    Texto del aviso de solo ubicación y hora (dentro de la ventana de
    24 h sale así; fuera, la plantilla crane_location_notice con lo
    mismo).
    """
    when, name, location = notice_parts(service)
    lines = ["\U0001f4cd Servicio el %s" % when, "Obra: %s" % name,
             "Ubicación: %s" % location]
    url = map_url(service)
    if url:
        lines.append("Mapa: %s" % url)
    return "\n".join(lines)


def notice_variables(service):
    """
    Variables of crane_location_notice: {{1}} name ... {{5}} map.
    ---
    Variables de la plantilla crane_location_notice: {{1}} gruista,
    {{2}} fecha y hora, {{3}} obra, {{4}} ubicación, {{5}} mapa o «-».
    """
    when, name, location = notice_parts(service)
    return {"1": service.person.given_name if service.person_id else "-",
            "2": when, "3": name, "4": location,
            "5": map_url(service) or "-"}


def status_url(notice):
    """
    Twilio status callback URL of a notice (signed pk).
    ---
    URL a la que Twilio manda el estado de entrega del envío; lleva el
    envío firmado para que nadie pueda marcar otro.
    """
    token = signing.dumps(notice.pk, salt=STATUS_SALT)
    return settings.PLATFORM_BASE_URL + reverse(
        "crane_albaranes:planning_notice_status", kwargs={"token": token})


def notice_pk_from_token(token):
    """The PlanningNotice pk signed in the URL, or None."""
    try:
        return signing.loads(token, salt=STATUS_SALT)
    except signing.BadSignature:
        return None


STATUS_ORDER = {
    "accepted": 0, "queued": 1, "sending": 2, "sent": 3,
    "delivered": 4, "read": 5, "undelivered": 6, "failed": 6,
}


def set_notice_status(notice_pk, status):
    """
    Store a newer Twilio status on a notice; True if stored.
    ---
    Guarda el estado de Twilio si avanza (sent -> delivered -> read); un
    fallo (failed, undelivered) queda siempre.
    """
    status = (status or "").lower()
    notice = PlanningNotice.objects.filter(pk=notice_pk).first()
    if notice is None or status not in STATUS_ORDER:
        return False
    if STATUS_ORDER.get(notice.whatsapp_status, -1) >= STATUS_ORDER[
            status] and status not in ("failed", "undelivered"):
        return False
    notice.whatsapp_status = status
    notice.whatsapp_status_at = timezone.now()
    notice.save(update_fields=["whatsapp_status", "whatsapp_status_at"])
    if status in ("failed", "undelivered") and notice.service_id:
        PlanningService.objects.filter(pk=notice.service_id).update(
            notice_status=PlanningService.Notice.FAILED,
            notice_error="WhatsApp no entregado (%s)." % status)
    return True


def why_not_sendable(service):
    """
    Reason a service cannot be notified, or "".
    ---
    Por qué no se puede avisar de un servicio («» si se puede).
    """
    from crane_albaranes.services import worker_phone

    if service.kind != PlanningService.KIND_SERVICE:
        return "es una anotación, no un servicio"
    if service.removed_from_planning:
        return "ya no está en el planning"
    if service.person_id is None:
        return "sin gruista reconocido"
    if not worker_phone(service.person):
        return "el gruista no tiene móvil en su ficha"
    return ""


def send_notice(service, sent_by=None, client=None, template=None):
    """
    Send the location-only notice of a service; return the notice.

    ---

    Envía al gruista la ubicación de la obra y la hora del servicio: la
    plantilla crane_location_notice si está aprobada o, dentro de la
    ventana de 24 h, el mismo texto libre. Siempre solo ubicación y
    hora (services.LOCATION_ONLY_NOTICE): el albarán no se envía hasta
    que la dirección lo ordene. Deja el envío en PlanningNotice y el
    servicio en «Enviado» o «Envío fallido» con el motivo.
    """
    from crane_albaranes.services import (
        LOCATION_ONLY_NOTICE, LOCATION_TEMPLATE_NAME, worker_phone,
    )
    from fleet.refuel_questions import template_approved
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.window_service import (
        send_notification, to_e164, window_open,
    )

    assert LOCATION_ONLY_NOTICE, "Solo ubicación y hora (S162/S165)."
    error = why_not_sendable(service)
    if error:
        # Sin gruista, sin móvil, anotación o quitado: no se intenta y
        # no se apunta como envío (solo en el servicio, con el motivo).
        if service.kind == PlanningService.KIND_SERVICE and \
                not service.removed_from_planning:
            service.notice_status = PlanningService.Notice.FAILED
            service.notice_error = error[:255]
            service.save(update_fields=["notice_status", "notice_error",
                                        "updated_at"])
        return PlanningNotice(service=service, ok=False, error=error)
    phone = worker_phone(service.person)
    text = notice_text(service)
    notice = PlanningNotice.objects.create(
        company=service.company, service=service,
        person=service.person, day=service.day, phone=phone, text=text,
        sent_by=sent_by)
    sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
    if not error and not sender:
        error = "falta TWILIO_WHATSAPP_SENDER en el servidor"
    sid = ""
    approved = False
    if not error:
        if template is None:
            template = WhatsAppTemplate.objects.filter(
                company=service.company, name=LOCATION_TEMPLATE_NAME,
                is_active=True).first()
        sid = template.content_sid if template else ""
        approved = bool(sid) and template_approved(sid)
        if not approved and not window_open(service.company,
                                            to_e164(phone)):
            error = ("la plantilla de WhatsApp del aviso está pendiente "
                     "de aprobación y el gruista no ha escrito al bot en "
                     "las últimas 24 h")
    if not error:
        try:
            if client is None:
                from whatsapp.services import _build_twilio_client

                client = _build_twilio_client()
            message = send_notification(
                client, sender, service.company, phone,
                sid if approved else None,
                variables=notice_variables(service) if approved else None,
                text=text, status_callback=status_url(notice))
            notice.message_sid = getattr(message, "sid", "") or ""
            notice.sent_as_text = bool(getattr(message, "sent_as_text",
                                               False))
        except Exception as exc:  # noqa: BLE001 -- se informa al usuario
            logger.exception("# [TRÁFICO] Aviso del servicio %s no enviado",
                             service.pk)
            error = "Twilio no aceptó el envío: %s" % exc
    notice.ok = not error
    notice.error = error[:255]
    notice.save(update_fields=["ok", "error", "message_sid",
                               "sent_as_text"])
    service.notice_error = error[:255]
    if error:
        service.notice_status = PlanningService.Notice.FAILED
    else:
        service.notice_status = PlanningService.Notice.SENT
        service.notified_at = timezone.now()
        service.changed_after_notice = False
    service.save(update_fields=["notice_error", "notice_status",
                                "notified_at", "changed_after_notice",
                                "updated_at"])
    logger.info("# [TRÁFICO] Servicio %s (%s) aviso a %s: %s", service.pk,
                service.day, phone, error or "enviado")
    return notice


def send_notices(services, sent_by=None):
    """
    Send the notices of several services; return (sent, [failures]).
    ---
    Envía los avisos de varios servicios con un solo cliente de Twilio.
    Devuelve cuántos se han enviado y la lista de los que no, con su
    motivo.
    """
    sent, failures, client = 0, [], None
    for service in services:
        if why_not_sendable(service) == "" and client is None:
            try:
                from whatsapp.services import _build_twilio_client

                client = _build_twilio_client()
            except Exception as exc:  # noqa: BLE001
                logger.exception("# [TRÁFICO] Sin cliente de Twilio")
                failures.append(("Twilio", str(exc)))
                break
        notice = send_notice(service, sent_by, client=client)
        if notice.ok:
            sent += 1
        else:
            failures.append((service_label(service), notice.error))
    return sent, failures


def service_label(service):
    """
    «25/11 PETRUS — CHURRIANA» for messages.
    ---
    Rótulo corto de un servicio para los mensajes del panel.
    """
    return "%s %s — %s" % (service.day.strftime("%d/%m"),
                           service.raw_person or "sin gruista",
                           service.raw_place or service.raw_client or "")
