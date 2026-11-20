# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/planning.py
"""
Planning Excel of the cranes: one row, one prepared albarán (H11, S162).

---

Planning de las grúas en Excel (H11, S162). Miguel Ángel: "Carlos Núñez
cargaría el planning con un Excel de dónde va a trabajar cada gruista,
en qué obras va a trabajar". Cada fila es un servicio: fecha, gruista,
obra, máquina y, si se quiere, hora, trabajo a realizar, nº de pedido,
toneladas, ayudantes y observaciones. Las cabeceras se reconocen sin
mayúsculas ni tildes y en cualquier orden; la plantilla se descarga
desde la pestaña Albaranes.
"""
import datetime
import io
import re
import unicodedata

from django.db.models import Q

from crane_albaranes.models import CraneAlbaran, PlanningImport
from crane_albaranes.services import create_albaran

HEADERS = (
    ("day", "Fecha", ("fecha", "dia")),
    ("time", "Hora", ("hora", "hora inicio", "hora prevista")),
    ("person", "Gruista", ("gruista", "operario", "trabajador",
                           "conductor", "nombre", "dni")),
    ("worksite", "Obra", ("obra", "codigo obra", "cod obra")),
    ("machine", "Máquina", ("maquina", "grua", "centro de gasto",
                            "vehiculo")),
    ("task", "Trabajo a realizar", ("trabajo a realizar", "trabajo",
                                    "tarea", "servicio")),
    ("order_number", "Nº de pedido", ("n de pedido", "no de pedido",
                                      "pedido", "n pedido")),
    ("tonnage", "Toneladas", ("toneladas", "tonelaje", "tn")),
    ("helpers", "Ayudantes", ("ayudantes", "ayudante")),
    ("observations", "Observaciones", ("observaciones", "notas")),
)


def _plain(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode(
        "ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def template_workbook():
    """
    Empty planning template with one example row.
    ---
    Plantilla del planning con sus cabeceras y una fila de ejemplo.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PLANNING"
    sheet.append([label for _key, label, _aliases in HEADERS])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0D6EFD")
    sheet.append([datetime.date.today(), "07:30", "Nombre Apellido",
                  "OBRA-0001", "A-65", "Montaje de torre", "", "80", "",
                  ""])
    for column, width in zip("ABCDEFGHIJ",
                             (12, 8, 28, 14, 10, 36, 14, 10, 18, 30)):
        sheet.column_dimensions[column].width = width
    return workbook


def _match_column(header):
    plain = _plain(header)
    for key, _label, aliases in HEADERS:
        if plain in aliases:
            return key
    return None


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    match = re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})",
                     str(value or ""))
    if match:
        day, month, year = (int(g) for g in match.groups())
        year = year + 2000 if year < 100 else year
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    try:
        return datetime.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _as_time(value):
    if isinstance(value, datetime.datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, datetime.time):
        return value.replace(second=0, microsecond=0)
    match = re.match(r"^\s*(\d{1,2})\s*[:.h]\s*(\d{2})", str(value or ""))
    if match and int(match.group(1)) < 24 and int(match.group(2)) < 60:
        return datetime.time(int(match.group(1)), int(match.group(2)))
    return None


def find_person(company, text):
    """
    Active worker by DNI, nickname or name words.
    ---
    Trabajador activo por DNI, por su mote o porque todas las palabras
    escritas están en su nombre y apellidos. Devuelve (persona, motivo);
    sin coincidencia única, persona None y el motivo.
    """
    from document_explorer.models import PersonIdentity

    raw = str(text or "").strip()
    if not raw:
        return None, "sin gruista"
    people = PersonIdentity.objects.filter(company=company,
                                           is_active_employee=True)
    dni = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
    if re.match(r"^[0-9XYZ]\d{6,7}[A-Z]$", dni):
        found = list(people.filter(dni__iexact=dni)[:2])
        if len(found) == 1:
            return found[0], ""
    found = list(people.filter(nickname__iexact=raw)[:2])
    if len(found) == 1:
        return found[0], ""
    words = _plain(raw).split()
    matches = []
    for person in people.only("pk", "given_name", "first_surname",
                              "second_surname", "nickname"):
        full = _plain(" ".join((person.given_name, person.first_surname,
                                person.second_surname or "",
                                person.nickname or ""))).split()
        if words and all(w in full for w in words):
            matches.append(person)
    if len(matches) == 1:
        return matches[0], ""
    if not matches:
        return None, "gruista «%s» no encontrado" % raw
    return None, "«%s» coincide con varios trabajadores" % raw


def find_worksite(text):
    """
    Site by code (OBRA-0001), project number or name.
    ---
    Obra por su código, su nº de proyecto o su nombre exacto.
    """
    from worksites.models import Worksite

    raw = str(text or "").strip()
    if not raw:
        return None
    return (Worksite.objects.filter(
        Q(code__iexact=raw) | Q(project_number__iexact=raw)
        | Q(name__iexact=raw)).order_by("-is_active", "pk").first())


def find_machine(company, text):
    """
    Active machine by code (A-65 or A65) or plate.
    ---
    Máquina activa por su código (con o sin guion) o su matrícula.
    """
    from fleet.models import MachineAsset

    raw = str(text or "").strip().upper()
    if not raw:
        return None
    machines = MachineAsset.objects.filter(company=company,
                                           is_active=True)
    found = machines.filter(Q(code__iexact=raw) | Q(plate__iexact=raw))
    if found.exists():
        return found.first()
    compact = raw.replace("-", "").replace(" ", "")
    for machine in machines.only("pk", "code"):
        if machine.code.replace("-", "").upper() == compact:
            return machine
    return None


def import_planning(company, uploaded, created_by=None):
    """
    Read the planning and create one prepared albarán per good row.
    ---
    Lee el planning y crea un albarán preparado por cada fila completa
    (fecha, gruista y obra son obligatorios; la máquina, si viene, tiene
    que existir). Una fila repetida (mismo día, gruista, obra y máquina
    ya preparada) no se duplica. Devuelve el PlanningImport con las
    filas que no se han podido cargar y el motivo.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(uploaded.read()), data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("El Excel está vacío.")
    columns = {}
    for index, header in enumerate(rows[0]):
        key = _match_column(header)
        if key and key not in columns:
            columns[key] = index
    missing = [label for key, label, _a in HEADERS
               if key in ("day", "person", "worksite")
               and key not in columns]
    if missing:
        raise ValueError("Faltan las columnas: %s." % ", ".join(missing))
    planning = PlanningImport.objects.create(
        company=company, file_name=getattr(uploaded, "name", "")[:255],
        uploaded_by=created_by)
    problems, created = [], 0
    for number, row in enumerate(rows[1:], start=2):
        def cell(key):
            index = columns.get(key)
            return row[index] if index is not None and index < len(
                row) else None
        if not any(v not in (None, "") for v in row):
            continue
        planning.rows_total += 1
        day = _as_date(cell("day"))
        person, why = find_person(company, cell("person"))
        worksite = find_worksite(cell("worksite"))
        machine = find_machine(company, cell("machine"))
        reasons = []
        if day is None:
            reasons.append("fecha no válida")
        if person is None:
            reasons.append(why)
        if worksite is None:
            reasons.append("obra «%s» no dada de alta" % (
                cell("worksite") or ""))
        if cell("machine") and machine is None:
            reasons.append("máquina «%s» no encontrada" % cell("machine"))
        if reasons:
            problems.append({"row": number, "reasons": reasons})
            continue
        duplicate = CraneAlbaran.objects.filter(
            company=company, day=day, person=person, worksite=worksite,
            machine=machine).exclude(
            status=CraneAlbaran.Status.CANCELLED).exists()
        if duplicate:
            problems.append({"row": number, "reasons": [
                "ya hay un albarán de ese gruista en esa obra ese día"]})
            continue
        create_albaran(
            company, day=day, worksite=worksite, machine=machine,
            person=person, origin=CraneAlbaran.ORIGIN_PLANNING,
            created_by=created_by, planning=planning,
            planned_time=_as_time(cell("time")),
            task=str(cell("task") or "").strip(),
            order_number=str(cell("order_number") or "").strip()[:60],
            tonnage=str(cell("tonnage") or "").strip()[:20],
            helpers=str(cell("helpers") or "").strip()[:200],
            observations=str(cell("observations") or "").strip(),
        )
        created += 1
    planning.rows_created = created
    planning.problems = problems
    planning.save(update_fields=["rows_total", "rows_created",
                                 "problems"])
    return planning
