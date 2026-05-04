# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/repair_entry_lines.py

"""
Django management command: repair_entry_lines.

Applies deterministic corrections to existing WorkOrderEntryLine records
in the database without invoking AI. Operates in three sequential rules:

  RULE 1 — O.R. field contains a time value with hc=None:
    Moves or_val (HH:MM) to hc. Only applied when hc is null — lines
    where hc and hf are already populated are never modified by this rule
    (those correspond to the line-overflow pattern handled by Gemini).

  RULE 2 — machine_raw contains multiple machine codes:
    Explodes the line into N WorkOrderEntryLine records, one per detected
    code, replicating fault_description, repair_notes, hc, hf and or_val.
    The original line is converted into the first entry; additional lines
    are created with incremental line_number values. Adds "MAQUINA" to
    flags on all resulting lines.

  RULE 3 — machine_asset unresolved with non-empty machine_raw:
    Re-runs _normalise_machine_code + _resolve_machine_asset (with the
    improved morphological substitution algorithm, including the purely-numeric
    code reinterpretation added in H8/S009: leading digit → letter candidate
    via _OCR_DIGIT_TO_LETTER_MAP, e.g. "294" → "Z-94") on every line where
    machine_asset is None and machine_raw is not blank.

  RULE 4 — machine_norm inconsistent with current normaliser output:
    Re-normalises lines where machine_asset IS resolved but machine_norm
    is still in 'raw' form (equal to the uppercased machine_raw, empty,
    or purely numeric). Lines whose machine_norm already has a
    LETTER-NUMBER structure different from machine_raw were established
    by a richer resolution path (morphological resolver) and are skipped.
    Only machine_norm is updated — machine_asset is left untouched.

Flags:
  --company   Filter by company pk or exact name (optional).
  --dry-run   (default) Show detected incidences without modifying anything.
  --apply     Apply corrections. IRREVERSIBLE without prior --dry-run.

---

Comando de gestión Django: repair_entry_lines.

Aplica correcciones determinísticas sobre los registros WorkOrderEntryLine
existentes en base de datos sin invocar IA. Opera en tres reglas secuenciales:

  REGLA 1 — Campo O.R. contiene un horario con hc=None:
    Mueve or_val (HH:MM) a hc. Solo se aplica cuando hc es nulo — las líneas
    donde hc y hf ya están rellenos nunca se modifican con esta regla
    (corresponden al patrón de desbordamiento de línea gestionado por Gemini).

  REGLA 2 — machine_raw contiene múltiples códigos de máquina:
    Explosiona la línea en N registros WorkOrderEntryLine, uno por código
    detectado, replicando fault_description, repair_notes, hc, hf y or_val.
    La línea original se convierte en la primera entrada; las adicionales
    se crean con line_number incremental. Añade "MAQUINA" a flags en todas.

  REGLA 3 — machine_asset no resuelto con machine_raw no vacío:
    Re-ejecuta _normalise_machine_code + _resolve_machine_asset (con el
    algoritmo de sustitución morfológica mejorado) sobre cada línea donde
    machine_asset es None y machine_raw no está vacío, para beneficiarse
    de la mejora del resolver del Hito 8 / S008.

  REGLA 4 — machine_norm inconsistente con la salida actual del normalizador:
    Re-normaliza las líneas donde machine_asset SÍ está resuelto pero
    machine_norm sigue en forma 'cruda' (igual al machine_raw en mayúsculas,
    vacío, o puramente numérico). Las líneas cuyo machine_norm ya tiene
    estructura LETRA-NÚMERO distinta al raw fueron establecidas por una
    vía de resolución más rica (resolver morfológico) y se omiten.
    Solo se actualiza machine_norm — machine_asset se deja intacto.

Flags:
  --company   Filtrar por pk o nombre exacto de empresa (opcional).
  --dry-run   (por defecto) Mostrar incidencias detectadas sin modificar nada.
  --apply     Aplicar correcciones. IRREVERSIBLE sin --dry-run previo.
"""

import re
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from work_order_processor.models import WorkOrderEntryLine
from work_order_processor.services import (
    _normalise_machine_code,
    _resolve_machine_asset,
)

logger = logging.getLogger(__name__)

# Regex that matches a time value in HH:MM format.
# Regex que coincide con un valor horario en formato HH:MM.
_TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')

# Regex that extracts individual machine-code tokens from a machine_raw field
# that may contain multiple codes. A token is: optional letter prefix (1-3
# letters) + optional space + optional hyphen + numeric suffix (1-4 digits),
# OR digits alone. The space-between-letter-and-digit variant (e.g. "Z 59")
# is normalised (space removed) inside _split_multi_codes.
#
# Regex que extrae tokens individuales de código de máquina de un campo
# machine_raw que puede contener múltiples códigos. Un token es: prefijo de
# letra opcional (1-3 letras) + espacio opcional + guion opcional + sufijo
# numérico (1-4 dígitos), O solo dígitos. La variante con espacio entre letra
# y dígito (ej. "Z 59") se normaliza (espacio eliminado) en _split_multi_codes.
_CODE_TOKEN_RE = re.compile(
    r'[A-Z]{1,3}\s?-?\d{1,4}|\d{1,4}',
    re.IGNORECASE,
)


def _parse_time_value(value: str):
    """
    Parses a HH:MM string into a datetime.time object.
    Returns None if the value is not a valid time string.

    ---

    Parsea una cadena HH:MM a un objeto datetime.time.
    Devuelve None si el valor no es una cadena de hora válida.
    """
    from datetime import time as dt_time
    if not value or not _TIME_RE.match(value.strip()):
        return None
    try:
        parts = value.strip().split(":")
        return dt_time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _split_multi_codes(machine_raw: str) -> list[str]:
    """
    Splits a machine_raw string containing multiple machine codes into a
    list of individual code strings. Returns a list with a single element
    if only one code is detected (or if the string is not a multi-code).

    Strategy: find all code-like tokens using _CODE_TOKEN_RE. If two or
    more tokens are found the field is considered a multi-code and the
    tokens are returned. Otherwise the original string is returned as-is
    so that the resolver can attempt morphological substitution on it.

    ---

    Divide una cadena machine_raw que contiene múltiples códigos de máquina
    en una lista de cadenas de código individuales. Devuelve una lista con
    un único elemento si solo se detecta un código (o si la cadena no es
    un multi-código).

    Estrategia: busca todos los tokens con formato de código usando
    _CODE_TOKEN_RE. Si se encuentran dos o más tokens el campo se considera
    multi-código y se devuelven los tokens. En caso contrario se devuelve
    la cadena original para que el resolver intente sustitución morfológica.
    """
    # Guard: canonical single-code pattern LETTERS?-DIGITS or LETTERS?DIGITS.
    # A single hyphen separating letters from digits is always one code —
    # never a multi-code field (e.g. "2-20" is one code, not two).
    # Guarda: patrón de código único canónico LETRAS?-DÍGITOS o LETRAS?DÍGITOS.
    # Un único guion entre letras y dígitos es siempre un solo código —
    # nunca un campo multi-código (ej. "2-20" es uno, no dos).
    _SINGLE_CODE_RE = re.compile(r'^[A-Z]{0,3}-?\d{1,4}$', re.IGNORECASE)
    if _SINGLE_CODE_RE.match(machine_raw.strip()):
        return [machine_raw]

    # Extract all code-like tokens from the raw string.
    # Extraer todos los tokens con formato de código de la cadena cruda.
    tokens = _CODE_TOKEN_RE.findall(machine_raw)

    # Normalise each token:
    #   1. Strip surrounding whitespace.
    #   2. Remove internal spaces between letter prefix and digits
    #      (e.g. "Z 59" → "Z59").
    #   3. Strip a leading "Y" that is the conjunction "y" written immediately
    #      before the code with no space (e.g. "Y295" → "295", "yZ26" → "Z26").
    #      This happens when operators write "... y Z26" and the OCR or the
    #      tokeniser captures "yZ26" as a single token.
    #
    # Normalizar cada token:
    #   1. Eliminar espacios circundantes.
    #   2. Eliminar espacios internos entre prefijo de letra y dígitos
    #      (ej. "Z 59" → "Z59").
    #   3. Eliminar una "Y" inicial que sea la conjunción "y" escrita pegada
    #      al código sin espacio (ej. "Y295" → "295", "yZ26" → "Z26").
    #      Ocurre cuando el operario escribe "... y Z26" y el tokenizador
    #      captura "yZ26" como un único token.
    _LEADING_Y_RE = re.compile(r'^[Yy](?=[A-Z]\d|\d{2,})', re.IGNORECASE)
    normalised: list[str] = []
    for t in tokens:
        t = t.strip()
        t = re.sub(r'([A-Z])\s+(\d)', r'\1\2', t, flags=re.IGNORECASE)
        t = _LEADING_Y_RE.sub('', t)
        normalised.append(t)

    # Deduplicate preserving order.
    # Deduplicar preservando orden.
    seen: set[str] = set()
    unique_tokens: list[str] = []
    for t in normalised:
        t_upper = t.upper()
        if t_upper and t_upper not in seen:
            seen.add(t_upper)
            unique_tokens.append(t)

    if len(unique_tokens) < 2:
        return [machine_raw]

    # Validation guard: only consider the field a genuine multi-code if at
    # least 2 of the extracted tokens have a letter prefix that could plausibly
    # be a machine-code prefix (A-Z, 1-3 letters). Tokens that are purely
    # numeric without a resolvable letter prefix (e.g. "20", "2") or that
    # carry an implausible letter prefix (e.g. "Y295") are filtered out.
    # If fewer than 2 tokens pass this filter, the field is not a multi-code.
    #
    # Guarda de validación: considerar el campo multi-código genuino solo si
    # al menos 2 de los tokens extraídos tienen un prefijo de letra que puede
    # ser plausiblemente un prefijo de código de máquina (A-Z, 1-3 letras).
    # Los tokens puramente numéricos sin prefijo de letra resoluble (ej. "20",
    # "2") o con prefijo de letra implausible (ej. "Y295") se filtran.
    # Si menos de 2 tokens pasan el filtro, el campo no es multi-código.
    _VALID_TOKEN_RE = re.compile(
        r'^[A-Z]{1,3}-?\d{1,4}$',
        re.IGNORECASE,
    )
    # Pure numeric tokens are also valid if they are >= 3 digits (short codes
    # like "2" or "20" are almost certainly fragments, not standalone codes).
    # Los tokens puramente numéricos también son válidos si tienen >= 3 dígitos
    # (los códigos cortos como "2" o "20" casi seguro son fragmentos).
    _PURE_NUMERIC_RE = re.compile(r'^\d{3,4}$')

    valid_count = sum(
        1 for t in unique_tokens
        if _VALID_TOKEN_RE.match(t) or _PURE_NUMERIC_RE.match(t)
    )

    return unique_tokens if valid_count >= 2 else [machine_raw]


class Command(BaseCommand):
    """
    Management command that applies deterministic corrections to
    WorkOrderEntryLine records already persisted in the database.

    ---

    Comando de gestión que aplica correcciones determinísticas sobre
    los registros WorkOrderEntryLine ya persistidos en base de datos.
    """

    help = (
        "Aplica correcciones determinísticas sobre WorkOrderEntryLine "
        "existentes en BD (sin IA). Usar --dry-run primero, luego --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            type=str,
            default=None,
            help=(
                "Filtrar por pk numérico o nombre exacto de empresa. "
                "Si se omite, procesa todas las empresas."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Modo simulación (por defecto): muestra las incidencias "
                "detectadas sin modificar ningún registro."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help=(
                "Aplica las correcciones detectadas. "
                "IRREVERSIBLE — ejecutar --dry-run primero."
            ),
        )

    # ------------------------------------------------------------------
    # Entry point / Punto de entrada
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        """
        Main handler. Resolves the company filter, builds the queryset,
        and runs the four correction rules sequentially.

        ---

        Manejador principal. Resuelve el filtro de empresa, construye el
        queryset y ejecuta las cuatro reglas de corrección secuencialmente.
        """
        dry_run = not options["apply"]

        if dry_run:
            self.stdout.write(
                "# Modo --dry-run activo. No se modificará ningún registro.\n"
            )
        else:
            self.stdout.write(
                "# Modo --apply activo. Las correcciones se persistirán en BD.\n"
            )

        # -- Company filter / Filtro de empresa --
        company = None
        if options["company"]:
            from ivr_config.models import Company
            raw = options["company"].strip()
            if raw.isdigit():
                try:
                    company = Company.objects.get(pk=int(raw))
                except Company.DoesNotExist:
                    raise CommandError(
                        f"No existe ninguna empresa con pk={raw}."
                    )
            else:
                try:
                    company = Company.objects.get(name=raw)
                except Company.DoesNotExist:
                    raise CommandError(
                        f"No existe ninguna empresa con nombre exacto '{raw}'."
                    )
            self.stdout.write(f"# Empresa filtrada: {company} (pk={company.pk})\n")

        # -- Base queryset / Queryset base --
        qs = WorkOrderEntryLine.objects.select_related(
            "entry__work_order__company",
            "machine_asset",
        ).all()

        if company is not None:
            qs = qs.filter(entry__work_order__company=company)

        lines = list(qs)
        total_inspected   = len(lines)
        total_r1          = 0
        total_r2          = 0
        total_r3_resolved = 0
        total_r3_tried    = 0
        total_r4_updated  = 0
        total_r4_tried    = 0

        # ------------------------------------------------------------------
        # RULE 1 — or_val with HH:MM format and hc=None
        # REGLA 1 — or_val con formato HH:MM y hc=None
        # ------------------------------------------------------------------
        self.stdout.write("\n# ── REGLA 1 — or_val horario con hc=None ──────────────\n")

        r1_lines = [
            l for l in lines
            if _TIME_RE.match(l.or_val or "") and l.hc is None
        ]

        if not r1_lines:
            self.stdout.write("  Sin incidencias detectadas.\n")
        else:
            for line in r1_lines:
                parsed_time = _parse_time_value(line.or_val)
                self.stdout.write(
                    f"  pk={line.pk} | operario={line.entry.worker_name} | "
                    f"fecha={line.entry.work_date} | "
                    f"or_val={line.or_val!r} → hc={line.or_val!r} | "
                    f"machine_raw={line.machine_raw!r}\n"
                )
                if not dry_run and parsed_time is not None:
                    line.hc     = parsed_time
                    line.or_val = ""
                    line.save(update_fields=["hc", "or_val"])
                    total_r1 += 1

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] {len(r1_lines)} línea(s) serían corregidas.\n"
                )
            else:
                self.stdout.write(
                    f"  {total_r1} línea(s) corregidas.\n"
                )

        # ------------------------------------------------------------------
        # RULE 2 — machine_raw with multiple machine codes
        # REGLA 2 — machine_raw con múltiples códigos de máquina
        # ------------------------------------------------------------------
        self.stdout.write("\n# ── REGLA 2 — machine_raw con múltiples códigos ───────\n")

        r2_lines = [
            l for l in lines
            if l.machine_raw and len(_split_multi_codes(l.machine_raw)) >= 2
        ]

        if not r2_lines:
            self.stdout.write("  Sin incidencias detectadas.\n")
        else:
            for line in r2_lines:
                codes = _split_multi_codes(line.machine_raw)
                self.stdout.write(
                    f"  pk={line.pk} | operario={line.entry.worker_name} | "
                    f"fecha={line.entry.work_date} | "
                    f"machine_raw={line.machine_raw!r} → {len(codes)} entradas: "
                    f"{codes}\n"
                    f"    desc={line.fault_description!r}\n"
                )

                if not dry_run:
                    with transaction.atomic():
                        # Determine the maximum existing line_number for this
                        # entry so that new lines do not collide.
                        # Determinar el line_number máximo existente para esta
                        # entrada para que las nuevas no colisionen.
                        existing_max = (
                            WorkOrderEntryLine.objects
                            .filter(entry=line.entry)
                            .order_by("-line_number")
                            .values_list("line_number", flat=True)
                            .first()
                        ) or 0

                        # Update the original line with the first code.
                        # Actualizar la línea original con el primer código.
                        first_code       = codes[0].strip()
                        first_norm       = _normalise_machine_code(first_code)
                        first_asset      = _resolve_machine_asset(
                            first_norm,
                            company=line.entry.work_order.company,
                        )
                        current_flags    = list(line.flags or [])
                        if "MAQUINA" not in current_flags:
                            current_flags.append("MAQUINA")

                        line.machine_raw  = first_code
                        line.machine_norm = first_norm
                        line.machine_asset = first_asset
                        line.flags         = current_flags
                        line.save(update_fields=[
                            "machine_raw", "machine_norm",
                            "machine_asset", "flags",
                        ])

                        # Create one new line per additional code.
                        # Crear una nueva línea por cada código adicional.
                        for offset, code in enumerate(codes[1:], start=1):
                            code       = code.strip()
                            norm       = _normalise_machine_code(code)
                            asset      = _resolve_machine_asset(
                                norm,
                                company=line.entry.work_order.company,
                            )
                            new_flags  = ["MAQUINA"]
                            WorkOrderEntryLine.objects.create(
                                entry              = line.entry,
                                line_number        = existing_max + offset,
                                machine_raw        = code,
                                machine_norm       = norm,
                                machine_asset      = asset,
                                fault_description = line.fault_description,
                                repair_notes         = line.repair_notes,
                                hc                 = line.hc,
                                hf                 = line.hf,
                                or_val             = "",
                                delta_hours        = line.delta_hours,
                                flags              = new_flags,
                            )
                            self.stdout.write(
                                f"    → Nueva línea creada: "
                                f"machine_raw={code!r} | "
                                f"machine_norm={norm!r} | "
                                f"machine_asset={asset}\n"
                            )

                        total_r2 += 1

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] {len(r2_lines)} línea(s) serían explosionadas.\n"
                )
            else:
                self.stdout.write(
                    f"  {total_r2} línea(s) procesadas.\n"
                )

        # ------------------------------------------------------------------
        # RULE 3 — Re-resolve unresolved machine_asset with improved resolver
        # REGLA 3 — Re-resolver machine_asset no resuelto con resolver mejorado
        # ------------------------------------------------------------------
        self.stdout.write("\n# ── REGLA 3 — Re-resolución morfológica de máquinas ───\n")

        # Reload lines after potential Rule 2 modifications to avoid stale data.
        # Recargar líneas tras posibles modificaciones de Regla 2 para evitar datos obsoletos.
        if not dry_run:
            qs_r3 = WorkOrderEntryLine.objects.select_related(
                "entry__work_order__company",
            ).filter(machine_asset__isnull=True).exclude(machine_raw="")
            if company is not None:
                qs_r3 = qs_r3.filter(entry__work_order__company=company)
            r3_lines = list(qs_r3)
        else:
            r3_lines = [
                l for l in lines
                if l.machine_asset is None and (l.machine_raw or "").strip()
            ]

        total_r3_tried = len(r3_lines)

        if not r3_lines:
            self.stdout.write("  Sin líneas con machine_asset no resuelto.\n")
        else:
            self.stdout.write(
                f"  {total_r3_tried} línea(s) con machine_asset=None "
                f"y machine_raw presente.\n"
            )
            for line in r3_lines:
                norm  = _normalise_machine_code(line.machine_raw)
                asset = _resolve_machine_asset(
                    norm,
                    company=line.entry.work_order.company,
                )
                if asset is not None:
                    self.stdout.write(
                        f"  pk={line.pk} | machine_raw={line.machine_raw!r} | "
                        f"machine_norm={norm!r} → resuelto: {asset.code}\n"
                    )
                    if not dry_run:
                        line.machine_norm  = norm
                        line.machine_asset = asset
                        line.save(update_fields=["machine_norm", "machine_asset"])
                        total_r3_resolved += 1
                else:
                    self.stdout.write(
                        f"  pk={line.pk} | machine_raw={line.machine_raw!r} | "
                        f"machine_norm={norm!r} → sin resolución.\n"
                    )

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] Resolución pendiente de --apply para ver resultados reales.\n"
                )
            else:
                self.stdout.write(
                    f"  {total_r3_resolved} de {total_r3_tried} línea(s) resueltas.\n"
                )

        # ------------------------------------------------------------------
        # RULE 4 — Re-normalise machine_norm for already-resolved lines
        # REGLA 4 — Re-normalizar machine_norm en líneas ya resueltas
        # ------------------------------------------------------------------
        self.stdout.write("\n# ── REGLA 4 — Re-normalización de machine_norm inconsistente ──\n")

        # Candidates: machine_asset is resolved but machine_norm does not
        # match the current normaliser output for machine_raw.
        # Candidatas: machine_asset resuelto pero machine_norm no coincide
        # con la salida actual del normalizador para machine_raw.
        if not dry_run:
            qs_r4 = WorkOrderEntryLine.objects.select_related(
                "entry__work_order__company",
                "machine_asset",
            ).filter(
                machine_asset__isnull=False,
            ).exclude(machine_raw="")
            if company is not None:
                qs_r4 = qs_r4.filter(entry__work_order__company=company)
            r4_lines = list(qs_r4)
        else:
            r4_lines = [
                l for l in lines
                if l.machine_asset is not None and (l.machine_raw or "").strip()
            ]

        total_r4_tried = len(r4_lines)
        r4_candidates  = []

        for line in r4_lines:
            expected_norm = _normalise_machine_code(line.machine_raw)
            if not expected_norm or expected_norm == line.machine_norm:
                continue

            # Guard: only update machine_norm when the current value is
            # 'raw' — i.e. it was never enriched by the morphological
            # resolver. A norm is considered raw when it equals the
            # uppercased machine_raw, is empty, or is purely numeric
            # (no letter prefix structure). If the existing norm already
            # has a LETTER-NUMBER structure different from machine_raw
            # it was established by a richer resolution path and must
            # not be overwritten by the simpler normaliser output.
            #
            # Guarda: solo actualizar machine_norm cuando el valor actual
            # es 'crudo' — es decir, nunca fue enriquecido por el resolver
            # morfológico. Un norm se considera crudo cuando es igual al
            # machine_raw en mayúsculas, está vacío, o es puramente
            # numérico (sin estructura de prefijo de letra). Si el norm
            # existente ya tiene estructura LETRA-NÚMERO distinta al raw
            # fue establecido por una vía de resolución más rica y no
            # debe sobreescribirse con la salida del normalizador simple.
            current_is_raw = (
                line.machine_norm.upper() == line.machine_raw.strip().upper()
                or line.machine_norm == ""
                or line.machine_norm.replace("-", "").isdigit()
            )
            if not current_is_raw:
                continue

            r4_candidates.append((line, expected_norm))

        if not r4_candidates:
            self.stdout.write("  Sin líneas con machine_norm inconsistente.\n")
        else:
            self.stdout.write(
                f"  {len(r4_candidates)} línea(s) con machine_norm inconsistente.\n"
            )
            for line, expected_norm in r4_candidates:
                self.stdout.write(
                    f"  pk={line.pk} | machine_raw={line.machine_raw!r} | "
                    f"machine_norm={line.machine_norm!r} → {expected_norm!r} | "
                    f"machine_asset={line.machine_asset.code}\n"
                )
                if not dry_run:
                    line.machine_norm = expected_norm
                    line.save(update_fields=["machine_norm"])
                    total_r4_updated += 1

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] {len(r4_candidates)} línea(s) serían actualizadas.\n"
                )
            else:
                self.stdout.write(
                    f"  {total_r4_updated} línea(s) actualizadas.\n"
                )

        # ------------------------------------------------------------------
        # Summary / Resumen final
        # ------------------------------------------------------------------
        self.stdout.write("\n# ── RESUMEN ────────────────────────────────────────────\n")
        self.stdout.write(f"  Total líneas inspeccionadas : {total_inspected}\n")

        if dry_run:
            self.stdout.write(
                f"  Regla 1 (or_val→hc)         : {len(r1_lines)} candidata(s)\n"
                f"  Regla 2 (multi-código)       : {len(r2_lines)} candidata(s)\n"
                f"  Regla 3 (re-resolución)      : {total_r3_tried} candidata(s)\n"
                f"  Regla 4 (re-normalización)   : {len(r4_candidates)} candidata(s)\n"
                f"\n  Modo DRY-RUN — ningún cambio aplicado.\n"
                f"  Ejecutar con --apply para persistir las correcciones.\n"
            )
        else:
            self.stdout.write(
                f"  Regla 1 aplicada             : {total_r1} línea(s)\n"
                f"  Regla 2 aplicada             : {total_r2} línea(s)\n"
                f"  Regla 3 resuelta             : {total_r3_resolved}/{total_r3_tried}\n"
                f"  Regla 4 re-normalizada       : {total_r4_updated}/{total_r4_tried}\n"
                f"\n  Correcciones persistidas en BD.\n"
            )
