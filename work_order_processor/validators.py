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

    ---

    Representa un único bloque de trabajo con hora de inicio (hc) y hora de
    fin (hf). Se usa como unidad de entrada para todas las reglas de validación
    intra-parte.
    """
    idx: int          # 1-based block index — índice de bloque base 1
    hc:  time         # start time — hora de inicio
    hf:  time         # end time   — hora de fin


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
    Result of intra-part validation (R1, R2, R3).

    Fields:
        ok     — True if no blocking errors were found (R1, R2, R3 all clear).
        errors — list of ValidationError instances describing each problem.

    ---

    Resultado de la validación intra-parte (R1, R2, R3).

    Campos:
        ok     — True si no se encontraron errores bloqueantes (R1, R2, R3 sin incidencias).
        errors — lista de instancias ValidationError describiendo cada problema.
    """
    ok:     bool
    errors: List[ValidationError] = field(default_factory=list)


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

def validate_intra_gaps(blocks: List[TimeBlock]) -> List[ValidationError]:
    """
    Detects uncovered gaps >= _GAP_THRESHOLD_MINUTES between consecutive blocks
    when sorted by start time. A gap means no block covers the time interval
    [hf_prev, hc_next).

    The operator must fill each gap with an AUSENCIA JUSTIFICADA or AUSENCIA
    NO JUSTIFICADA block before the part can be saved.

    Returns a list of ValidationError(rule='R3', ...) for each gap found.

    ---

    Detecta lagunas sin cubrir >= _GAP_THRESHOLD_MINUTES entre bloques
    consecutivos ordenados por hora de inicio. Una laguna significa que ningún
    bloque cubre el intervalo [hf_prev, hc_next).

    El operario debe rellenar cada laguna con un bloque de AUSENCIA JUSTIFICADA
    o AUSENCIA NO JUSTIFICADA antes de poder guardar el parte.

    Devuelve una lista de ValidationError(rule='R3', ...) por cada laguna encontrada.
    """
    errors: List[ValidationError] = []
    if len(blocks) < 2:
        return errors

    sorted_blocks = sorted(blocks, key=lambda b: _to_minutes(b.hc))

    for i in range(len(sorted_blocks) - 1):
        current  = sorted_blocks[i]
        nxt      = sorted_blocks[i + 1]
        hf_curr  = _to_minutes(current.hf)
        hc_next  = _to_minutes(nxt.hc)
        gap_min  = hc_next - hf_curr

        if gap_min >= _GAP_THRESHOLD_MINUTES:
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
        .filter(company_user=company_user, work_date=work_date)
        .prefetch_related("entries")
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
        for entry in wo.entries.all():
            if not entry.start_time or not entry.end_time:
                continue
            hc_ex = _to_minutes(entry.start_time)
            hf_ex = _to_minutes(entry.end_time)
            for hc_new, hf_new in new_intervals:
                # Half-open interval overlap: [hc_a, hf_a) ∩ [hc_b, hf_b) ≠ ∅
                # iff hc_a < hf_b and hc_b < hf_a.
                if hc_new < hf_ex and hc_ex < hf_new:
                    if wo.pk not in conflicting_ids:
                        conflicting_ids.append(wo.pk)
                        conflicting_dates.append(
                            wo.work_date.strftime("%d/%m/%Y")
                            if wo.work_date else "—"
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
    Runs all intra-part validation rules (R2, R1, R3) in priority order and
    returns an IntraPartResult.

    R2 is checked first because an invalid HF/HC pair makes R1 and R3
    results unreliable.

    ---

    Ejecuta todas las reglas de validación intra-parte (R2, R1, R3) en orden
    de prioridad y devuelve un IntraPartResult.

    R2 se comprueba primero porque un par HC/HF inválido hace que los resultados
    de R1 y R3 sean poco fiables.
    """
    errors: List[ValidationError] = []

    # R2 first — unreliable intervals must be caught before overlap/gap checks.
    # R2 primero — los intervalos inválidos deben detectarse antes de las
    # comprobaciones de solapamiento/laguna.
    errors.extend(validate_hf_after_hc(blocks))

    # Only proceed to R1 and R3 if all intervals are structurally valid.
    # Solo continuar con R1 y R3 si todos los intervalos son estructuralmente válidos.
    if not errors:
        errors.extend(validate_intra_overlap(blocks))
        errors.extend(validate_intra_gaps(blocks))

    return IntraPartResult(ok=not errors, errors=errors)


def parse_blocks_from_post(post_data, num_entradas: int) -> List[TimeBlock]:
    """
    Extracts TimeBlock instances from a Django POST QueryDict.
    Silently skips blocks where hc or hf cannot be parsed — the server-side
    gate in the view handles missing/malformed time fields independently.

    ---

    Extrae instancias TimeBlock de un QueryDict POST de Django.
    Omite silenciosamente los bloques donde hc o hf no pueden parsearse —
    la barrera server-side de la vista gestiona los campos de hora
    ausentes/malformados de forma independiente.
    """
    blocks: List[TimeBlock] = []
    for i in range(1, num_entradas + 1):
        hc = _parse_hhmm(post_data.get(f"entrada_{i}_hc", ""))
        hf = _parse_hhmm(post_data.get(f"entrada_{i}_hf", ""))
        if hc is not None and hf is not None:
            blocks.append(TimeBlock(idx=i, hc=hc, hf=hf))
    return blocks
