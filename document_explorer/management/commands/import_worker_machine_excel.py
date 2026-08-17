# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/import_worker_machine_excel.py
"""
H30 (S54). Importa el Excel real de administración de trabajadores y
maquinaria (document_explorer/data_imports/EXCEL_TRABAJADORES.xlsx,
subido por Miguel Angel) hacia PersonIdentity y fleet.MachineAsset.

Cierra el pendiente abierto desde S043: aquella sesion cruzo el Excel
contra la base de datos de forma puntual (confirmo "70/70 personas y
37/37 maquinas ya cubiertas") pero nunca persistio el resultado -- ni
un campo is_active, ni las fechas reales de cumplimiento. Esta vez se
persiste de verdad, y el comando queda para volver a ejecutarse cada
vez que Miguel Angel suba una version nueva del Excel.

Validado en S54 contra el Excel real antes de escribir este comando
(nunca a ciegas): 70 DNIs distintos sin duplicados entre las 5 hojas
de trabajadores (coincide exacto con el "70/70" de S043), 37 codigos
de maquina en la hoja MAQUINARIA (coincide exacto con "37/37").

Diseno defensivo, dado el estado real del archivo:
- Las "Tablas" de Excel definidas en el libro estan rotas/desactualizadas
  (columnas genericas "ColumnaN", rangos que no cuadran con los datos
  reales) -- NUNCA se usan. La fila de cabecera real se detecta por
  contenido (busca "DNI"/"NOMBRE" o "CODIGO"/"MATRICULA" en las primeras
  filas de cada hoja).
- Las columnas varian ligeramente de nombre entre hojas (p.ej.
  "TARJ.CUALIFI.CONDUC." vs "TARJ.CUAL.CONDUCT.") -- se resuelven por
  alias, nunca por posicion fija de columna.
- Fechas mal escritas en el propio Excel (visto un caso real,
  '21/03/230', año con un digito de menos) se registran como error y
  se saltan, nunca se guardan como si fueran validas ni hacen fallar
  el resto de la fila.
- is_active_employee SOLO se pone a True cuando el DNI aparece en el
  Excel. Nunca se pone a False por ausencia -- el Excel puede estar
  incompleto, y "no aparece" no es lo mismo que "de baja" (directriz
  de Miguel Angel, S54: nunca adivinar, comparar siempre contra una
  fuente real).

Por defecto es un dry-run (--apply para escribir de verdad), mismo
patron que el resto de comandos de auditoria/reparacion del proyecto.
"""
import datetime
import os
import re

import openpyxl
from django.core.management.base import BaseCommand

from document_explorer.models import PersonIdentity
from fleet.models import MachineAsset

EXCEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data_imports",
    "EXCEL_TRABAJADORES.xlsx",
)

WORKER_SHEETS = [
    "TRABAJADORES GRUAS ALVAREZ MALA",
    "TRABAJADORES TRANSGRUAL",
    "ADMINISTRACION",
    "TRABAJADORES TALLER GRUAS ",
    "TRABAJADORES ASIST.Y GRUAS GRAN",
]
MACHINE_SHEET = "MAQUINARIA"

DNI_RE = re.compile(r"^[XYZ]?\d{7,8}[A-Z]$")

# Alias reales de cabecera vistos en las distintas hojas -> nombre de
# columna logico usado por este comando. Todo en mayusculas para
# comparar sin sensibilidad a caja.
WORKER_HEADER_ALIASES = {
    "NOMBRE TRABAJADOR": "nombre",
    "DNI": "dni",
    "RM": "rm",
    "FECHA CAD.DNI": "dni_expiry",
    "FECHA CAD.CARNET COND.": "driving_license_expiry",
    "CAD.CARNET GRUISTA": "crane_card_expiry",
    "TARJ.CUALIFI.CONDUC.": "driver_qualification_card_expiry",
    "TARJ.CUAL.CONDUCT.": "driver_qualification_card_expiry",
    "TARJCOND.(TACOGR.)": "tachograph_card_expiry",
    "TARJ.COND.": "tachograph_card_expiry",
    "NUMERO AFILIACION SS": "ss_affiliation_number",
    "EMPRESA": "empresa",
    "TELEFONO": "telefono",
    "CORREO ELECTRONICO": "email",
    "CORREO ELECT.": "email",
    "CORREO ELECTRON.": "email",
}

MACHINE_HEADER_ALIASES = {
    "CODIGO": "codigo",
    "MATRICULA": "matricula",
    "ITV": "itv",
    "CITA ITV": "cita_itv",
    "SEGURO": "seguro",
    "OCA": "oca",
}

# Correcciones puntuales de erratas reales del propio Excel,
# confirmadas explicitamente por Miguel Angel una a una -- NUNCA una
# regla generica de "año de 3 cifras => insertar un 0", que podria
# adivinar mal en un caso futuro distinto a este. Clave: el texto
# exacto tal cual aparece en la celda: valor corregido real.
# ---
# Confirmado por Miguel Angel (S54): '21/03/230' en el carnet de
# conducir de ALVAREZ GEA (DNI 44599171D) es '21/03/2030' -- un cero
# perdido al escribir el año.
KNOWN_TYPO_CORRECTIONS = {
    "21/03/230": datetime.date(2030, 3, 21),
}

# Correcciones puntuales por persona cuando el propio Excel no trae
# nada aprovechable en la celda (texto ajeno, vacio) y Miguel Angel
# confirma el dato real a partir del documento fisico. Clave: DNI
# normalizado. Nunca una inferencia -- solo lo que Miguel Angel ha
# confirmado explicitamente viendo el documento real.
# ---
# S54: GUTIERREZ MATEO, ALEJANDRO JOSE (DNI 25723198K) -- la columna
# de caducidad de carnet de conducir traia 'PARASCHI' (texto ajeno,
# sin fecha real). Confirmado con foto real del permiso de conducir:
# casilla 4b, caducidad 27-04-2032.
MANUAL_FIELD_OVERRIDES = {
    "25723198K": {
        "driving_license_expiry_date": datetime.date(2032, 4, 27),
    },
}


def _norm_dni(value):
    if not value:
        return None
    text = str(value).strip().upper().replace(" ", "").replace("-", "")
    return text if DNI_RE.match(text) else None


def _norm_code(value):
    if not value:
        return None
    return str(value).strip().upper().replace(" ", "").replace("-", "")


def _parse_date(value, context_label, errors):
    """Best-effort date parsing. Never raises -- logs to `errors` and
    returns None for anything it cannot parse with confidence.
    ---
    Parseo de fecha de mejor esfuerzo. Nunca lanza excepcion -- registra
    en `errors` y devuelve None para cualquier cosa que no pueda
    interpretar con confianza.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if text in KNOWN_TYPO_CORRECTIONS:
        return KNOWN_TYPO_CORRECTIONS[text]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    errors.append(f"{context_label}: fecha no reconocida: {text!r}")
    return None


def _find_header_row(ws, markers, max_scan_rows=5):
    for r in range(1, max_scan_rows + 1):
        values = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        text = " ".join(str(v).upper() for v in values if v)
        if any(marker in text for marker in markers):
            return r, values
    return None, None


def _map_headers(raw_headers, aliases):
    mapping = {}
    for idx, raw in enumerate(raw_headers, start=1):
        if not raw:
            continue
        key = str(raw).strip().upper()
        logical = aliases.get(key)
        if logical:
            mapping[logical] = idx
    return mapping


class Command(BaseCommand):
    help = (
        "Importa EXCEL_TRABAJADORES.xlsx (document_explorer/data_imports/) "
        "hacia PersonIdentity y fleet.MachineAsset. Dry-run por defecto, "
        "usar --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Escribe de verdad. Sin este flag, solo informa (dry-run).",
        )
        parser.add_argument(
            "--excel-path",
            default=EXCEL_PATH,
            help="Ruta alternativa al .xlsx, si no es la version commiteada.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        excel_path = options["excel_path"]

        if not os.path.isfile(excel_path):
            self.stderr.write(f"No se encuentra el Excel en: {excel_path}")
            return

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        errors = []

        # ------------------------------------------------------------
        # Trabajadores
        # ------------------------------------------------------------
        workers_matched = 0
        workers_unmatched = []
        workers_seen_dni = set()

        for sheet_name in WORKER_SHEETS:
            if sheet_name not in wb.sheetnames:
                errors.append(f"Hoja no encontrada, saltada: {sheet_name!r}")
                continue
            ws = wb[sheet_name]
            header_row, raw_headers = _find_header_row(ws, ["DNI", "NOMBRE"])
            if header_row is None:
                errors.append(f"{sheet_name}: sin cabecera reconocible")
                continue
            columns = _map_headers(raw_headers, WORKER_HEADER_ALIASES)
            if "dni" not in columns:
                errors.append(f"{sheet_name}: columna DNI no localizada")
                continue

            for r in range(header_row + 1, ws.max_row + 1):
                raw_dni = ws.cell(row=r, column=columns["dni"]).value
                dni = _norm_dni(raw_dni)
                if not dni:
                    continue
                if dni in workers_seen_dni:
                    errors.append(
                        f"{sheet_name} fila {r}: DNI {dni} repetido en el "
                        "propio Excel (ya visto en otra hoja), se ignora "
                        "esta segunda aparicion"
                    )
                    continue
                workers_seen_dni.add(dni)

                def _cell(logical):
                    col = columns.get(logical)
                    return ws.cell(row=r, column=col).value if col else None

                context = f"{sheet_name} fila {r} (DNI {dni})"
                values = dict(
                    dni_expiry_date=_parse_date(_cell("dni_expiry"), context, errors),
                    driving_license_expiry_date=_parse_date(
                        _cell("driving_license_expiry"), context, errors,
                    ),
                    crane_operator_card_expiry_date=_parse_date(
                        _cell("crane_card_expiry"), context, errors,
                    ),
                    driver_qualification_card_expiry_date=_parse_date(
                        _cell("driver_qualification_card_expiry"), context, errors,
                    ),
                    tachograph_card_expiry_date=_parse_date(
                        _cell("tachograph_card_expiry"), context, errors,
                    ),
                    medical_exam_date=_parse_date(_cell("rm"), context, errors),
                    ss_affiliation_number=str(
                        _cell("ss_affiliation_number") or ""
                    ).strip(),
                    employer_company=str(_cell("empresa") or "").strip(),
                    phone=str(_cell("telefono") or "").strip(),
                    email=str(_cell("email") or "").strip(),
                )
                if dni in MANUAL_FIELD_OVERRIDES:
                    values.update(MANUAL_FIELD_OVERRIDES[dni])

                try:
                    person = PersonIdentity.objects.get(dni=dni)
                except PersonIdentity.DoesNotExist:
                    workers_unmatched.append((dni, sheet_name, r))
                    continue

                workers_matched += 1
                if apply_changes:
                    person.is_active_employee = True
                    person.excel_imported_at = datetime.datetime.now()
                    for field, value in values.items():
                        if value:
                            setattr(person, field, value)
                    person.save()

        # ------------------------------------------------------------
        # Maquinaria
        # ------------------------------------------------------------
        machines_matched = 0
        machines_unmatched = []

        if MACHINE_SHEET in wb.sheetnames:
            ws = wb[MACHINE_SHEET]
            header_row, raw_headers = _find_header_row(ws, ["CODIGO", "MATRICULA"])
            if header_row is None:
                errors.append(f"{MACHINE_SHEET}: sin cabecera reconocible")
            else:
                columns = _map_headers(raw_headers, MACHINE_HEADER_ALIASES)
                for r in range(header_row + 1, ws.max_row + 1):
                    raw_codigo = ws.cell(row=r, column=columns.get("codigo", 0)).value
                    codigo = _norm_code(raw_codigo)
                    if not codigo:
                        continue

                    def _mcell(logical):
                        col = columns.get(logical)
                        return ws.cell(row=r, column=col).value if col else None

                    context = f"{MACHINE_SHEET} fila {r} (codigo {codigo})"
                    machine = None
                    # Prueba varias normalizaciones reales contra
                    # MachineAsset.code, en orden: literal tal cual
                    # aparece en el Excel, sin espacios, sin guion.
                    # Nunca se adivina -- si ninguna coincide, se
                    # informa como sin cruzar, no se crea nada nuevo.
                    candidatos_code = []
                    if raw_codigo:
                        candidatos_code.append(str(raw_codigo).strip())
                    candidatos_code.append(codigo)
                    for candidato in candidatos_code:
                        machine = MachineAsset.objects.filter(
                            code__iexact=candidato,
                        ).first()
                        if machine:
                            break
                    if machine is None:
                        matricula = _mcell("matricula")
                        if matricula:
                            machine = MachineAsset.objects.filter(
                                plate__iexact=str(matricula).strip(),
                            ).first()

                    if machine is None:
                        machines_unmatched.append((raw_codigo, r))
                        continue

                    machines_matched += 1
                    if apply_changes:
                        machine.itv_date = _parse_date(
                            _mcell("itv"), context, errors,
                        ) or machine.itv_date
                        machine.itv_next_appointment = _parse_date(
                            _mcell("cita_itv"), context, errors,
                        ) or machine.itv_next_appointment
                        seguro = _mcell("seguro")
                        if seguro:
                            machine.insurance_info = str(seguro).strip()
                        oca = _parse_date(_mcell("oca"), context, errors)
                        if oca:
                            machine.oca_date = oca
                        machine.excel_imported_at = datetime.datetime.now()
                        machine.save()
        else:
            errors.append(f"Hoja no encontrada: {MACHINE_SHEET!r}")

        # ------------------------------------------------------------
        # Resumen
        # ------------------------------------------------------------
        self.stdout.write("=" * 70)
        self.stdout.write(f"MODO: {'APLICADO' if apply_changes else 'DRY-RUN (sin --apply)'}")
        self.stdout.write("=" * 70)
        self.stdout.write(
            f"Trabajadores -- DNIs distintos en el Excel: {len(workers_seen_dni)}"
        )
        self.stdout.write(f"  Cruzados con PersonIdentity real: {workers_matched}")
        self.stdout.write(
            f"  SIN PersonIdentity real (no tocados, no se infiere baja): "
            f"{len(workers_unmatched)}"
        )
        for dni, sheet_name, r in workers_unmatched:
            self.stdout.write(f"    - {dni} ({sheet_name} fila {r})")

        self.stdout.write("")
        self.stdout.write(f"Maquinaria -- filas con codigo en el Excel")
        self.stdout.write(f"  Cruzadas con MachineAsset real: {machines_matched}")
        self.stdout.write(f"  SIN MachineAsset real: {len(machines_unmatched)}")
        for raw_codigo, r in machines_unmatched:
            self.stdout.write(f"    - {raw_codigo!r} (fila {r})")

        if errors:
            self.stdout.write("")
            self.stdout.write(f"Incidencias reales durante el parseo ({len(errors)}):")
            for e in errors:
                self.stdout.write(f"    ! {e}")
