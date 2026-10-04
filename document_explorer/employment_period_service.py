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
- Cada periodo exige un contrato fechado de `CONTRACT_DAYS_BEFORE` días
  antes a `CONTRACT_DAYS_AFTER` días después de alguna de sus altas
  (S127, Miguel Ángel: el contrato se firma antes del alta; con ±15
  quedaban fuera contratos reales a 16, 24 y 32 días).
- El periodo termina con la primera baja (Seguridad Social) fechada
  después de su inicio y antes del periodo siguiente.
- Un alta sin fecha no se puede emparejar: se cuenta aparte.
- Las prórrogas y modificaciones de contrato (PRORROGA_CONTRATO,
  MODIFICACION_CONTRATO, S122) nunca cuentan como contrato del alta:
  se colocan en el periodo en cuyo tramo empiezan (desde su alta hasta
  la siguiente), para verlas dentro de su contrato.

Funciones puras sobre listas de `DocumentIndexEntry` (sin consultas),
para que las usen igual la ficha, los avisos y los informes.
"""
from dataclasses import dataclass, field
from datetime import timedelta

MATCH_WINDOW_DAYS = 15
# S127 (aprobado por Miguel Ángel): ventana asimétrica contrato-alta.
CONTRACT_DAYS_BEFORE = 45
CONTRACT_DAYS_AFTER = MATCH_WINDOW_DAYS
ALTA_CODE = "ALTA"
CONTRACT_CODE = "CONTRATO"
BAJA_CODE = "BAJA_PERSONAL"
EXTENSION_CODE = "PRORROGA_CONTRATO"
MODIFICATION_CODE = "MODIFICACION_CONTRATO"
# Subtipos de contrato que se ven dentro de su periodo y nunca cuentan
# como contrato del alta (prórrogas y modificaciones, S122).
CONTRACT_SUBTYPE_CODES = (EXTENSION_CODE, MODIFICATION_CODE)
# S127 (Miguel Ángel, opción a): subrogación y conversión a indefinido
# no son el contrato, pero demuestran que lo hubo y CUBREN el alta, con
# su propia fecha (efectos / celebración del contrato original).
SUBROGATION_CODE = "SUBROGACION_CONTRATO"
CONVERSION_CODE = "CONVERSION_CONTRATO"
CONTRACT_COVER_CODES = (CONTRACT_CODE, SUBROGATION_CODE, CONVERSION_CODE)
PERIOD_CODES = (
    (ALTA_CODE, BAJA_CODE) + CONTRACT_COVER_CODES + CONTRACT_SUBTYPE_CODES
)


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
    extensions: list = field(default_factory=list)
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


def contract_covers(contract_date, alta_date):
    """
    True if a contract dated `contract_date` covers an alta.

    ---

    True si un contrato con esa fecha cubre el alta: firmado hasta
    `CONTRACT_DAYS_BEFORE` días antes o `CONTRACT_DAYS_AFTER` después.
    """
    gap = (contract_date - alta_date).days
    return -CONTRACT_DAYS_BEFORE <= gap <= CONTRACT_DAYS_AFTER


def build_periods(altas, contracts, bajas, extensions=()):
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
                if any(contract_covers(contract.issue_date, d)
                       for d in alta_dates)
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
    dated_extensions = sorted(
        (entry for entry in extensions if entry.issue_date),
        key=lambda entry: (entry.issue_date, entry.pk),
    )
    for extension in dated_extensions:
        home = None
        for period in periods:
            if period.start_date <= extension.issue_date:
                home = period
        if home is not None:
            home.extensions.append(extension)
    return periods, undated


def unplaced_extensions(periods, extensions):
    """
    Extensions not placed in any period (undated or before every alta).

    ---

    Prórrogas que no caen en ningún periodo (sin fecha, o anteriores a
    toda alta registrada): se enseñan aparte, nunca se pierden.
    """
    placed = {
        extension.pk for period in periods
        for extension in period.extensions
    }
    return [entry for entry in extensions if entry.pk not in placed]


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
    return (
        first - timedelta(days=CONTRACT_DAYS_BEFORE),
        last + timedelta(days=CONTRACT_DAYS_AFTER),
    )
