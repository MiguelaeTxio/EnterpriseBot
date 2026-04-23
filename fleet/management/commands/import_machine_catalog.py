# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/import_machine_catalog.py

"""
Django management command: import_machine_catalog.
Parses the LISTADO MAQUINARIA PDF exported from the fleet management system
and imports all machine records into the MachineAsset model.

The PDF follows a fixed hierarchical structure:
  EMPRESA: <codigo> - <nombre>
    FAMILIA: <nombre_familia>
      TIPO: <codigo_tipo> - <nombre_tipo>
        <codigo> <matricula> <num_bastidor> <marca_modelo> <fecha_compra> <kms> <horas>

Each machine row is mapped to a MachineAsset record. The command is
idempotent: existing records (matched by `codigo`) are updated, not
duplicated. Records not present in the PDF are left untouched unless
--deactivate-missing is passed, in which case they are marked inactive.

Usage:
    python -m dotenv run python manage.py import_machine_catalog \
        --pdf /ruta/al/LISTADO_MAQUINARIA.pdf \
        --company-map GRA=1 TRA=2 GRH=3 GRB=4 GRG=5 GLA=6 LRA=7 BEN=8 \
        [--deactivate-missing] \
        [--dry-run]

---

Comando de gestión Django: import_machine_catalog.
Parsea el PDF LISTADO MAQUINARIA exportado del sistema de gestión de flota
e importa todos los registros de maquinaria al modelo MachineAsset.

El PDF sigue una estructura jerárquica fija:
  EMPRESA: <codigo> - <nombre>
    FAMILIA: <nombre_familia>
      TIPO: <codigo_tipo> - <nombre_tipo>
        <codigo> <matricula> <num_bastidor> <marca_modelo> <fecha_compra> <kms> <horas>

Cada fila de máquina se mapea a un registro MachineAsset. El comando es
idempotente: los registros existentes (identificados por `codigo`) se
actualizan, no se duplican. Los registros ausentes en el PDF se dejan
intactos salvo que se pase --deactivate-missing, en cuyo caso se marcan
como inactivos.

Uso:
    python -m dotenv run python manage.py import_machine_catalog \
        --pdf /ruta/al/LISTADO_MAQUINARIA.pdf \
        --company-map GRA=1 TRA=2 GRH=3 GRB=4 GRG=5 GLA=6 LRA=7 BEN=8 \
        [--deactivate-missing] \
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
# Regex patterns for PDF line classification
# Patrones regex para clasificación de líneas del PDF
# ---------------------------------------------------------------------------

# Matches:  EMPRESA: GRA - GRUAS ADOLFO ALVAREZ, S.L. CIF B29405040
_RE_EMPRESA = re.compile(
    r"^\s*EMPRESA:\s*(?P<codigo>[A-Z0-9]+)\s*-\s*(?P<nombre>.+?)\s*$"
)

# Matches:  FAMILIA: MOVILES - GRUAS MOVILES   or   FAMILIA: MOVILES
_RE_FAMILIA = re.compile(
    r"^\s*FAMILIA:\s*(?P<codigo>[A-Z0-9./\- ]+?)(?:\s*-\s*(?P<nombre>.+?))?\s*$"
)

# Matches:  TIPO: MV035 - GRUA MOVIL DE 35 TM   or   TIPO: MV035
_RE_TIPO = re.compile(
    r"^\s*TIPO:\s*(?P<codigo>[A-Z0-9./\- ]+?)(?:\s*-\s*(?P<nombre>.+?))?\s*$"
)

# Matches the table header line — used to skip it.
# Coincide con la línea de cabecera de la tabla — se usa para saltarla.
_RE_HEADER = re.compile(
    r"^\s*C[oó]digo\s+Matr[ií]cula\s+N[oº°]\s*Bastidor"
)

# Matches a machine data row. The PDF places each field separated by
# variable whitespace. Fields after marca_modelo may be absent.
# Coincide con una fila de datos de máquina. El PDF separa cada campo con
# espacios variables. Los campos tras marca_modelo pueden estar ausentes.
#
# Strategy: split on 2+ spaces to isolate tokens, then validate the first
# token as a plausible machine code (starts with letter or digit, short).
# Estrategia: dividir en 2+ espacios para aislar tokens, luego validar el
# primer token como un código de máquina plausible.
_RE_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _is_machine_code(token: str) -> bool:
    """
    Heuristic to decide whether a token looks like a machine code.
    Machine codes are short (≤20 chars), start with a letter or digit,
    and do not contain keywords that identify structural lines.

    ---

    Heurístico para decidir si un token parece un código de máquina.
    Los códigos de máquina son cortos (≤20 caracteres), comienzan con
    letra o dígito y no contienen palabras clave de líneas estructurales.
    """
    if not token or len(token) > 20:
        return False
    if token.startswith(("EMPRESA", "FAMILIA", "TIPO", "Código", "Hora", "Fecha",
                          "Página", "Maquinaria", "Criterios", "Familia", "Tipo",
                          "Bajas", "v ", "v1")):
        return False
    return bool(re.match(r"^[A-Za-z0-9]", token))


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


def _parse_machine_row(tokens: list[str]) -> dict | None:
    """
    Attempts to parse a list of whitespace-split tokens into a machine
    record dict. Returns None if the tokens do not represent a valid row.

    Token order from the PDF:
      [0] codigo
      [1] matricula
      [2] num_bastidor
      [3] marca (may span multiple tokens before the date)
      [-3] fecha_compra (DD/MM/YYYY)
      [-2] kms
      [-1] horas

    ---

    Intenta parsear una lista de tokens separados por espacios en un dict
    de registro de máquina. Devuelve None si los tokens no representan
    una fila válida.

    Orden de tokens del PDF:
      [0] codigo
      [1] matricula
      [2] num_bastidor
      [3] marca (puede abarcar varios tokens antes de la fecha)
      [-3] fecha_compra (DD/MM/YYYY)
      [-2] kms
      [-1] horas
    """
    if len(tokens) < 4:
        return None
    if not _is_machine_code(tokens[0]):
        return None

    codigo       = tokens[0].strip().upper()
    matricula    = tokens[1].strip() if len(tokens) > 1 else ""
    num_bastidor = tokens[2].strip() if len(tokens) > 2 else ""

    # Locate the date token to split off marca_modelo, kms, horas.
    # Localizar el token de fecha para separar marca_modelo, kms, horas.
    date_idx = None
    for i, tok in enumerate(tokens):
        if _RE_DATE.match(tok):
            date_idx = i
            break

    if date_idx is not None and date_idx >= 3:
        marca_modelo  = " ".join(tokens[3:date_idx]).strip()
        fecha_compra  = _parse_date(tokens[date_idx])
        kms           = _parse_int(tokens[date_idx + 1]) if date_idx + 1 < len(tokens) else 0
        horas         = _parse_int(tokens[date_idx + 2]) if date_idx + 2 < len(tokens) else 0
    else:
        # No date found — marca_modelo spans remaining tokens.
        # Sin fecha — marca_modelo abarca los tokens restantes.
        marca_modelo = " ".join(tokens[3:]).strip()
        fecha_compra = None
        kms          = 0
        horas        = 0

    return {
        "codigo":       codigo,
        "matricula":    matricula,
        "num_bastidor": num_bastidor,
        "marca_modelo": marca_modelo,
        "fecha_compra": fecha_compra,
        "kms":          kms,
        "horas":        horas,
    }


def _parse_catalogue(lines: list[str]) -> list[dict]:
    """
    Iterates the extracted PDF lines and returns a list of machine record
    dicts enriched with empresa, familia and tipo context.

    ---

    Itera las líneas extraídas del PDF y devuelve una lista de dicts de
    registro de máquina enriquecidos con el contexto de empresa, familia
    y tipo.
    """
    records: list[dict] = []

    current_empresa_codigo  = ""
    current_empresa_nombre  = ""
    current_familia         = ""
    current_tipo_codigo     = ""
    current_tipo_nombre     = ""

    for line in lines:
        # --- Structural markers / Marcadores estructurales ---
        m = _RE_EMPRESA.match(line)
        if m:
            current_empresa_codigo = m.group("codigo").strip()
            current_empresa_nombre = m.group("nombre").strip()
            current_familia        = ""
            current_tipo_codigo    = ""
            current_tipo_nombre    = ""
            continue

        m = _RE_FAMILIA.match(line)
        if m:
            current_familia     = m.group("codigo").strip()
            current_tipo_codigo = ""
            current_tipo_nombre = ""
            continue

        m = _RE_TIPO.match(line)
        if m:
            current_tipo_codigo = m.group("codigo").strip()
            current_tipo_nombre = (m.group("nombre") or "").strip()
            continue

        # Skip table header / Saltar cabecera de tabla.
        if _RE_HEADER.match(line):
            continue

        # Skip page metadata lines / Saltar líneas de metadatos de página.
        if re.match(r"^\s*(Hora:|Fecha:|Página:|v\s*\d)", line):
            continue

        # Attempt to parse as machine row using 2+-space split.
        # Intentar parsear como fila de máquina usando separación de 2+ espacios.
        tokens = re.split(r"\s{2,}", line.strip())
        record = _parse_machine_row(tokens)

        if record is None:
            continue

        record.update({
            "empresa_codigo": current_empresa_codigo,
            "empresa_nombre": current_empresa_nombre,
            "familia":        current_familia,
            "tipo_codigo":    current_tipo_codigo,
            "tipo_nombre":    current_tipo_nombre,
        })
        records.append(record)

    return records


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
                codigo, company_id = entry.split("=")
                company_map[codigo.strip().upper()] = int(company_id.strip())
            except ValueError:
                raise CommandError(
                    f"# Formato inválido en --company-map: '{entry}'. "
                    f"Use CODIGO=ID (ej: GRA=1)."
                )

        self.stdout.write("# Extrayendo texto del PDF...")
        lines   = _extract_text_from_pdf(pdf_path)
        self.stdout.write(f"# Líneas extraídas: {len(lines)}")

        self.stdout.write("# Parseando catálogo de maquinaria...")
        records = _parse_catalogue(lines)
        self.stdout.write(f"# Registros encontrados en el PDF: {len(records)}")

        if dry_run:
            self.stdout.write("# [DRY-RUN] Registros parseados:")
            for r in records:
                self.stdout.write(
                    f"  {r['codigo']:20s} | {r['empresa_codigo']:6s} | "
                    f"{r['familia']:15s} | {r['marca_modelo']}"
                )
            self.stdout.write(f"# [DRY-RUN] Total: {len(records)} registros. Sin escritura en BD.")
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
        created_count   = 0
        updated_count   = 0
        skipped_count   = 0
        imported_codes: set[str] = set()

        with transaction.atomic():
            for rec in records:
                emp_codigo = rec["empresa_codigo"].upper()

                if emp_codigo not in company_map:
                    self.stdout.write(
                        f"# OMITIDO (sin mapeo de empresa): "
                        f"{rec['codigo']} [{emp_codigo}]"
                    )
                    skipped_count += 1
                    continue

                company    = company_cache[company_map[emp_codigo]]
                codigo     = rec["codigo"]
                imported_codes.add(codigo)

                defaults = {
                    "company":        company,
                    "empresa_codigo": emp_codigo,
                    "empresa_nombre": rec["empresa_nombre"],
                    "familia":        rec["familia"],
                    "tipo_codigo":    rec["tipo_codigo"],
                    "tipo_nombre":    rec["tipo_nombre"],
                    "matricula":      rec["matricula"],
                    "num_bastidor":   rec["num_bastidor"],
                    "marca_modelo":   rec["marca_modelo"],
                    "fecha_compra":   rec["fecha_compra"],
                    "kms":            rec["kms"],
                    "horas":          rec["horas"],
                    "es_activo":      True,
                }

                obj, created = MachineAsset.objects.update_or_create(
                    codigo=codigo,
                    defaults=defaults,
                )

                if created:
                    created_count += 1
                    self.stdout.write(f"# CREADO:       {codigo} — {rec['marca_modelo']}")
                else:
                    updated_count += 1
                    self.stdout.write(f"# ACTUALIZADO:  {codigo} — {rec['marca_modelo']}")

            # --- Deactivate missing / Desactivar ausentes ---
            if deactivate_missing:
                missing_qs = MachineAsset.objects.exclude(codigo__in=imported_codes)
                deactivated = missing_qs.update(es_activo=False)
                self.stdout.write(
                    f"# DESACTIVADOS: {deactivated} registros no presentes en el PDF."
                )

        self.stdout.write(
            f"\n# Importación completada.\n"
            f"#   Creados:    {created_count}\n"
            f"#   Actualizados: {updated_count}\n"
            f"#   Omitidos:   {skipped_count}"
        )
