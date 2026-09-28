# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/employment_period_service.py
"""
H30 (S122). Employment periods of a person, from their Social Security
registrations (ALTA), each paired with its employment contract.

---

H30 (S122). Periodos de contratación de una persona, a partir de sus
altas en la Seguridad Social, cada uno emparejado con su contrato.
Miguel Ángel: "en esta empresa tengo dos contratos, tres contratos,
pero solamente está apareciendo el primero. ¿Tenemos alguna forma
para detectar esto?".

Reglas (decididas por Miguel Ángel en S122):
- Cada alta con fecha abre un periodo. Dos altas a menos de
  `MATCH_WINDOW_DAYS` días son la misma (copias escaneadas dos veces).
- Cada periodo exige un contrato fechado a ±`MATCH_WINDOW_DAYS` días
  de alguna de sus altas ("más menos 15 días y aseguramos").
- El periodo termina con la primera baja (Seguridad Social) fechada
  después de su inicio y antes del periodo siguiente.
- Un alta sin fecha no se puede emparejar: se cuenta aparte.

Funciones puras sobre listas de `DocumentIndexEntry` (sin consultas),
para que las usen igual la ficha, los avisos y los informes.
"""
from dataclasses import dataclass, field
from datetime import timedelta

MATCH_WINDOW_DAYS = 15
ALTA_CODE = "ALTA"
CONTRACT_CODE = "CONTRATO"
BAJA_CODE = "BAJA_PERSONAL"
PERIOD_CODES = (ALTA_CODE, CONTRACT_CODE, BAJA_CODE)


@dataclass
class EmploymentPeriod:
    """
    One employment period (one or more ALTA copies of the same date).

    ---

    Un periodo de contratación: sus altas (una o varias copias), los
    contratos emparejados y la baja que lo cierra, si la hay.
    """

    start_date: object
    altas: list = field(default_factory=list)
    contracts: list = field(default_factory=list)
    end_baja: object = None

    @property
    def has_contract(self):
        """
        True if at least one contract is paired with this period.

        ---

        True si hay al menos un contrato emparejado.
        """
        return bool(self.contracts)

    @property
    def end_date(self):
        """
        Date of the closing BAJA, or None if still open.

        ---

        Fecha de la baja que lo cierra, o None si sigue abierto.
        """
        return self.end_baja.issue_date if self.end_baja else None


def _within(date_a, date_b):
    """
    True if two dates are within the matching window.

    ---

    True si dos fechas están a ±MATCH_WINDOW_DAYS días.
    """
    return abs((date_a - date_b).days) <= MATCH_WINDOW_DAYS


def build_periods(altas, contracts, bajas):
    """
    Employment periods from ALTA/CONTRATO/BAJA entries of one person.

    ---

    Construye los periodos de una persona a partir de sus altas,
    contratos y bajas (listas de DocumentIndexEntry, solo las de esa
    persona). Devuelve (periodos ordenados, altas_sin_fecha).
    """
    dated = sorted(
        (entry for entry in altas if entry.issue_date),
        key=lambda entry: (entry.issue_date, entry.pk),
    )
    undated = [entry for entry in altas if not entry.issue_date]

    periods = []
    for alta in dated:
        if periods and _within(alta.issue_date, periods[-1].start_date):
            periods[-1].altas.append(alta)
            continue
        periods.append(EmploymentPeriod(alta.issue_date, altas=[alta]))

    dated_contracts = [entry for entry in contracts if entry.issue_date]
    for period in periods:
        alta_dates = [alta.issue_date for alta in period.altas]
        period.contracts = sorted(
            (
                contract for contract in dated_contracts
                if any(_within(contract.issue_date, d) for d in alta_dates)
            ),
            key=lambda entry: (entry.issue_date, entry.pk),
        )

    dated_bajas = sorted(
        (entry for entry in bajas if entry.issue_date),
        key=lambda entry: (entry.issue_date, entry.pk),
    )
    for index, period in enumerate(periods):
        next_start = (
            periods[index + 1].start_date if index + 1 < len(periods)
            else None
        )
        for baja in dated_bajas:
            if baja.issue_date < period.start_date:
                continue
            if next_start is not None and baja.issue_date >= next_start:
                break
            period.end_baja = baja
            break
    return periods, undated


def unmatched_contracts(periods, contracts):
    """
    Contracts not paired with any period (dated or not).

    ---

    Contratos que no se emparejan con ningún periodo (sin fecha, o con
    fecha lejos de toda alta): se enseñan aparte, nunca se pierden.
    """
    paired = {
        contract.pk for period in periods for contract in period.contracts
    }
    return [contract for contract in contracts if contract.pk not in paired]


def missing_contract_window(period):
    """
    (from, to) dates where the missing contract should be dated.

    ---

    Rango de fechas donde debería estar fechado el contrato que falta
    (para el texto del aviso y para buscarlo a mano).
    """
    first = period.altas[0].issue_date
    last = period.altas[-1].issue_date
    window = timedelta(days=MATCH_WINDOW_DAYS)
    return first - window, last + window
