# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/validators.py
#
# Work-order entry validation module.
# Encapsulates all business rules applied before and after persisting a
# WorkOrder submitted via any of the three operator entry paths (Form, STT,
# Upload / confirm).
#
# Rules implemented:
#   R1 — Intra-part overlap:   two blocks within the same submission overlap.
#   R2 — HF <= HC:             end time is not strictly after start time.
#   R3 — Intra-part gap >= 30m: uncovered gap between consecutive blocks.
#   R4 — Inter-part overlap:   new part overlaps an existing WorkOrder in BD
#                              for the same operator and date.
#   R5 — Complementary part:  same date, no overlap — accepted silently.
#
# Módulo de validación de partes de trabajo.
# Encapsula todas las reglas de negocio aplicadas antes y después de persistir
# un WorkOrder enviado por cualquiera de las tres vías de entrada del operario
# (Formulario, STT, Upload / confirmar).
#
# Reglas implementadas:
#   R1 — Solapamiento intra-parte:  dos bloques del mismo envío se solapan.
#   R2 — HF <= HC:                  la hora de fin no es estrictamente posterior
#                                   a la hora de inicio.
#   R3 — Laguna intra-parte >= 30m: hueco sin cubrir entre bloques consecutivos.
#   R4 — Solapamiento inter-parte:  el nuevo parte solapa con un WorkOrder ya
#                                   existente en BD del mismo operario y fecha.
#   R5 — Parte complementario:      misma fecha, sin solapamiento — se acepta.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import List, Optional

from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Data structures
# Estructuras de datos
# ---------------------------------------------------------------------------

@dataclass
class TimeBlock:
    """
    Represents a single work block with a start time (hc) and end time (hf).
    Used as the input unit for all intra-part validation rules.
    Optional fields carry meter readings for R6/R7/R8 validation and the
    resolved MachineAsset instance for threshold contrast.

    ---

    Representa un único bloque de trabajo con hora de inicio (hc) y hora de
    fin (hf). Se usa como unidad de entrada para todas las reglas de validación
    intra-parte.
    Los campos opcionales transportan lecturas de contadores para la validación
    R6/R7/R8 y la instancia MachineAsset resuelta para el contraste de umbrales.
    """
    idx: int                        # 1-based block index — índice de bloque base 1
    hc:  time                       # start time — hora de inicio
    hf:  time                       # end time   — hora de fin
    machine_asset:         object   = None  # resolved MachineAsset or None — MachineAsset resuelto o None
    odometer_reading:      object   = None  # Decimal or None — km leídos
    engine_hours_reading:  object   = None  # Decimal or None — horas motor leídas
    crane_hours_reading:   object   = None  # Decimal or None — horas grúa leídas


@dataclass
class ValidationError:
    """
    Describes a single validation error or warning produced by a validator.

    Fields:
        rule    — rule code (R1–R4).
        message — human-readable description in Spanish for display in the UI.
        blocks  — list of block indices involved (for field highlighting).

    ---

    Describe un único error o aviso de validación producido por un validador.

    Campos:
        rule    — código de regla (R1–R4).
        message — descripción legible en castellano para mostrar en la UI.
        blocks  — lista de índices de bloques implicados (para resaltado de campo).
    """
    rule:    str
    message: str
    blocks:  List[int] = field(default_factory=list)


@dataclass
class IntraPartResult:
    """
    Result of intra-part validation (R1, R2, R3, R6, R7, R8).

    Fields:
        ok       — True if no blocking errors were found.
        errors   — list of blocking ValidationError instances.
        warnings — list of non-blocking ValidationError instances (R6/R7 jump alerts).

    ---

    Resultado de la validación intra-parte (R1, R2, R3, R6, R7, R8).

    Campos:
        ok       — True si no se encontraron errores bloqueantes.
        errors   — lista de instancias ValidationError bloqueantes.
        warnings — lista de instancias ValidationError no bloqueantes (avisos de salto R6/R7).
    """
    ok:       bool
    errors:   List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)


@dataclass
class InterPartResult:
    """
    Result of inter-part validation (R4, R5).

    Fields:
        has_overlap        — True if the new part overlaps an existing WorkOrder.
        conflicting_ids    — list of WorkOrder PKs that overlap with the new part.
        conflicting_dates  — list of work_date strings for display.

    ---

    Resultado de la validación inter-parte (R4, R5).

    Campos:
        has_overlap        — True si el nuevo parte solapa con un WorkOrder existente.
        conflicting_ids    — lista de PKs de WorkOrder que solapan con el nuevo parte.
        conflicting_dates  — lista de cadenas work_date para mostrar en la UI.
    """
    has_overlap:       bool
    conflicting_ids:   List[int]  = field(default_factory=list)
    conflicting_dates: List[str]  = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# Auxiliares
# ---------------------------------------------------------------------------

# Minimum gap duration (in minutes) that triggers an R3 error.
# Duración mínima de laguna (en minutos) que activa un error R3.
_GAP_THRESHOLD_MINUTES = 30

# R6 — Odometer jump threshold (km) above which a non-blocking warning is raised.
# R6 — Umbral de salto de odómetro (km) por encima del cual se emite un aviso no bloqueante.
_ODOMETER_JUMP_THRESHOLD_KM = 1000

# R7 — Engine hours jump threshold (h) above which a non-blocking warning is raised.
# R7 — Umbral de salto de horómetro motor (h) por encima del cual se emite un aviso no bloqueante.
_ENGINE_HOURS_JUMP_THRESHOLD_H = 500


def _to_minutes(t: time) -> int:
    """
    Converts a time object to total minutes since midnight.

    ---

    Convierte un objeto time a minutos totales desde medianoche.
    """
    return t.hour * 60 + t.minute


def _parse_hhmm(value: str) -> Optional[time]:
    """
    Parses a time string in HH:MM or H:MM format.
    Returns None if the string is empty or cannot be parsed.

    ---

    Parsea una cadena de tiempo en formato HH:MM o H:MM.
    Devuelve None si la cadena está vacía o no puede parsearse.
    """
    if not value:
        return None
    value = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            from datetime import datetime
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# R1 — Intra-part overlap / Solapamiento intra-parte
# ---------------------------------------------------------------------------

def validate_intra_overlap(blocks: List[TimeBlock]) -> List[ValidationError]:
    """
    Detects pairwise overlaps between blocks within the same submission.
    Two blocks [hc_a, hf_a) and [hc_b, hf_b) overlap if hc_a < hf_b and
    hc_b < hf_a (half-open interval semantics).

    Returns a list of ValidationError(rule='R1', ...) for each overlapping pair.

    ---

    Detecta solapamientos por pares entre bloques del mismo envío.
    Dos bloques [hc_a, hf_a) y [hc_b, hf_b) se solapan si hc_a < hf_b y
    hc_b < hf_a (semántica de intervalo semiabierto).

    Devuelve una lista de ValidationError(rule='R1', ...) por cada par solapado.
    """
    errors: List[ValidationError] = []
    sorted_blocks = sorted(blocks, key=lambda b: _to_minutes(b.hc))

    for i, a in enumerate(sorted_blocks):
        for b in sorted_blocks[i + 1:]:
            hc_a = _to_minutes(a.hc)
            hf_a = _to_minutes(a.hf)
            hc_b = _to_minutes(b.hc)
            hf_b = _to_minutes(b.hf)
            if hc_a < hf_b and hc_b < hf_a:
                errors.append(ValidationError(
                    rule="R1",
                    message=(
                        f"El bloque {a.idx} ({a.hc.strftime('%H:%M')}–{a.hf.strftime('%H:%M')}) "
                        f"se solapa con el bloque {b.idx} "
                        f"({b.hc.strftime('%H:%M')}–{b.hf.strftime('%H:%M')}). "
                        f"Corrige las horas antes de guardar."
                    ),
                    blocks=[a.idx, b.idx],
                ))
    return errors


# ---------------------------------------------------------------------------
# R2 — HF <= HC / Hora de fin no posterior a hora de inicio
# ---------------------------------------------------------------------------

def validate_hf_after_hc(blocks: List[TimeBlock]) -> List[ValidationError]:
    """
    Checks that each block's end time (hf) is strictly after its start time (hc).

    Returns a list of ValidationError(rule='R2', ...) for each offending block.

    ---

    Comprueba que la hora de fin (hf) de cada bloque es estrictamente posterior
    a la hora de inicio (hc).

    Devuelve una lista de ValidationError(rule='R2', ...) por cada bloque infractor.
    """
    errors: List[ValidationError] = []
    for b in blocks:
        if _to_minutes(b.hf) <= _to_minutes(b.hc):
            errors.append(ValidationError(
                rule="R2",
                message=(
                    f"Bloque {b.idx}: la hora de fin "
                    f"({b.hf.strftime('%H:%M')}) debe ser posterior "
                    f"a la hora de inicio ({b.hc.strftime('%H:%M')})."
                ),
                blocks=[b.idx],
            ))
    return errors


# ---------------------------------------------------------------------------
# R3 — Intra-part gap / Laguna intra-parte
# ---------------------------------------------------------------------------

# Lunch break window boundaries (minutes since midnight).
# The gap between consecutive blocks is tolerated (single use per part)
# when it falls entirely within this window, regardless of its duration.
# This matches the configurable WorkdaySchedule split-shift window used by
# Gate 4 in panel/views.py — no hardcoded duration or minimum-hours check.
#
# Límites de la franja horaria de comida (minutos desde medianoche).
# La laguna entre bloques consecutivos se tolera (uso único por parte)
# cuando cae completamente dentro de esta ventana, sin importar su duración.
# Coincide con la ventana de turno partido del WorkdaySchedule configurable
# usado por Gate 4 en panel/views.py — sin duración fija ni mínimo de horas.
_LUNCH_WINDOW_START_MIN = 13 * 60        # 13:00
_LUNCH_WINDOW_END_MIN   = 15 * 60 + 30  # 15:30


def _is_lunch_gap(gap_start_min: int, gap_end_min: int) -> bool:
    """
    Returns True when the gap falls entirely within the tolerated lunch
    window [_LUNCH_WINDOW_START_MIN, _LUNCH_WINDOW_END_MIN].
    No duration restriction is applied — the window boundaries are the
    only criterion, matching the configurable WorkdaySchedule split-shift
    window used by Gate 4.

    ---

    Devuelve True cuando la laguna cae completamente dentro de la ventana
    de comida tolerada [_LUNCH_WINDOW_START_MIN, _LUNCH_WINDOW_END_MIN].
    No se aplica restricción de duración — los límites de la ventana son
    el único criterio, alineado con la ventana de turno partido del
    WorkdaySchedule configurable usado por Gate 4.
    """
    return (
        gap_start_min >= _LUNCH_WINDOW_START_MIN
        and gap_end_min <= _LUNCH_WINDOW_END_MIN
    )


def validate_intra_gaps(blocks: List[TimeBlock]) -> List[ValidationError]:
    """
    Detects uncovered gaps >= _GAP_THRESHOLD_MINUTES between consecutive blocks
    when sorted by start time. A gap means no block covers the time interval
    [hf_prev, hc_next).

    Regla A — Lunch break exception: a single gap falling entirely within the
    lunch window [_LUNCH_WINDOW_START_MIN, _LUNCH_WINDOW_END_MIN] is tolerated
    without error (single use per part). No duration restriction or minimum
    worked-hours check is applied.

    The operator must fill any other gap with an AUSENCIA JUSTIFICADA or
    AUSENCIA NO JUSTIFICADA block before the part can be saved.

    Returns a list of ValidationError(rule='R3', ...) for each gap found.

    ---

    Detecta lagunas sin cubrir >= _GAP_THRESHOLD_MINUTES entre bloques
    consecutivos ordenados por hora de inicio. Una laguna significa que ningún
    bloque cubre el intervalo [hf_prev, hc_next).

    Regla A — Excepción de comida: una única laguna que cae completamente
    dentro de la ventana de comida [_LUNCH_WINDOW_START_MIN,
    _LUNCH_WINDOW_END_MIN] se tolera sin error (uso único por parte). No se
    aplica restricción de duración ni mínimo de horas trabajadas.

    El operario debe rellenar cualquier otra laguna con un bloque de AUSENCIA
    JUSTIFICADA o AUSENCIA NO JUSTIFICADA antes de poder guardar el parte.

    Devuelve una lista de ValidationError(rule='R3', ...) por cada laguna encontrada.
    """
    errors: List[ValidationError] = []
    if len(blocks) < 2:
        return errors

    sorted_blocks = sorted(blocks, key=lambda b: _to_minutes(b.hc))

    # Track whether the lunch exception has already been consumed for this part.
    # Registrar si la excepción de comida ya fue consumida para este parte.
    lunch_exception_used = False

    for i in range(len(sorted_blocks) - 1):
        current  = sorted_blocks[i]
        nxt      = sorted_blocks[i + 1]
        hf_curr  = _to_minutes(current.hf)
        hc_next  = _to_minutes(nxt.hc)
        gap_min  = hc_next - hf_curr

        if gap_min < _GAP_THRESHOLD_MINUTES:
            continue

        # Regla A — Lunch break exception (single use per part).
        # Regla A — Excepción de pausa de comida (uso único por parte).
        if not lunch_exception_used and _is_lunch_gap(hf_curr, hc_next):
            lunch_exception_used = True
            continue

        gap_hf_str = current.hf.strftime('%H:%M')
        gap_hc_str = nxt.hc.strftime('%H:%M')
        errors.append(ValidationError(
            rule="R3",
            message=(
                f"Laguna horaria sin cubrir de {gap_min} minutos entre "
                f"el bloque {current.idx} (fin {gap_hf_str}) y el bloque "
                f"{nxt.idx} (inicio {gap_hc_str}). Añade un bloque de "
                f"AUSENCIA JUSTIFICADA o AUSENCIA NO JUSTIFICADA para "
                f"cubrir el intervalo {gap_hf_str}–{gap_hc_str}."
            ),
            blocks=[current.idx, nxt.idx],
        ))
    return errors


# ---------------------------------------------------------------------------
# R6 — Odometer reading / Lectura de odómetro
# ---------------------------------------------------------------------------

def validate_odometer(blocks: List[TimeBlock]) -> tuple:
    """
    R6 — Validates odometer_reading for each block whose machine_asset has
    has_odometer=True.

    Blocking errors:
      - odometer_reading is None when has_odometer is True.
      - odometer_reading < machine_asset.mileage (reading lower than last known value).

    Non-blocking warnings:
      - Jump > _ODOMETER_JUMP_THRESHOLD_KM km vs last known mileage.

    Returns (errors, warnings) as two separate lists of ValidationError.

    ---

    R6 — Valida odometer_reading para cada bloque cuyo machine_asset tiene
    has_odometer=True.

    Errores bloqueantes:
      - odometer_reading es None cuando has_odometer es True.
      - odometer_reading < machine_asset.mileage (lectura inferior al último valor conocido).

    Avisos no bloqueantes:
      - Salto > _ODOMETER_JUMP_THRESHOLD_KM km respecto al último kilometraje conocido.

    Devuelve (errors, warnings) como dos listas separadas de ValidationError.
    """
    errors:   List[ValidationError] = []
    warnings: List[ValidationError] = []

    for b in blocks:
        asset = b.machine_asset
        if asset is None or not getattr(asset, "has_odometer", False):
            continue

        if b.odometer_reading is None:
            errors.append(ValidationError(
                rule="R6",
                message=(
                    f"Bloque {b.idx}: la máquina '{asset.code}' requiere lectura "
                    f"de odómetro (km). El campo no puede estar vacío."
                ),
                blocks=[b.idx],
            ))
            continue

        # If first_repair=True skip BD comparison — zero is valid as baseline.
        # Si first_repair=True saltar comparacion BD — cero es valido como base.
        if getattr(asset, "first_repair", False):
            continue

        last_km = getattr(asset, "mileage", None)
        if last_km is not None:
            reading = b.odometer_reading
            if reading < last_km:
                errors.append(ValidationError(
                    rule="R6",
                    message=(
                        f"Bloque {b.idx}: la lectura de odómetro ({reading} km) es "
                        f"inferior al último kilometraje registrado ({last_km} km) "
                        f"para la máquina '{asset.code}'. Verifica la lectura."
                    ),
                    blocks=[b.idx],
                ))
            elif (reading - last_km) > _ODOMETER_JUMP_THRESHOLD_KM:
                warnings.append(ValidationError(
                    rule="R6",
                    message=(
                        f"Bloque {b.idx}: salto de odómetro inusualmente alto "
                        f"({reading - last_km} km) para la máquina '{asset.code}'. "
                        f"Verifica que la lectura sea correcta."
                    ),
                    blocks=[b.idx],
                ))

    return errors, warnings


# ---------------------------------------------------------------------------
# R7 — Engine hours reading / Lectura de horómetro motor
# ---------------------------------------------------------------------------

def validate_engine_hours(blocks: List[TimeBlock]) -> tuple:
    """
    R7 — Validates engine_hours_reading for each block whose machine_asset has
    has_engine_hours=True.

    Blocking errors:
      - engine_hours_reading is None when has_engine_hours is True.
      - engine_hours_reading < machine_asset.hours (reading lower than last known value).

    Non-blocking warnings:
      - Jump > _ENGINE_HOURS_JUMP_THRESHOLD_H hours vs last known hours.

    Returns (errors, warnings) as two separate lists of ValidationError.

    ---

    R7 — Valida engine_hours_reading para cada bloque cuyo machine_asset tiene
    has_engine_hours=True.

    Errores bloqueantes:
      - engine_hours_reading es None cuando has_engine_hours es True.
      - engine_hours_reading < machine_asset.hours (lectura inferior al último valor conocido).

    Avisos no bloqueantes:
      - Salto > _ENGINE_HOURS_JUMP_THRESHOLD_H horas respecto a las horas conocidas.

    Devuelve (errors, warnings) como dos listas separadas de ValidationError.
    """
    errors:   List[ValidationError] = []
    warnings: List[ValidationError] = []

    for b in blocks:
        asset = b.machine_asset
        if asset is None or not getattr(asset, "has_engine_hours", False):
            continue

        if b.engine_hours_reading is None:
            errors.append(ValidationError(
                rule="R7",
                message=(
                    f"Bloque {b.idx}: la máquina '{asset.code}' requiere lectura "
                    f"de horómetro de motor (h). El campo no puede estar vacío."
                ),
                blocks=[b.idx],
            ))
            continue

        # If first_repair=True skip BD comparison — zero is valid as baseline.
        # Si first_repair=True saltar comparacion BD — cero es valido como base.
        if getattr(asset, "first_repair", False):
            continue

        last_h = getattr(asset, "hours", None)
        if last_h is not None:
            reading = b.engine_hours_reading
            if reading < last_h:
                errors.append(ValidationError(
                    rule="R7",
                    message=(
                        f"Bloque {b.idx}: la lectura de horómetro motor ({reading} h) es "
                        f"inferior a las últimas horas registradas ({last_h} h) "
                        f"para la máquina '{asset.code}'. Verifica la lectura."
                    ),
                    blocks=[b.idx],
                ))
            elif (reading - last_h) > _ENGINE_HOURS_JUMP_THRESHOLD_H:
                warnings.append(ValidationError(
                    rule="R7",
                    message=(
                        f"Bloque {b.idx}: salto de horómetro motor inusualmente alto "
                        f"({reading - last_h} h) para la máquina '{asset.code}'. "
                        f"Verifica que la lectura sea correcta."
                    ),
                    blocks=[b.idx],
                ))

    return errors, warnings


# ---------------------------------------------------------------------------
# R8 — Crane hours reading / Lectura de horómetro grúa
# ---------------------------------------------------------------------------

def validate_crane_hours(blocks: List[TimeBlock]) -> tuple:
    """
    R8 — Validates crane_hours_reading for each block whose machine_asset has
    has_crane_hours=True.

    Blocking errors:
      - crane_hours_reading is None when has_crane_hours is True.

    No threshold contrast is applied (no reference value stored in DB for crane hours).

    Returns (errors, warnings) as two separate lists of ValidationError.
    warnings is always an empty list for R8.

    ---

    R8 — Valida crane_hours_reading para cada bloque cuyo machine_asset tiene
    has_crane_hours=True.

    Errores bloqueantes:
      - crane_hours_reading es None cuando has_crane_hours es True.

    No se aplica contraste de umbral (no hay valor de referencia en BD para horas de grúa).

    Devuelve (errors, warnings) como dos listas separadas de ValidationError.
    warnings es siempre una lista vacía para R8.
    """
    errors:   List[ValidationError] = []
    warnings: List[ValidationError] = []

    for b in blocks:
        asset = b.machine_asset
        if asset is None or not getattr(asset, "has_crane_hours", False):
            continue

        if b.crane_hours_reading is None:
            errors.append(ValidationError(
                rule="R8",
                message=(
                    f"Bloque {b.idx}: la máquina '{asset.code}' requiere lectura "
                    f"de horómetro de grúa (h). El campo no puede estar vacío."
                ),
                blocks=[b.idx],
            ))

    return errors, warnings


# ---------------------------------------------------------------------------
# R4 / R5 — Inter-part overlap / Solapamiento inter-parte
# ---------------------------------------------------------------------------

def validate_inter_overlap(
    company_user,
    work_date,
    blocks: List[TimeBlock],
    exclude_work_order_pk: Optional[int] = None,
) -> InterPartResult:
    """
    Checks whether the given blocks overlap with any existing WorkOrder for the
    same operator (company_user) and work_date already persisted in the database.

    The exclude_work_order_pk parameter allows excluding the WorkOrder being
    edited (used when re-validating after an edit).

    Returns an InterPartResult. If has_overlap is False, the part is considered
    complementary (R5) and is accepted silently.

    ---

    Comprueba si los bloques dados solapan con algún WorkOrder existente para
    el mismo operario (company_user) y work_date ya persistido en la base de datos.

    El parámetro exclude_work_order_pk permite excluir el WorkOrder que se está
    editando (usado al re-validar tras una edición).

    Devuelve un InterPartResult. Si has_overlap es False, el parte se considera
    complementario (R5) y se acepta silenciosamente.
    """
    from work_order_processor.models import WorkOrder, WorkOrderEntry

    existing_qs = (
        WorkOrder.objects
        .filter(uploaded_by=company_user, entries__work_date=work_date).distinct()
        .prefetch_related("entries__lines")
    )
    if exclude_work_order_pk is not None:
        existing_qs = existing_qs.exclude(pk=exclude_work_order_pk)

    conflicting_ids:   List[int] = []
    conflicting_dates: List[str] = []

    # Build list of (hc_min, hf_min) for the new submission.
    # Construir lista de (hc_min, hf_min) para el nuevo envío.
    new_intervals = [
        (_to_minutes(b.hc), _to_minutes(b.hf))
        for b in blocks
    ]

    for wo in existing_qs:
        # Times are stored in WorkOrderEntryLine (hc/hf), not in WorkOrderEntry.
        # Los tiempos se almacenan en WorkOrderEntryLine (hc/hf), no en WorkOrderEntry.
        for entry in wo.entries.all():
            for line in entry.lines.all():
                if not line.hc or not line.hf:
                    continue
                hc_ex = _to_minutes(line.hc)
                hf_ex = _to_minutes(line.hf)
                for hc_new, hf_new in new_intervals:
                    # Half-open interval overlap: [hc_a, hf_a) ∩ [hc_b, hf_b) ≠ ∅
                    # iff hc_a < hf_b and hc_b < hf_a.
                    if hc_new < hf_ex and hc_ex < hf_new:
                        if wo.pk not in conflicting_ids:
                            work_date = entry.work_date
                            conflicting_ids.append(wo.pk)
                            conflicting_dates.append(
                                work_date.strftime("%d/%m/%Y")
                                if work_date else "—"
                            )
                        break

    return InterPartResult(
        has_overlap=bool(conflicting_ids),
        conflicting_ids=conflicting_ids,
        conflicting_dates=conflicting_dates,
    )


# ---------------------------------------------------------------------------
# Public facade
# Fachada pública
# ---------------------------------------------------------------------------

def run_intra_part_validation(blocks: List[TimeBlock]) -> IntraPartResult:
    """
    Runs all intra-part validation rules (R2, R1, R3, R6, R7, R8) in priority
    order and returns an IntraPartResult.

    R2 is checked first because an invalid HF/HC pair makes R1 and R3
    results unreliable. R6, R7, R8 are meter-reading rules independent of
    time structure and are always evaluated regardless of R1/R2/R3 outcome.

    ---

    Ejecuta todas las reglas de validación intra-parte (R2, R1, R3, R6, R7, R8)
    en orden de prioridad y devuelve un IntraPartResult.

    R2 se comprueba primero porque un par HC/HF inválido hace que los resultados
    de R1 y R3 sean poco fiables. R6, R7, R8 son reglas de lecturas de contadores
    independientes de la estructura temporal y se evalúan siempre con independencia
    del resultado de R1/R2/R3.
    """
    errors:   List[ValidationError] = []
    warnings: List[ValidationError] = []

    # R2 first — unreliable intervals must be caught before overlap/gap checks.
    # R2 primero — los intervalos inválidos deben detectarse antes de las
    # comprobaciones de solapamiento/laguna.
    errors.extend(validate_hf_after_hc(blocks))

    # Only proceed to R1 and R3 if all intervals are structurally valid.
    # Solo continuar con R1 y R3 si todos los intervalos son estructuralmente válidos.
    if not errors:
        errors.extend(validate_intra_overlap(blocks))
        errors.extend(validate_intra_gaps(blocks))

    # R6, R7, R8 — meter readings: always evaluated, independent of time rules.
    # R6, R7, R8 — lecturas de contadores: siempre evaluadas, independientes de reglas temporales.
    r6_errors, r6_warnings = validate_odometer(blocks)
    r7_errors, r7_warnings = validate_engine_hours(blocks)
    r8_errors, r8_warnings = validate_crane_hours(blocks)

    errors.extend(r6_errors)
    errors.extend(r7_errors)
    errors.extend(r8_errors)
    warnings.extend(r6_warnings)
    warnings.extend(r7_warnings)
    warnings.extend(r8_warnings)

    return IntraPartResult(ok=not errors, errors=errors, warnings=warnings)


def parse_blocks_from_post(post_data, num_entradas: int, entry_lines_data: list = None) -> List[TimeBlock]:
    """
    Extracts TimeBlock instances from a Django POST QueryDict.
    Silently skips blocks where hc or hf cannot be parsed — the server-side
    gate in the view handles missing/malformed time fields independently.

    When entry_lines_data is provided (list of dicts produced by
    _parse_entry_lines_from_post), each TimeBlock is enriched with the
    resolved machine_asset and the meter reading values (odometer_reading,
    engine_hours_reading, crane_hours_reading) so that R6/R7/R8 can operate.

    ---

    Extrae instancias TimeBlock de un QueryDict POST de Django.
    Omite silenciosamente los bloques donde hc o hf no pueden parsearse —
    la barrera server-side de la vista gestiona los campos de hora
    ausentes/malformados de forma independiente.

    Cuando se proporciona entry_lines_data (lista de dicts producida por
    _parse_entry_lines_from_post), cada TimeBlock se enriquece con el
    machine_asset resuelto y los valores de lectura de contadores
    (odometer_reading, engine_hours_reading, crane_hours_reading) para que
    R6/R7/R8 puedan operar.
    """
    blocks: List[TimeBlock] = []
    for i in range(1, num_entradas + 1):
        hc = _parse_hhmm(post_data.get(f"entrada_{i}_hc", ""))
        hf = _parse_hhmm(post_data.get(f"entrada_{i}_hf", ""))
        if hc is None or hf is None:
            continue

        machine_asset        = None
        odometer_reading     = None
        engine_hours_reading = None
        crane_hours_reading  = None

        if entry_lines_data is not None and (i - 1) < len(entry_lines_data):
            entry = entry_lines_data[i - 1]
            machine_asset        = entry.get("machine_asset")
            odometer_reading     = entry.get("odometer_reading")
            engine_hours_reading = entry.get("engine_hours_reading")
            crane_hours_reading  = entry.get("crane_hours_reading")

        blocks.append(TimeBlock(
            idx=i,
            hc=hc,
            hf=hf,
            machine_asset=machine_asset,
            odometer_reading=odometer_reading,
            engine_hours_reading=engine_hours_reading,
            crane_hours_reading=crane_hours_reading,
        ))
    return blocks
