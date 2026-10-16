# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/balance_import.py
"""
Starting vacation balance from Carolina's spreadsheet (H24, S129).

The template lists the active workers by ID number with two columns to
fill in: days already taken in the year and days left over from the
previous year. The year travels in the column headers ("Disfrutados
2026", "Sobrantes 2025"), so a template filled in for one year can
never be loaded as another. Importing writes one OPENING_TAKEN and one
OPENING_CARRYOVER row per worker and year (a new import overwrites
them); an empty cell leaves that value as it was. Rows that cannot be
matched are reported, never guessed.

---

Saldo de partida de vacaciones desde la hoja de cálculo de Carolina
(H24, S129).

La plantilla lista a los trabajadores activos por DNI con dos columnas
para rellenar: días ya disfrutados en el año y días que sobraron del
año anterior. El año va en las cabeceras ("Disfrutados 2026",
"Sobrantes 2025"), así que una plantilla rellenada para un año nunca se
puede cargar como otro. La importación escribe una fila OPENING_TAKEN y
otra OPENING_CARRYOVER por trabajador y año (una importación posterior
las sobrescribe); una celda vacía deja ese dato como estaba. Las filas
que no casan se informan, nunca se adivinan.
"""
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from document_explorer.models import PersonIdentity
from document_ingestion.entity_matching_service import normalize_dni
from hr_calendar.balance import set_opening_balance
from hr_calendar.models import (
    PersonSectionAssignment,
    VacationBalanceAdjustment,
)

TAKEN_HEADER = "Disfrutados"
CARRYOVER_HEADER = "Sobrantes"
IMPORT_REASON = "Importado de la hoja de cálculo de saldos (plantilla)."


def _clean_dni(value):
    """
    Uppercase, without spaces, dots or hyphens.
    ---
    En mayúsculas, sin espacios, puntos ni guiones (mismo formato que
    PersonIdentity.dni).
    """
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper())


def build_template(company, year, as_of):
    """
    Return the .xlsx template (bytes) for `year`.
    ---
    Devuelve la plantilla .xlsx (bytes) para `year`: trabajadores
    activos ordenados por apellidos, con su sección a fecha `as_of` y
    lo ya cargado de ese año, para que Carolina corrija en vez de
    teclear de nuevo.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    people = list(PersonIdentity.objects.filter(
        is_active_employee=True,
    ).order_by("first_surname", "second_surname", "given_name"))
    ids = [p.pk for p in people]
    sections = {}
    for row in PersonSectionAssignment.objects.filter(
        person_id__in=ids, valid_from__lte=as_of,
    ).select_related("section").order_by("valid_from"):
        sections[row.person_id] = row.section.name
    loaded = {}
    for row in VacationBalanceAdjustment.objects.filter(
        person_id__in=ids, company=company, year=year,
        kind__in=[
            VacationBalanceAdjustment.Kind.OPENING_TAKEN,
            VacationBalanceAdjustment.Kind.OPENING_CARRYOVER,
        ],
    ):
        loaded[(row.person_id, row.kind)] = row.days

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"Saldos {year}"
    headers = [
        "DNI", "Apellidos y nombre", "Sección",
        f"{TAKEN_HEADER} {year}", f"{CARRYOVER_HEADER} {year - 1}",
    ]
    sheet.append(headers)
    fill = PatternFill("solid", fgColor="FFF2CC")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for person in people:
        name = " ".join(
            p for p in (person.first_surname, person.second_surname) if p
        ) + ", " + person.given_name
        taken = loaded.get(
            (person.pk, VacationBalanceAdjustment.Kind.OPENING_TAKEN),
        )
        carry = loaded.get(
            (person.pk, VacationBalanceAdjustment.Kind.OPENING_CARRYOVER),
        )
        sheet.append([
            person.dni, name, sections.get(person.pk, ""),
            float(taken) if taken is not None else None,
            float(carry) if carry is not None else None,
        ])
    last_row = sheet.max_row
    validation = DataValidation(
        type="decimal", operator="between", formula1="-366",
        formula2="366", allow_blank=True,
        error="Escribe un número de días (admite medios días, p. ej. 3,5).",
    )
    sheet.add_data_validation(validation)
    if last_row >= 2:
        validation.add(f"D2:E{last_row}")
        for row in sheet.iter_rows(min_row=2, min_col=4, max_col=5):
            for cell in row:
                cell.fill = fill
    for column, width in zip("ABCDE", (14, 40, 26, 18, 18)):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@dataclass
class ImportReport:
    """
    Outcome of an import, row by row.
    ---
    Resultado de una importación: año leído de la cabecera, filas
    cargadas, filas sin cambios (celdas vacías) y filas no casadas con
    su motivo (número de fila tal cual lo ve Carolina en Excel).
    """
    year: int = None
    loaded: int = 0
    created_rows: int = 0
    updated_rows: int = 0
    unchanged: int = 0
    unmatched: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _parse_days(value):
    """
    Cell value -> Decimal days, None for an empty cell.
    ---
    Valor de celda -> días (Decimal), None si está vacía. Acepta coma
    decimal. Lanza ValueError si no es un número o no es múltiplo de
    medio día.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        days = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("no es un número") from exc
    if (days * 2) != (days * 2).to_integral_value():
        raise ValueError("solo admite días enteros o medios días")
    return days.quantize(Decimal("0.1"))


def import_template(uploaded_file, company, created_by):
    """
    Load a filled template; return an ImportReport.
    ---
    Carga una plantilla rellenada y devuelve un ImportReport. Nada se
    escribe si la cabecera no es la de la plantilla.
    """
    from openpyxl import load_workbook

    report = ImportReport()
    try:
        workbook = load_workbook(uploaded_file, data_only=True,
                                 read_only=True)
    except Exception:
        report.errors.append(
            "El archivo no se puede leer como hoja de Excel (.xlsx)."
        )
        return report
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None) or ()
    header = [str(h or "").strip() for h in header]
    col_dni = col_taken = col_carry = None
    taken_year = carry_year = None
    for idx, title in enumerate(header):
        if title.upper() == "DNI":
            col_dni = idx
        match = re.match(rf"^{TAKEN_HEADER}\s+(\d{{4}})$", title, re.I)
        if match:
            col_taken, taken_year = idx, int(match.group(1))
        match = re.match(rf"^{CARRYOVER_HEADER}\s+(\d{{4}})$", title, re.I)
        if match:
            col_carry, carry_year = idx, int(match.group(1))
    if col_dni is None or col_taken is None or col_carry is None:
        report.errors.append(
            "La primera fila no es la de la plantilla: faltan las "
            "columnas DNI, «Disfrutados AAAA» y «Sobrantes AAAA». "
            "Descarga la plantilla y rellénala sin cambiar la cabecera."
        )
        return report
    if carry_year != taken_year - 1:
        report.errors.append(
            f"Las cabeceras no cuadran: «{TAKEN_HEADER} {taken_year}» "
            f"debe ir con «{CARRYOVER_HEADER} {taken_year - 1}»."
        )
        return report
    report.year = taken_year

    people = {}
    for person in PersonIdentity.objects.all().only("pk", "dni"):
        people[_clean_dni(person.dni)] = person
    for excel_row, values in enumerate(rows, start=2):
        values = list(values) + [None] * len(header)
        raw_dni = values[col_dni]
        raw_taken, raw_carry = values[col_taken], values[col_carry]
        if raw_dni in (None, "") and raw_taken in (None, "") \
                and raw_carry in (None, ""):
            continue
        dni = _clean_dni(raw_dni)
        if not dni:
            report.unmatched.append((excel_row, "", "Fila sin DNI."))
            continue
        person = people.get(dni) or people.get(normalize_dni(dni))
        if person is None:
            report.unmatched.append(
                (excel_row, dni, "No hay ningún trabajador con ese DNI."),
            )
            continue
        try:
            taken = _parse_days(raw_taken)
            carry = _parse_days(raw_carry)
        except ValueError as exc:
            report.unmatched.append(
                (excel_row, dni, f"Valor de días no válido: {exc}."),
            )
            continue
        if taken is None and carry is None:
            report.unchanged += 1
            continue
        for kind, days in (
            (VacationBalanceAdjustment.Kind.OPENING_TAKEN, taken),
            (VacationBalanceAdjustment.Kind.OPENING_CARRYOVER, carry),
        ):
            if days is None:
                continue
            created = set_opening_balance(
                person, company, report.year, kind, days, created_by,
                IMPORT_REASON,
            )
            if created:
                report.created_rows += 1
            else:
                report.updated_rows += 1
        report.loaded += 1
    return report
