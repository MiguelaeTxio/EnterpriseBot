# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/import_machine_catalog.py

"""
Django management command: import_machine_catalog.
Parses the LISTADO MAQUINARIA PDF exported from the fleet management system
and imports all machine records into the MachineAsset model.

PyMuPDF renders each table cell as a separate line. The column order within
each table block is fixed, but fields with long values (plate+chassis on one
line, multi-word brand_model split across lines) cause variable line counts
per record. The parser uses a date-anchored strategy:

  - Lines are accumulated into a dynamic buffer (a plain list).
  - After each line is added, the buffer is scanned right-to-left for the
    pattern DATE NUMERIC NUMERIC. When found, everything before the date is
    the pre-date block [code, plate, chassis_number, brand_model...] and the
    three trailing tokens are [purchase_date, mileage, hours].
  - The first token of the pre-date block is validated as a machine code.
  - Consumed tokens are removed from the buffer with del, not reassigned,
    so the mutation is visible to the enclosing scope on the next iteration.
  - Structural markers (EMPRESA, FAMILIA, TIPO) and page metadata flush any
    pending record and reset the buffer.

The command is idempotent: existing records (matched by `code`) are updated,
not duplicated.

Usage:
    python -m dotenv run python manage.py import_machine_catalog \\
        --pdf /ruta/al/LISTADO_MAQUINARIA.pdf \\
        --company-map GRA=1 TRA=2 GRH=3 GRB=4 GRG=5 GLA=6 LRA=7 BEN=8 \\
        [--deactivate-missing] \\
        [--dry-run]

---

Comando de gestión Django: import_machine_catalog.
Parsea el PDF LISTADO MAQUINARIA exportado del sistema de gestión de flota
e importa todos los registros de maquinaria al modelo MachineAsset.

PyMuPDF renderiza cada celda de tabla como una línea separada. El orden de
columnas es fijo, pero campos con valores largos generan un número variable
de líneas por registro. El parser usa una estrategia anclada en la fecha:

  - Las líneas se acumulan en un buffer dinámico (lista simple).
  - Tras añadir cada línea, el buffer se escanea de derecha a izquierda
    buscando el patrón FECHA NUMERICO NUMERICO. Cuando se encuentra, todo
    lo anterior a la fecha es el bloque pre-fecha [code, plate,
    chassis_number, brand_model...] y los tres tokens finales son
    [purchase_date, mileage, hours].
  - El primer token del bloque pre-fecha se valida como código de máquina.
  - Los tokens consumidos se eliminan del buffer con del, no reasignando,
    de modo que la mutación es visible en el scope superior en la siguiente
    iteración.
  - Los marcadores estructurales (EMPRESA, FAMILIA, TIPO) y los metadatos
    de página vacían cualquier registro pendiente y resetean el buffer.

El comando es idempotente: los registros existentes (identificados por `code`)
se actualizan, no se duplican.

Uso:
    python -m dotenv run python manage.py import_machine_catalog \\
        --pdf /ruta/al/LISTADO_MAQUINARIA.pdf \\
        --company-map GRA=1 TRA=2 GRH=3 GRB=4 GRG=5 GLA=6 LRA=7 BEN=8 \\
        [--deactivate-missing] \\
        [--dry-run]
"""

import re
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF — ya en requirements
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fleet.models import MachineAsset
from ivr_config.models import Company


# ---------------------------------------------------------------------------
# Regex patterns / Patrones regex
# ---------------------------------------------------------------------------

# Structural markers — double space after colon matches PyMuPDF output.
# Marcadores estructurales — doble espacio tras los dos puntos = salida PyMuPDF.
_RE_EMPRESA = re.compile(
    r"^EMPRESA:\s+(?P<codigo>[A-Z0-9]+)\s+-\s+(?P<nombre>.+?)\s*$"
)
_RE_FAMILIA = re.compile(
    r"^FAMILIA:\s+(?P<codigo>[A-Z0-9./\- ]+?)(?:\s+-\s+(?P<nombre>.+?))?\s*$"
)
_RE_TIPO = re.compile(
    r"^TIPO:\s+(?P<codigo>[A-Z0-9./\- ]+?)(?:\s+-\s+(?P<nombre>.+?))?\s*$"
)

# Date token DD/MM/YYYY — flush anchor / Token de fecha — ancla de volcado.
_RE_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Numeric value token (mileage / hours) / Token de valor numérico (kms/horas).
_RE_NUMERIC = re.compile(r"^[\d.,]+$")

# Page metadata lines to skip / Líneas de metadatos de página a saltar.
# Note: bare single/double digit strings (0, 1 .. 99) are NOT excluded here
# because they are valid mileage/hours values. The PDF page-number token
# always appears after an explicit "Página:" line and is handled by that prefix.
# Bare time tokens (HH:MM) are excluded because they never appear as data values.
#
# Nota: los números solos de uno o dos dígitos (0, 1 .. 99) NO se excluyen aquí
# porque son valores válidos de kms/horas. El token de número de página del PDF
# siempre aparece tras una línea "Página:" explícita y se gestiona con ese prefijo.
# Los tokens de hora aislados (HH:MM) sí se excluyen porque nunca son valores de dato.
_RE_META = re.compile(
    r"^(Hora:|Fecha:|Página:|v\s*\d|Maquinaria de Empresas|Criterios de Selección"
    r"|Empresa:|Familia:|Tipo:|Bajas:|\d{1,2}:\d{2}$)"
)

# Column header tokens / Tokens de cabecera de columna.
_HEADER_TOKENS = {
    "Código", "Matrícula", "Nº Bastidor",
    "Marca / Modelo", "Compra", "Kms.", "Horas",
}

# Structural line prefixes / Prefijos de líneas estructurales.
_STRUCTURAL_PREFIXES = ("EMPRESA:", "FAMILIA:", "TIPO:")


# ---------------------------------------------------------------------------
# Helper functions / Funciones auxiliares
# ---------------------------------------------------------------------------

def _parse_date(value: str) -> date | None:
    """
    Parses a date string in DD/MM/YYYY format into a Python date.
    Returns None if unparseable.

    ---

    Parsea una cadena de fecha en formato DD/MM/YYYY a un objeto date.
    Devuelve None si no es parseable.
    """
    try:
        day, month, year = value.strip().split("/")
        return date(int(year), int(month), int(day))
    except (ValueError, AttributeError):
        return None


def _parse_int(value: str) -> int:
    """
    Parses a string as integer, returning 0 on failure.

    ---

    Parsea una cadena como entero, devolviendo 0 en caso de fallo.
    """
    try:
        return int(value.replace(".", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0


def _is_machine_code(token: str) -> bool:
    """
    Heuristic to decide whether a token looks like a machine code.
    Rejects empty strings, tokens longer than 30 chars, structural keywords,
    metadata patterns and pure date strings.

    ---

    Heurístico para decidir si un token parece un código de máquina.
    Rechaza cadenas vacías, tokens de más de 30 caracteres, palabras clave
    estructurales, patrones de metadatos y cadenas de fecha puras.
    """
    if not token or len(token) > 30:
        return False
    if any(token.startswith(p) for p in _STRUCTURAL_PREFIXES):
        return False
    if _RE_META.match(token):
        return False
    if _RE_DATE.match(token):
        return False
    return bool(re.match(r"^[A-Za-z0-9]", token))


def _scan_and_consume(
    buf: list[str],
    company_code: str,
    company_name: str,
    family: str,
    type_code: str,
    type_name: str,
) -> list[dict]:
    """
    Scans the buffer right-to-left for DATE NUMERIC NUMERIC anchor patterns.
    For each match found, builds a machine record and removes the consumed
    tokens from the buffer in place using del (not reassignment).
    Returns the list of records extracted in this pass.

    Pre-date block layout (variable length ≥ 2):
      [0]    code
      [1]    plate
      [2]    chassis_number  (optional — may be absent or merged with plate)
      [3..n] brand_model tokens (concatenated with space)

    ---

    Escanea el buffer de derecha a izquierda buscando patrones ancla
    FECHA NUMERICO NUMERICO. Por cada coincidencia, construye un registro
    de máquina y elimina los tokens consumidos del buffer en sitio usando
    del (no reasignación). Devuelve la lista de registros extraídos en
    este pase.

    Disposición del bloque pre-fecha (longitud variable ≥ 2):
      [0]    code
      [1]    plate
      [2]    chassis_number  (opcional — puede estar fusionado con plate)
      [3..n] tokens de brand_model (concatenados con espacio)
    """
    extracted: list[dict] = []

    while True:
        # Need at least: code + date + mileage + hours = 4 tokens.
        # Necesitamos al menos: code + fecha + kms + horas = 4 tokens.
        if len(buf) < 4:
            break

        anchor = None
        for i in range(len(buf) - 3, 0, -1):
            if (
                _RE_DATE.match(buf[i])
                and _RE_NUMERIC.match(buf[i + 1])
                and _RE_NUMERIC.match(buf[i + 2])
            ):
                anchor = i
                break

        if anchor is None:
            break

        pre_date    = buf[:anchor]
        purchase    = buf[anchor]
        mileage_raw = buf[anchor + 1]
        hours_raw   = buf[anchor + 2]

        # Remove consumed tokens from buffer in place.
        # Eliminar tokens consumidos del buffer en sitio.
        del buf[:anchor + 3]

        if len(pre_date) < 2:
            continue
        if not _is_machine_code(pre_date[0]):
            continue

        code           = pre_date[0].strip().upper()
        plate          = pre_date[1].strip()
        chassis_number = pre_date[2].strip() if len(pre_date) > 2 else ""
        brand_model    = " ".join(pre_date[3:]).strip() if len(pre_date) > 3 else ""

        extracted.append({
            "code":           code,
            "plate":          plate,
            "chassis_number": chassis_number,
            "brand_model":    brand_model,
            "purchase_date":  _parse_date(purchase),
            "mileage":        _parse_int(mileage_raw),
            "hours":          _parse_int(hours_raw),
            "company_code":   company_code,
            "company_name":   company_name,
            "family":         family,
            "type_code"
:      type_code,
            "type_name":      type_name,
        })

    return extracted


def _extract_text_from_pdf(pdf_path: Path) -> list[str]:
    """
    Extracts all text lines from the PDF using PyMuPDF.
    Returns a flat list of non-empty stripped lines preserving page order.

    ---

    Extrae todas las líneas de texto del PDF usando PyMuPDF.
    Devuelve una lista plana de líneas no vacías y saneadas preservando
    el orden de páginas.
    """
    lines: list[str] = []
    doc = fitz.open(str(pdf_path))
    for page in doc:
        page_text = page.get_text("text")
        for raw_line in page_text.splitlines():
            stripped = raw_line.strip()
            if stripped:
                lines.append(stripped)
    doc.close()
    return lines


def _parse_catalogue(lines: list[str]) -> list[dict]:
    """
    Iterates extracted PDF lines and returns machine record dicts enriched
    with company, family and type context.

    Uses a date-anchored strategy with in-place buffer mutation via del.
    The buffer is a plain list shared by reference; _scan_and_consume
    modifies it in place so the main loop always sees the current state.

    ---

    Itera las líneas extraídas del PDF y devuelve dicts de registro de
    máquina enriquecidos con el contexto de empresa, familia y tipo.

    Usa una estrategia anclada en la fecha con mutación en sitio del buffer
    mediante del. El buffer es una lista simple compartida por referencia;
    _scan_and_consume la modifica en sitio de modo que el bucle principal
    siempre ve el estado actual.
    """
    records: list[dict] = []

    current_company_code = ""
    current_company_name = ""
    current_family       = ""
    current_type_code    = ""
    current_type_name    = ""

    buf: list[str] = []

    def flush() -> None:
        """Flush any pending record from buf and clear it."""
        found = _scan_and_consume(
            buf,
            current_company_code, current_company_name,
            current_family, current_type_code, current_type_name,
        )
        records.extend(found)
        buf.clear()

    for line in lines:

        # --- Structural markers ---
        m = _RE_EMPRESA.match(line)
        if m:
            flush()
            current_company_code = m.group("code").strip()
            current_company_name = m.group("nombre").strip()
            current_family       = ""
            current_type_code    = ""
            current_type_name    = ""
            continue

        m = _RE_FAMILIA.match(line)
        if m:
            flush()
            current_family    = m.group("code").strip()
            current_type_code = ""
            current_type_name = ""
            continue

        m = _RE_TIPO.match(line)
        if m:
            flush()
            current_type_code = m.group("code").strip()
            current_type_name = (m.group("nombre") or "").strip()
            continue

        # --- Page metadata ---
        if _RE_META.match(line):
            flush()
            continue

        # --- Column header tokens ---
        if line in _HEADER_TOKENS:
            if line == "Código":
                flush()
            continue

        # --- Accumulate and attempt incremental flush ---
        buf.append(line)
        found = _scan_and_consume(
            buf,
            current_company_code, current_company_name,
            current_family, current_type_code, current_type_name,
        )
        records.extend(found)

    # Final flush / Volcado final.
    flush()

    return records


# ---------------------------------------------------------------------------
# Management command / Comando de gestión
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    """
    Management command that imports the LISTADO MAQUINARIA PDF into the
    MachineAsset table. Idempotent: safe to run multiple times.

    ---

    Comando de gestión que importa el PDF LISTADO MAQUINARIA en la tabla
    MachineAsset. Idempotente: seguro de ejecutar múltiples veces.
    """

    help = (
        "Importa el catálogo de maquinaria desde el PDF LISTADO MAQUINARIA "
        "al modelo MachineAsset. Idempotente: actualiza registros existentes."
    )

    def add_arguments(self, parser) -> None:
        """
        Defines the command-line arguments accepted by the command.

        ---

        Define los argumentos de línea de comandos aceptados por el comando.
        """
        parser.add_argument(
            "--pdf",
            required=True,
            type=str,
            help="Ruta absoluta al archivo PDF LISTADO MAQUINARIA.",
        )
        parser.add_argument(
            "--company-map",
            nargs="+",
            metavar="CODIGO=ID",
            default=[],
            help=(
                "Mapeo de código de empresa del catálogo al ID de Company en BD. "
                "Formato: GRA=1 TRA=2 GRH=3. Los códigos sin mapeo se omiten."
            ),
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            default=False,
            help=(
                "Marca como inactivos los MachineAsset existentes en BD que no "
                "aparezcan en el PDF importado."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Ejecuta el parseo y muestra el resultado sin escribir en BD."
            ),
        )

    def handle(self, *args, **options) -> None:
        """
        Entry point of the management command. Orchestrates PDF parsing,
        company resolution, and MachineAsset upsert.

        ---

        Punto de entrada del comando de gestión. Orquesta el parseo del PDF,
        la resolución de empresa y el upsert de MachineAsset.
        """
        pdf_path = Path(options["pdf"])
        if not pdf_path.exists():
            raise CommandError(f"# El archivo PDF no existe: {pdf_path}")

        dry_run            = options["dry_run"]
        deactivate_missing = options["deactivate_missing"]

        # --- Parse company map / Parsear mapa de empresas ---
        company_map: dict[str, int] = {}
        for entry in options["company_map"]:
            try:
                code_key, company_id = entry.split("=")
                company_map[code_key.strip().upper()] = int(company_id.strip())
            except ValueError:
                raise CommandError(
                    f"# Formato inválido en --company-map: '{entry}'. "
                    f"Use CODIGO=ID (ej: GRA=1)."
                )

        self.stdout.write("# Extrayendo texto del PDF...")
        lines = _extract_text_from_pdf(pdf_path)
        self.stdout.write(f"# Líneas extraídas: {len(lines)}")

        self.stdout.write("# Parseando catálogo de maquinaria...")
        records = _parse_catalogue(lines)
        self.stdout.write(f"# Registros encontrados en el PDF: {len(records)}")

        if dry_run:
            self.stdout.write("# [DRY-RUN] Registros parseados:")
            for r in records:
                self.stdout.write(
                    f"  {r['code']:20s} | {r['company_code']:6s} | "
                    f"{r['family']:15s} | {r['brand_model']}"
                )
            self.stdout.write(
                f"# [DRY-RUN] Total: {len(records)} registros. Sin escritura en BD."
            )
            return

        # --- Resolve Company instances / Resolver instancias de Company ---
        company_cache: dict[int, Company] = {}
        for company_id in set(company_map.values()):
            try:
                company_cache[company_id] = Company.objects.get(pk=company_id)
            except Company.DoesNotExist:
                raise CommandError(
                    f"# Company con ID={company_id} no existe en BD. "
                    f"Verifica el --company-map."
                )

        # --- Upsert loop / Bucle de upsert ---
        created_count  = 0
        updated_count  = 0
        skipped_count  = 0
        imported_codes: set[str] = set()

        with transaction.atomic():
            for rec in records:
                emp_code = rec["company_code"].upper()

                if emp_code not in company_map:
                    self.stdout.write(
                        f"# OMITIDO (sin mapeo de empresa): "
                        f"{rec['code']} [{emp_code}]"
                    )
                    skipped_count += 1
                    continue

                company = company_cache[company_map[emp_code]]
                code    = rec["code"]
                imported_codes.add(code)

                # Fields updated on every import run (catalog metadata).
                # Campos actualizados en cada importacion (metadatos del catalogo).
                defaults = {
                    "company":        company,
                    "company_code":   emp_code,
                    "company_name":   rec["company_name"],
                    "family":         rec["family"],
                    "type_code":      rec["type_code"],
                    "type_name":      rec["type_name"],
                    "plate":          rec["plate"],
                    "chassis_number": rec["chassis_number"],
                    "brand_model":    rec["brand_model"],
                    "purchase_date":  rec["purchase_date"],
                    "is_active":      True,
                }

                # mileage y hours se preservan en registros existentes para que
                # las lecturas reales de los operarios nunca sean sobreescritas
                # por los valores base del catalogo. Solo se aplican en creacion.
                create_only_defaults = {
                    "mileage": rec["mileage"],
                    "hours":   rec["hours"],
                }

                obj, created = MachineAsset.objects.update_or_create(
                    code=code,
                    defaults=defaults,
                )

                if created:
                    for field, value in create_only_defaults.items():
                        setattr(obj, field, value)
                    obj.save(update_fields=list(create_only_defaults.keys()))

                if created:
                    created_count += 1
                    self.stdout.write(f"# CREADO:       {code} — {rec['brand_model']}")
                else:
                    updated_count += 1
                    self.stdout.write(f"# ACTUALIZADO:  {code} — {rec['brand_model']}")

            # --- Deactivate missing / Desactivar ausentes ---
            if deactivate_missing:
                deactivated = MachineAsset.objects.exclude(
                    code__in=imported_codes
                ).update(is_active=False)
                self.stdout.write(
                    f"# DESACTIVADOS: {deactivated} registros no presentes en el PDF."
                )

        self.stdout.write(
            f"\n# Importación completada.\n"
            f"#   Creados:      {created_count}\n"
            f"#   Actualizados: {updated_count}\n"
            f"#   Omitidos:     {skipped_count}"
        )
