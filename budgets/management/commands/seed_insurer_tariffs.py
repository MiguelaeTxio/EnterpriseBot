# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/seed_insurer_tariffs.py
"""
Management command: seed_insurer_tariffs.
Loads all 2026 insurer tariffs for the ASISTENCIA section into the database.
Data is extracted from the official 2026 tariff documents supplied by the client.
Idempotent: safe to run multiple times. Uses get_or_create / update_or_create
at every level so existing records are updated, not duplicated.
Supports --dry-run flag to preview changes without writing to the database.
---
Comando de gestion: seed_insurer_tariffs.
Carga todas las tarifas 2026 de aseguradoras para la seccion ASISTENCIA en la BD.
Los datos se extraen de los documentos oficiales de tarifa 2026 aportados por el cliente.
Idempotente: seguro para ejecutar multiples veces. Usa get_or_create / update_or_create
en todos los niveles para actualizar registros existentes sin duplicarlos.
Soporta el flag --dry-run para previsualizar cambios sin escribir en la base de datos.
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budgets.models import (
    Insurer,
    InsurerTariff,
    TariffLine,
    VehicleType,
)
from ivr_config.models import Company


# ---------------------------------------------------------------------------
# Tariff data — extracted from 2026 official documents
# Datos de tarifa — extraidos de los documentos oficiales 2026
# ---------------------------------------------------------------------------

# Each entry in TARIFF_DATA defines one insurer with its full tariff.
# Structure:
#   name            : display name in the dropdown
#   code            : unique internal code (no spaces)
#   management_fee  : % gastos de gestion (0 if none)
#   surcharges_cumulative: False = apply only the higher surcharge (standard)
#   notes           : internal notes
#   vehicle_types   : list of {name, sort_order} dicts
#   tariff_lines    : list of {vehicle_type_name|None, concept, unit, price,
#                              km_threshold, min_units, requires_authorization}
#                     vehicle_type_name=None means the line applies to all
#                     vehicle types (surcharges, unlock if universal price)
# ---------------------------------------------------------------------------

VALID_FROM = datetime.date(2026, 1, 1)
YEAR = 2026

TARIFF_DATA = [

    # ── 1. TRANSSORUAL / MONDIAL ─────────────────────────────────────────────
    {
        "name": "Transsorual / Mondial",
        "code": "TRANSSORUAL",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Provincia Malaga. "
            "Localidades: Malaga, Velez Malaga, Marbella, Loja, "
            "Carratraca, V. Cauche, Coin."
        ),
        "vehicle_types": [
            {"name": "De 3.501 Kgs. a 10.000 Kgs. MMA", "sort_order": 1},
            {"name": "De 10.001 Kgs. a 20.000 Kgs. MMA", "sort_order": 2},
            {"name": "De 20.001 Kgs. a 40.000 Kgs. MMA", "sort_order": 3},
            {"name": "Cabeza Tractora", "sort_order": 4},
            {"name": "Autobus", "sort_order": 5},
            {"name": "Remolque", "sort_order": 6},
            {"name": "Vehiculo Taller Movil", "sort_order": 7},
        ],
        "tariff_lines": [
            # Servicio local
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "129.00",
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "161.25",
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "193.50",
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "161.25",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "204.25",
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "193.50",
            },
            {
                "vt": "Vehiculo Taller Movil",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "64.50",
            },
            # Salida
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "129.00",
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.88",
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "193.50",
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.88",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "204.25",
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "174.69",
            },
            {
                "vt": "Vehiculo Taller Movil",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "53.75",
            },
            # Km normal
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.51",
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.77",
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.04",
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.77",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.15",
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.90",
            },
            {
                "vt": "Vehiculo Taller Movil",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "0.86",
            },
            # Km largo recorrido >200 km
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.40",
                "km_threshold": 200,
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.63",
                "km_threshold": 200,
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.90",
                "km_threshold": 200,
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.63",
                "km_threshold": 200,
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.99",
                "km_threshold": 200,
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.77",
                "km_threshold": 200,
            },
            {
                "vt": "Vehiculo Taller Movil",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "0.75",
                "km_threshold": 200,
            },
            # Hora mano de obra mecanico (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WORKER_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "53.75",
            },
            # Desbloqueo (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "53.75",
            },
            # Custodia por dia (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_CUSTODY_DAY,
                "unit": TariffLine.UNIT_PER_DAY,
                "price": "10.75",
            },
            # Recargo NYF 45%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "45",
            },
        ],
    },

    # ── 2. EUROP ASSISTANCE ──────────────────────────────────────────────────
    {
        "name": "Europ Assistance",
        "code": "EUROP",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Localidades: Loja o Moraleda, "
            "Malaga-Marbella-Antequera-Velez Malaga y La Roda."
        ),
        "vehicle_types": [
            {"name": "Veh. Taller", "sort_order": 1},
            {"name": "3500-8000 kg", "sort_order": 2},
            {"name": "8001-18000 kg", "sort_order": 3},
            {"name": "Tres ejes", "sort_order": 4},
            {"name": "Cuatro ejes", "sort_order": 5},
            {"name": "Completo", "sort_order": 6},
            {"name": "Autocares", "sort_order": 7},
            {"name": "Semiremolque", "sort_order": 8},
        ],
        "tariff_lines": [
            # Urbano
            {
                "vt": "Veh. Taller",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "72.63",
            },
            {
                "vt": "3500-8000 kg",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "176.10",
            },
            {
                "vt": "8001-18000 kg",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "211.41",
            },
            {
                "vt": "Tres ejes",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "238.05",
            },
            {
                "vt": "Cuatro ejes",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "251.64",
            },
            {
                "vt": "Completo",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "251.64",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "265.24",
            },
            {
                "vt": "Semiremolque",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "205.26",
            },
            # Salida
            {
                "vt": "Veh. Taller",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "72.63",
            },
            {
                "vt": "3500-8000 kg",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "176.10",
            },
            {
                "vt": "8001-18000 kg",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "211.41",
            },
            {
                "vt": "Tres ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "238.05",
            },
            {
                "vt": "Cuatro ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "251.64",
            },
            {
                "vt": "Completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "251.64",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "265.24",
            },
            {
                "vt": "Semiremolque",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "205.26",
            },
            # Km normal
            {
                "vt": "Veh. Taller",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.11",
            },
            {
                "vt": "3500-8000 kg",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.67",
            },
            {
                "vt": "8001-18000 kg",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.96",
            },
            {
                "vt": "Tres ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.26",
            },
            {
                "vt": "Cuatro ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.40",
            },
            {
                "vt": "Completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.40",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.40",
            },
            {
                "vt": "Semiremolque",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.96",
            },
            # Km largo recorrido >250 km
            {
                "vt": "Veh. Taller",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.11",
                "km_threshold": 250,
            },
            {
                "vt": "3500-8000 kg",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.68",
                "km_threshold": 250,
            },
            {
                "vt": "8001-18000 kg",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.87",
                "km_threshold": 250,
            },
            {
                "vt": "Tres ejes",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.16",
                "km_threshold": 250,
            },
            {
                "vt": "Cuatro ejes",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.28",
                "km_threshold": 250,
            },
            {
                "vt": "Completo",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.28",
                "km_threshold": 250,
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.40",
                "km_threshold": 250,
            },
            {
                "vt": "Semiremolque",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.96",
                "km_threshold": 250,
            },
            # Mano de obra (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WORKER_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "57.20",
            },
            # Hora ayudante (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "57.20",
            },
            # Hora rescate (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "117.50",
            },
            # Recargo NYF 40%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "40",
            },
        ],
    },

    # ── 3. ARAG ──────────────────────────────────────────────────────────────
    {
        "name": "ARAG",
        "code": "ARAG",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa ASISTENCIA 2026. Localidades: Carratraca, Malaga, "
            "Velez Malaga, Villa Nueva de Cauche, Marbella. "
            "Recargo NYF: fines de semana, festivos y laborables 20:00-08:00h. "
            "Horas Trabajo/Espera/Ayudante/Rescate requieren autorizacion "
            "previa de la CENTRAL OPERATIVA DE ASISTENCIA."
        ),
        "vehicle_types": [
            {"name": "Camiones hasta 5.000 kgs", "sort_order": 1},
            {"name": "Camiones hasta 8.000 kgs", "sort_order": 2},
            {"name": "Camiones hasta 18.000 kgs", "sort_order": 3},
            {"name": "Camiones de 3 ejes (18000-26000)", "sort_order": 4},
            {"name": "Camiones de 4 ejes (26000-32000)", "sort_order": 5},
            {"name": "Cabezas tractoras", "sort_order": 6},
            {"name": "Trailer completo", "sort_order": 7},
            {"name": "Autocar microbús", "sort_order": 8},
            {"name": "Autocar", "sort_order": 9},
            {"name": "Furgon Taller", "sort_order": 10},
        ],
        "tariff_lines": [
            # Enganche (salida)
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "121.46",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "183.40",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "208.19",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "232.97",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "195.81",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.62",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.63",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "85.00",
            },
            # Km (precio unico por tipo)
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.50",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.98",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.10",
            },
            # Hora rescate (min 2h) — requiere autorizacion
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "130.12",
                "min_units": "2",
                "requires_authorization": True,
            },
            # Hora trabajo/ayudante/espera — requiere autorizacion
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "45.86",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "45.86",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WORKER_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "45.86",
                "requires_authorization": True,
            },
            # Quitar transmision
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "49.58",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 4. AVINATAN / ASISTENCIA TECNICA EUROPEA ─────────────────────────────
    {
        "name": "Avinatan / Asistencia Tecnica Europea",
        "code": "AVINATAN",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa ASISTENCIA 2026. Localidades: Malaga, Antequera. "
            "Misma tabla de precios que ARAG. "
            "Recargo NYF: fines de semana, festivos y laborables 20:00-08:00h."
        ),
        "vehicle_types": [
            {"name": "Camiones hasta 5.000 kgs", "sort_order": 1},
            {"name": "Camiones hasta 8.000 kgs", "sort_order": 2},
            {"name": "Camiones hasta 18.000 kgs", "sort_order": 3},
            {"name": "Camiones de 3 ejes (18000-26000)", "sort_order": 4},
            {"name": "Camiones de 4 ejes (26000-32000)", "sort_order": 5},
            {"name": "Cabezas tractoras", "sort_order": 6},
            {"name": "Trailer completo", "sort_order": 7},
            {"name": "Autocar microbús", "sort_order": 8},
            {"name": "Autocar", "sort_order": 9},
            {"name": "Furgon Taller", "sort_order": 10},
        ],
        "tariff_lines": [
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "121.46",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "183.40",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "208.19",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "232.97",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "195.81",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.62",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.63",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "85.00",
            },
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.50",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.98",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.10",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "175.00",
                "min_units": "2",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "80.00",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "80.00",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "80.00",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 5. IMA IBERICA ───────────────────────────────────────────────────────
    {
        "name": "IMA Iberica",
        "code": "IMA",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa ASISTENCIA 2026. Localidades: Malaga, Antequera. "
            "Misma tabla de precios que ARAG/Avinatan."
        ),
        "vehicle_types": [
            {"name": "Camiones hasta 5.000 kgs", "sort_order": 1},
            {"name": "Camiones hasta 8.000 kgs", "sort_order": 2},
            {"name": "Camiones hasta 18.000 kgs", "sort_order": 3},
            {"name": "Camiones de 3 ejes (18000-26000)", "sort_order": 4},
            {"name": "Camiones de 4 ejes (26000-32000)", "sort_order": 5},
            {"name": "Cabezas tractoras", "sort_order": 6},
            {"name": "Trailer completo", "sort_order": 7},
            {"name": "Autocar microbús", "sort_order": 8},
            {"name": "Autocar", "sort_order": 9},
            {"name": "Furgon Taller", "sort_order": 10},
        ],
        "tariff_lines": [
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "121.46",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "183.40",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "208.19",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "232.97",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "195.81",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.62",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.63",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "85.00",
            },
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.50",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.98",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.10",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "175.00",
                "min_units": "2",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "80.00",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "80.00",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "80.00",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 6. TREASCA ───────────────────────────────────────────────────────────
    {
        "name": "Treasca",
        "code": "TREASCA",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa ASISTENCIA 2026. Localidades: Malaga, Antequera. "
            "Misma tabla de precios que ARAG/Avinatan/IMA."
        ),
        "vehicle_types": [
            {"name": "Camiones hasta 5.000 kgs", "sort_order": 1},
            {"name": "Camiones hasta 8.000 kgs", "sort_order": 2},
            {"name": "Camiones hasta 18.000 kgs", "sort_order": 3},
            {"name": "Camiones de 3 ejes (18000-26000)", "sort_order": 4},
            {"name": "Camiones de 4 ejes (26000-32000)", "sort_order": 5},
            {"name": "Cabezas tractoras", "sort_order": 6},
            {"name": "Trailer completo", "sort_order": 7},
            {"name": "Autocar microbús", "sort_order": 8},
            {"name": "Autocar", "sort_order": 9},
            {"name": "Furgon Taller", "sort_order": 10},
        ],
        "tariff_lines": [
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "121.46",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "183.40",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "208.19",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "232.97",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "195.81",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.62",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "146.24",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "272.63",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "85.00",
            },
            {
                "vt": "Camiones hasta 5.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.50",
            },
            {
                "vt": "Camiones hasta 8.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Camiones hasta 18.000 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Camiones de 3 ejes (18000-26000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.98",
            },
            {
                "vt": "Camiones de 4 ejes (26000-32000)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "Cabezas tractoras",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.86",
            },
            {
                "vt": "Trailer completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Autocar microbús",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
            },
            {
                "vt": "Autocar",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.10",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "175.00",
                "min_units": "2",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "80.00",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "80.00",
                "requires_authorization": True,
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "80.00",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 7. ASITUR ────────────────────────────────────────────────────────────
    {
        "name": "Asitur",
        "code": "ASITUR",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa GRUA CAMION 2026. "
            "Localidades: Malaga, Velez Malaga, Marbella, Antequera. "
            "Nocturno: 20:00-08:00h. Festivo: sabado a domingo. "
            "NYF y festivo NO acumulables. "
            "Espera por tramos de 30 min, previa autorizacion. "
            "Rescate por tramos de 30 min, previa autorizacion. "
            "Recargo vehiculo cargado 25 porciento."
        ),
        "vehicle_types": [
            {"name": "Camiones hasta 5 TN", "sort_order": 1},
            {"name": "Camiones hasta 8 TN", "sort_order": 2},
            {"name": "Camiones hasta 15 TN", "sort_order": 3},
            {"name": "Camiones hasta 20 TN", "sort_order": 4},
            {"name": "Camiones hasta 26 TN (3 ejes)", "sort_order": 5},
            {"name": "Camiones hasta 36 TN (4 ejes)", "sort_order": 6},
            {"name": "Cabezas Tractoras", "sort_order": 7},
            {"name": "Trailer Completo", "sort_order": 8},
            {"name": "Autocar Microbus", "sort_order": 9},
            {"name": "Autocares", "sort_order": 10},
            {"name": "Autocares 3 Ejes o Articulado", "sort_order": 11},
            {"name": "Coche Taller Industrial", "sort_order": 12},
        ],
        "tariff_lines": [
            {
                "vt": "Camiones hasta 5 TN",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "98.92",
            },
            {
                "vt": "Camiones hasta 8 TN",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "130.38",
            },
            {
                "vt": "Camiones hasta 15 TN",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "149.94",
            },
            {
                "vt": "Camiones hasta 20 TN",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "173.04",
            },
            {
                "vt": "Camiones hasta 26 TN (3 ejes)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "187.41",
            },
            {
                "vt": "Camiones hasta 36 TN (4 ejes)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "217.75",
            },
            {
                "vt": "Cabezas Tractoras",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "162.23",
            },
            {
                "vt": "Trailer Completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "213.91",
            },
            {
                "vt": "Autocar Microbus",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "135.16",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "224.45",
            },
            {
                "vt": "Autocares 3 Ejes o Articulado",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "246.88",
            },
            {
                "vt": "Coche Taller Industrial",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "67.60",
            },
            # Km
            {
                "vt": "Camiones hasta 5 TN",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.29",
            },
            {
                "vt": "Camiones hasta 8 TN",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.46",
            },
            {
                "vt": "Camiones hasta 15 TN",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.63",
            },
            {
                "vt": "Camiones hasta 20 TN",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.78",
            },
            {
                "vt": "Camiones hasta 26 TN (3 ejes)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.93",
            },
            {
                "vt": "Camiones hasta 36 TN (4 ejes)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.18",
            },
            {
                "vt": "Cabezas Tractoras",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.68",
            },
            {
                "vt": "Trailer Completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "Autocar Microbus",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.52",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.22",
            },
            {
                "vt": "Autocares 3 Ejes o Articulado",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.51",
            },
            {
                "vt": "Coche Taller Industrial",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.09",
            },
            # Hora rescate (min rescate 86.52)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "59.48",
                "requires_authorization": True,
            },
            # Hora espera (tramos 30 min, previa autorizacion)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "44.42",
                "requires_authorization": True,
            },
            # Hora ayudante
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "32.63",
                "requires_authorization": True,
            },
            # Desbloqueo frenos/transmision
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "52.20",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo vehiculo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 8. TAI 2026 ──────────────────────────────────────────────────────────
    {
        "name": "TAI 2026",
        "code": "TAI",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa TAI 2026. Gruas Alvarez + Grualdi + Asist. y Gruas Granada. "
            "Localidades: Malaga, Velez Malaga, Antequera, Marbella, Loja, "
            "Carratraca. Recargo NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "Camiones de 3,5T a 5T", "sort_order": 1},
            {"name": "Camiones de 2 ejes", "sort_order": 2},
            {"name": "Camiones de 3 ejes", "sort_order": 3},
            {"name": "Camiones de 4 ejes/Remolques", "sort_order": 4},
            {"name": "Tractora", "sort_order": 5},
            {"name": "Trailer Completo", "sort_order": 6},
            {"name": "Autobus", "sort_order": 7},
            {"name": "Coche taller (todos los tonelajes)", "sort_order": 8},
            {"name": "Rescate Pluma 10 Tn", "sort_order": 9},
            {"name": "Rescate Pluma 30 Tn", "sort_order": 10},
            {"name": "Rescate Pluma 60 Tn", "sort_order": 11},
        ],
        "tariff_lines": [
            {
                "vt": "Camiones de 3,5T a 5T",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "127.95",
            },
            {
                "vt": "Camiones de 2 ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "184.10",
            },
            {
                "vt": "Camiones de 3 ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "202.44",
            },
            {
                "vt": "Camiones de 4 ejes/Remolques",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "218.90",
            },
            {
                "vt": "Tractora",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "184.10",
            },
            {
                "vt": "Trailer Completo",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "252.55",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "252.55",
            },
            {
                "vt": "Coche taller (todos los tonelajes)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "75.75",
            },
            {
                "vt": "Rescate Pluma 10 Tn",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "123.50",
            },
            {
                "vt": "Rescate Pluma 30 Tn",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "184.10",
            },
            {
                "vt": "Rescate Pluma 60 Tn",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "202.44",
            },
            # Km
            {
                "vt": "Camiones de 3,5T a 5T",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.39",
            },
            {
                "vt": "Camiones de 2 ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Camiones de 3 ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "Camiones de 4 ejes/Remolques",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.35",
            },
            {
                "vt": "Tractora",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Trailer Completo",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.52",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.52",
            },
            {
                "vt": "Coche taller (todos los tonelajes)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.15",
            },
            {
                "vt": "Rescate Pluma 10 Tn",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.45",
            },
            {
                "vt": "Rescate Pluma 30 Tn",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Rescate Pluma 60 Tn",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            # Mano de obra (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WORKER_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "62.80",
            },
            # Hora rescate pluma — precio por tipo
            {
                "vt": "Rescate Pluma 10 Tn",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "78.55",
            },
            {
                "vt": "Rescate Pluma 30 Tn",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "95.40",
            },
            {
                "vt": "Rescate Pluma 60 Tn",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "110.00",
            },
            # Desbloqueo/enganche
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "62.80",
            },
            # Hora espera
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "62.80",
            },
            # Hora ayudante
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "62.80",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 9. RACE ──────────────────────────────────────────────────────────────
    {
        "name": "RACE",
        "code": "RACE",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa RACE ASISTENCIA 2026. "
            "Localidades: Malaga, Marbella, Antequera, Loja. "
            "Urbano = 20 km totales. "
            "Recargo cargado 25 porciento. "
            "Hora rescate con remolcador 150 EUR/H (min 3h). "
            "Custodia desde 2o dia 21 EUR/dia. "
            "Hora ayudante 55 EUR. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "Camiones hasta 8000 KG", "sort_order": 1},
            {"name": "Camiones hasta 18000 KG", "sort_order": 2},
            {"name": "Cabezas Tractoras", "sort_order": 3},
            {"name": "Camiones 3 o 4 Ejes", "sort_order": 4},
            {"name": "Camiones + 32000 KG", "sort_order": 5},
            {"name": "Autocares", "sort_order": 6},
            {"name": "Traslado de Semiremolque", "sort_order": 7},
            {"name": "Furgon Taller", "sort_order": 8},
        ],
        "tariff_lines": [
            # Urbano (20km forfait)
            {
                "vt": "Camiones hasta 8000 KG",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "180.00",
            },
            {
                "vt": "Camiones hasta 18000 KG",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "Cabezas Tractoras",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "Camiones 3 o 4 Ejes",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "265.00",
            },
            {
                "vt": "Camiones + 32000 KG",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "280.00",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "280.00",
            },
            {
                "vt": "Traslado de Semiremolque",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "100.00",
            },
            # Salida
            {
                "vt": "Camiones hasta 8000 KG",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "150.00",
            },
            {
                "vt": "Camiones hasta 18000 KG",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "180.00",
            },
            {
                "vt": "Cabezas Tractoras",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "180.00",
            },
            {
                "vt": "Camiones 3 o 4 Ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "240.00",
            },
            {
                "vt": "Camiones + 32000 KG",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "265.00",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "250.00",
            },
            {
                "vt": "Traslado de Semiremolque",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "180.00",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "80.00",
            },
            # Km
            {
                "vt": "Camiones hasta 8000 KG",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.70",
            },
            {
                "vt": "Camiones hasta 18000 KG",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Cabezas Tractoras",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Camiones 3 o 4 Ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.40",
            },
            {
                "vt": "Camiones + 32000 KG",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.65",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.50",
            },
            {
                "vt": "Traslado de Semiremolque",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.20",
            },
            {
                "vt": "Furgon Taller",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.20",
            },
            # Mano de obra 1h (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WORKER_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "55.00",
            },
            # Hora ayudante
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "55.00",
            },
            # Custodia desde 2o dia
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_CUSTODY_DAY,
                "unit": TariffLine.UNIT_PER_DAY,
                "price": "21.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 10. MAPFRE ───────────────────────────────────────────────────────────
    {
        "name": "Mapfre",
        "code": "MAPFRE",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Localidades: Malaga, Fuengirola, Antequera, Loja. "
            "Servicio urbano forfait 177.16 EUR. "
            "Largo recorrido aplica cuando km supera umbral. "
            "Custodia a partir del 3er dia."
        ),
        "vehicle_types": [
            {"name": "De 3.500 kg. Hasta 5.000 kg.", "sort_order": 1},
            {"name": "De 5.001 kg. Hasta 10.000 kg.", "sort_order": 2},
            {"name": "De 10.001 kg. Hasta 15.000 kg.", "sort_order": 3},
            {"name": "De 15.001 kg. Hasta 20.000 kg.", "sort_order": 4},
            {"name": "Mas de 20.001 kg.", "sort_order": 5},
            {"name": "Autocares", "sort_order": 6},
        ],
        "tariff_lines": [
            # Servicio urbano forfait (177.16 EUR plano)
            {
                "vt": "De 3.500 kg. Hasta 5.000 kg.",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "177.16",
            },
            {
                "vt": "De 5.001 kg. Hasta 10.000 kg.",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "177.16",
            },
            {
                "vt": "De 10.001 kg. Hasta 15.000 kg.",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "177.16",
            },
            {
                "vt": "De 15.001 kg. Hasta 20.000 kg.",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "177.16",
            },
            {
                "vt": "Mas de 20.001 kg.",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "177.16",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "177.16",
            },
            # Salida (carretera)
            {
                "vt": "De 3.500 kg. Hasta 5.000 kg.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "99.96",
            },
            {
                "vt": "De 5.001 kg. Hasta 10.000 kg.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "120.95",
            },
            {
                "vt": "De 10.001 kg. Hasta 15.000 kg.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "137.03",
            },
            {
                "vt": "De 15.001 kg. Hasta 20.000 kg.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "160.45",
            },
            {
                "vt": "Mas de 20.001 kg.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "224.98",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "160.46",
            },
            # Km normal
            {
                "vt": "De 3.500 kg. Hasta 5.000 kg.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.21",
            },
            {
                "vt": "De 5.001 kg. Hasta 10.000 kg.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.36",
            },
            {
                "vt": "De 10.001 kg. Hasta 15.000 kg.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.70",
            },
            {
                "vt": "De 15.001 kg. Hasta 20.000 kg.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.08",
            },
            {
                "vt": "Mas de 20.001 kg.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.48",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.05",
            },
            # Km largo recorrido
            {
                "vt": "De 3.500 kg. Hasta 5.000 kg.",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.08",
                "km_threshold": 200,
            },
            {
                "vt": "De 5.001 kg. Hasta 10.000 kg.",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.19",
                "km_threshold": 200,
            },
            {
                "vt": "De 10.001 kg. Hasta 15.000 kg.",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.50",
                "km_threshold": 200,
            },
            {
                "vt": "De 15.001 kg. Hasta 20.000 kg.",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.84",
                "km_threshold": 200,
            },
            {
                "vt": "Mas de 20.001 kg.",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.16",
                "km_threshold": 200,
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.77",
                "km_threshold": 200,
            },
            # Extracciones (min 2h)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "127.38",
                "min_units": "2",
            },
            # Tiempo de espera (1/2 hora)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "15.35",
            },
            # Custodia a partir del 3er dia
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_CUSTODY_DAY,
                "unit": TariffLine.UNIT_PER_DAY,
                "price": "11.82",
            },
            # Hora ayudante
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "36.34",
            },
        ],
    },

    # ── 11. INTER PARTNER / AXA ──────────────────────────────────────────────
    {
        "name": "Inter Partner / AXA",
        "code": "AXA",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa Gran Tonelaje 2026. Localidades: Malaga. "
            "Recargo NYF 45 porciento (20:00-08:00h). "
            "Servicio urbano = dentro del casco urbano (km 0, solo salida). "
            "Servicio carretera = salida + km desde el limite del casco."
        ),
        "vehicle_types": [
            {"name": "De 3.501 Kg hasta 6.000 kg de P.M.A", "sort_order": 1},
            {"name": "De 6.001 Kg hasta 10.000 Kg de P.M.A", "sort_order": 2},
            {"name": "Cabeza tractora", "sort_order": 3},
            {"name": "De 10.001 Kg hasta 15.000 Kg de P.M.A", "sort_order": 4},
            {"name": "De 15.001 Kg hasta 20.000 Kg de P.M.A", "sort_order": 5},
            {"name": "De 20.001 Kg hasta 26.000 Kg de P.M.A", "sort_order": 6},
            {"name": "De 26.001 Kg hasta 35.000 Kg de P.M.A", "sort_order": 7},
            {"name": "De 35.001 Kg hasta 42.000 Kg de P.M.A", "sort_order": 8},
            {"name": "Autocares", "sort_order": 9},
        ],
        "tariff_lines": [
            {
                "vt": "De 3.501 Kg hasta 6.000 kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "107.64",
            },
            {
                "vt": "De 6.001 Kg hasta 10.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.48",
            },
            {
                "vt": "Cabeza tractora",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "160.85",
            },
            {
                "vt": "De 10.001 Kg hasta 15.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "169.87",
            },
            {
                "vt": "De 15.001 Kg hasta 20.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "187.59",
            },
            {
                "vt": "De 20.001 Kg hasta 26.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "214.29",
            },
            {
                "vt": "De 26.001 Kg hasta 35.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "240.88",
            },
            {
                "vt": "De 35.001 Kg hasta 42.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "285.45",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "285.45",
            },
            # Km
            {
                "vt": "De 3.501 Kg hasta 6.000 kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.43",
            },
            {
                "vt": "De 6.001 Kg hasta 10.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.91",
            },
            {
                "vt": "Cabeza tractora",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.01",
            },
            {
                "vt": "De 10.001 Kg hasta 15.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.12",
            },
            {
                "vt": "De 15.001 Kg hasta 20.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.33",
            },
            {
                "vt": "De 20.001 Kg hasta 26.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.59",
            },
            {
                "vt": "De 26.001 Kg hasta 35.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.77",
            },
            {
                "vt": "De 35.001 Kg hasta 42.000 Kg de P.M.A",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.12",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.94",
            },
            # Hora trabajo/espera/desbloqueo (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "59.80",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "59.80",
            },
            # Recargo NYF 45%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "45",
            },
        ],
    },

    # ── 12. SERVIREAC (SVR) ──────────────────────────────────────────────────
    {
        "name": "Servireac (SVR)",
        "code": "SVR",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa REAC ASISTENCIA vigente desde 01/03/2023. "
            "Localidades: Malaga, Antequera. "
            "Horario diurno: lunes-viernes 08:00-20:00h. "
            "Nocturno: 20:00-08:00h. Festivo: fines de semana y festivos nacionales. "
            "NYF y festivo NO acumulables. "
            "Largo recorrido >300 km. "
            "Custodia desde 3er dia 19 EUR/dia."
        ),
        "vehicle_types": [
            {"name": "Coche piloto", "sort_order": 1},
            {"name": "De 3.500 kg a 10.000 kg", "sort_order": 2},
            {"name": "De 10.001 kg a 20.000 kg", "sort_order": 3},
            {"name": "Camiones de 3 ejes", "sort_order": 4},
            {"name": "Camiones de 4 ejes", "sort_order": 5},
            {"name": "REMOLQUE (con nuestra cabeza tractora)", "sort_order": 6},
            {"name": "Cabeza tractora", "sort_order": 7},
            {"name": "Autobus o autocar", "sort_order": 8},
        ],
        "tariff_lines": [
            # Urbano o salida
            {
                "vt": "Coche piloto",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "72.65",
            },
            {
                "vt": "De 3.500 kg a 10.000 kg",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "150.00",
            },
            {
                "vt": "De 10.001 kg a 20.000 kg",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "175.00",
            },
            {
                "vt": "Camiones de 3 ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "190.00",
            },
            {
                "vt": "Camiones de 4 ejes",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "210.00",
            },
            {
                "vt": "REMOLQUE (con nuestra cabeza tractora)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "185.00",
            },
            {
                "vt": "Cabeza tractora",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "185.00",
            },
            {
                "vt": "Autobus o autocar",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "250.00",
            },
            # Km normal
            {
                "vt": "Coche piloto",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.00",
            },
            {
                "vt": "De 3.500 kg a 10.000 kg",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.60",
            },
            {
                "vt": "De 10.001 kg a 20.000 kg",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.85",
            },
            {
                "vt": "Camiones de 3 ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.05",
            },
            {
                "vt": "Camiones de 4 ejes",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "REMOLQUE (con nuestra cabeza tractora)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Cabeza tractora",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "Autobus o autocar",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.50",
            },
            # Km largo recorrido >300 km
            {
                "vt": "Coche piloto",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "0.93",
                "km_threshold": 300,
            },
            {
                "vt": "De 3.500 kg a 10.000 kg",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.53",
                "km_threshold": 300,
            },
            {
                "vt": "De 10.001 kg a 20.000 kg",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.78",
                "km_threshold": 300,
            },
            {
                "vt": "Camiones de 3 ejes",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.98",
                "km_threshold": 300,
            },
            {
                "vt": "Camiones de 4 ejes",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.18",
                "km_threshold": 300,
            },
            {
                "vt": "REMOLQUE (con nuestra cabeza tractora)",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.88",
                "km_threshold": 300,
            },
            {
                "vt": "Cabeza tractora",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.88",
                "km_threshold": 300,
            },
            {
                "vt": "Autobus o autocar",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.42",
                "km_threshold": 300,
            },
            # Rescate 1 hora
            {
                "vt": "De 3.500 kg a 10.000 kg",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "120.00",
            },
            {
                "vt": "De 10.001 kg a 20.000 kg",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "136.72",
            },
            {
                "vt": "Camiones de 3 ejes",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "153.25",
            },
            {
                "vt": "Camiones de 4 ejes",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "155.71",
            },
            {
                "vt": "Cabeza tractora",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "136.72",
            },
            {
                "vt": "Autobus o autocar",
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "167.19",
            },
            # Custodia desde 3er dia
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_CUSTODY_DAY,
                "unit": TariffLine.UNIT_PER_DAY,
                "price": "19.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 13. GRUAS ALVAREZ (tarifa propia) ────────────────────────────────────
    {
        "name": "Gruas Alvarez (tarifa propia)",
        "code": "ALVAREZ",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifas 2023 vehiculos industriales. Localidades: Malaga. "
            "Precios antes de IVA o IGIC. "
            "Recargo vehiculo cargado 25 porciento. NYF 40 porciento. "
            "Hora rescate minimo 2h."
        ),
        "vehicle_types": [
            {"name": "De 3.501 Kgs. a 10.000 Kgs. MMA", "sort_order": 1},
            {"name": "De 10.001 Kgs. a 20.000 Kgs. MMA", "sort_order": 2},
            {"name": "De 20.001 Kgs. a 40.000 Kgs. MMA", "sort_order": 3},
            {"name": "Cabeza Tractora", "sort_order": 4},
            {"name": "Autobus", "sort_order": 5},
            {"name": "Remolque", "sort_order": 6},
            {"name": "Vehiculo Taller Movil / Coche Piloto", "sort_order": 7},
            {"name": "Grua Movil", "sort_order": 8},
        ],
        "tariff_lines": [
            # Servicio local
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "135.00",
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.00",
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "200.00",
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.00",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "200.00",
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "200.00",
            },
            {
                "vt": "Vehiculo Taller Movil / Coche Piloto",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "78.00",
            },
            {
                "vt": "Grua Movil",
                "concept": TariffLine.CONCEPT_SERVICE_LOCAL,
                "unit": TariffLine.UNIT_FIXED,
                "price": "350.00",
            },
            # Salida
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "135.00",
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.00",
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "200.00",
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.00",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "200.00",
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "200.00",
            },
            {
                "vt": "Vehiculo Taller Movil / Coche Piloto",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "70.00",
            },
            {
                "vt": "Grua Movil",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "350.00",
            },
            # Km normal
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.54",
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.75",
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.09",
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.75",
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.10",
            },
            {
                "vt": "Vehiculo Taller Movil / Coche Piloto",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "0.90",
            },
            {
                "vt": "Grua Movil",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.50",
            },
            # Km largo recorrido >200 km
            {
                "vt": "De 3.501 Kgs. a 10.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.43",
                "km_threshold": 200,
            },
            {
                "vt": "De 10.001 Kgs. a 20.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
                "km_threshold": 200,
            },
            {
                "vt": "De 20.001 Kgs. a 40.000 Kgs. MMA",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.94",
                "km_threshold": 200,
            },
            {
                "vt": "Cabeza Tractora",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.62",
                "km_threshold": 200,
            },
            {
                "vt": "Autobus",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.09",
                "km_threshold": 200,
            },
            {
                "vt": "Remolque",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
                "km_threshold": 200,
            },
            {
                "vt": "Vehiculo Taller Movil / Coche Piloto",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "0.83",
                "km_threshold": 200,
            },
            {
                "vt": "Grua Movil",
                "concept": TariffLine.CONCEPT_KM_LONG,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.50",
                "km_threshold": 200,
            },
            # Hora rescate (min 2h)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_RESCUE_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "145.00",
                "min_units": "2",
            },
            # Hora mano de obra mecanico
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WORKER_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "55.00",
            },
            # Desbloqueo
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "55.00",
            },
            # Custodia por dia
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_CUSTODY_DAY,
                "unit": TariffLine.UNIT_PER_DAY,
                "price": "10.00",
            },
            # Recargo NYF 40%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "40",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 14. MAN TRUCK ────────────────────────────────────────────────────────
    {
        "name": "MAN Truck",
        "code": "MAN",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Aplicar 15 porciento descuento sobre estas tarifas. "
            "Nocturno desde las 18:00h hasta las 08:00h del lunes. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "Desbloqueo/enganche/hora de espera a partir de las 18:00h: "
            "precio a convenir. "
            "Recargo vehiculo cargado 25 porciento. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "3.500KG - 8.000KG P.M.A.", "sort_order": 1},
            {"name": "8.001KG - 14.000KG P.M.A.", "sort_order": 2},
            {"name": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)", "sort_order": 3},
            {"name": "DE 18.001 A 26.000KG. P.M.A.", "sort_order": 4},
            {"name": "DE 26.001 A 38.000KG. P.M.A.", "sort_order": 5},
            {"name": "AUTOBUS", "sort_order": 6},
            {"name": "TRAILER COMPLETO", "sort_order": 7},
            {"name": "COCHE TALLER", "sort_order": 8},
        ],
        "tariff_lines": [
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "190.00",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "290.00",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "315.00",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "335.00",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "335.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "90.00",
            },
            # Km
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.90",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.58",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.93",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.15",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.35",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.35",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.30",
            },
            # Desbloqueo/MO (precio unico)
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "78.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 15. PETIT FORESTIER ──────────────────────────────────────────────────
    {
        "name": "Petit Forestier",
        "code": "PETIT",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Nocturno desde las 20:00h hasta las 08:00h del lunes. "
            "Festivo desde las 20:00h del viernes hasta las 08:00h del lunes. "
            "Ayudante 52.50 EUR. NYF 50 porciento. Cargado 25 porciento."
        ),
        "vehicle_types": [
            {"name": "3.500KG - 8.000KG P.M.A.", "sort_order": 1},
            {"name": "8.001KG - 14.000KG P.M.A.", "sort_order": 2},
            {"name": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)", "sort_order": 3},
            {"name": "DE 18.001 A 26.000KG. P.M.A.", "sort_order": 4},
            {"name": "DE 26.001 A 38.000KG. P.M.A.", "sort_order": 5},
            {"name": "COCHE TALLER", "sort_order": 6},
        ],
        "tariff_lines": [
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "155.00",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "176.00",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "205.00",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "215.00",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "225.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "75.00",
            },
            # Km
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.55",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.76",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.05",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.15",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.10",
            },
            # Hora espera
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "60.00",
            },
            # Hora ayudante
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "52.50",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 16. COVEI ────────────────────────────────────────────────────────────
    {
        "name": "COVEI",
        "code": "COVEI",
        "management_fee": 5,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Gastos de gestion 5 porciento. "
            "Nocturno desde las 18:00h hasta las 08:00h. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "Cargado 25 porciento. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "DE 3.500 A 5.000 KGS PMA", "sort_order": 1},
            {"name": "DE 5.001 A 8.000 KGS PMA", "sort_order": 2},
            {"name": "DE 8.001 A 10.000 KGS PMA", "sort_order": 3},
            {"name": "DE 10.001 A 18.000 KGS PMA (Tractora)", "sort_order": 4},
            {"name": "DE 18.001 A 26.000 KGS PMA", "sort_order": 5},
            {"name": "DE 26.001 A 32.000 KGS PMA", "sort_order": 6},
            {"name": "VEHICULO TRAILER VACIO", "sort_order": 7},
            {"name": "MICROBUS", "sort_order": 8},
            {"name": "AUTOCARES", "sort_order": 9},
            {"name": "AUTOCARES 3 EJES O ARTICULADO", "sort_order": 10},
        ],
        "tariff_lines": [
            {
                "vt": "DE 3.500 A 5.000 KGS PMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "149.00",
            },
            {
                "vt": "DE 5.001 A 8.000 KGS PMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "175.50",
            },
            {
                "vt": "DE 8.001 A 10.000 KGS PMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "180.00",
            },
            {
                "vt": "DE 10.001 A 18.000 KGS PMA (Tractora)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "258.00",
            },
            {
                "vt": "DE 18.001 A 26.000 KGS PMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "275.00",
            },
            {
                "vt": "DE 26.001 A 32.000 KGS PMA",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "311.50",
            },
            {
                "vt": "VEHICULO TRAILER VACIO",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "311.50",
            },
            {
                "vt": "MICROBUS",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "258.50",
            },
            {
                "vt": "AUTOCARES",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "277.00",
            },
            {
                "vt": "AUTOCARES 3 EJES O ARTICULADO",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "300.00",
            },
            # Km
            {
                "vt": "DE 3.500 A 5.000 KGS PMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.49",
            },
            {
                "vt": "DE 5.001 A 8.000 KGS PMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.85",
            },
            {
                "vt": "DE 8.001 A 10.000 KGS PMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.87",
            },
            {
                "vt": "DE 10.001 A 18.000 KGS PMA (Tractora)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.44",
            },
            {
                "vt": "DE 18.001 A 26.000 KGS PMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.75",
            },
            {
                "vt": "DE 26.001 A 32.000 KGS PMA",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.11",
            },
            {
                "vt": "VEHICULO TRAILER VACIO",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.11",
            },
            {
                "vt": "MICROBUS",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.68",
            },
            {
                "vt": "AUTOCARES",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.77",
            },
            {
                "vt": "AUTOCARES 3 EJES O ARTICULADO",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.00",
            },
            # Desbloqueo
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "65.00",
            },
            # Hora espera
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "55.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 17. TVA (ALSA) ───────────────────────────────────────────────────────
    {
        "name": "TVA (ALSA)",
        "code": "TVA",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Nocturno desde las 18:00h hasta las 08:00h. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "Cargado 25 porciento. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "3.500KG - 8.000KG P.M.A.", "sort_order": 1},
            {"name": "8.001KG - 14.000KG P.M.A.", "sort_order": 2},
            {"name": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)", "sort_order": 3},
            {"name": "DE 18.001 A 26.000KG. P.M.A.", "sort_order": 4},
            {"name": "DE 26.001 A 38.000KG. P.M.A.", "sort_order": 5},
            {"name": "AUTOBUS", "sort_order": 6},
            {"name": "TRAILER COMPLETO", "sort_order": 7},
            {"name": "COCHE TALLER", "sort_order": 8},
        ],
        "tariff_lines": [
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "168.00",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "190.00",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "255.00",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "275.00",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "290.00",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "350.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "90.00",
            },
            # Km
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.68",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.60",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.75",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.90",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.50",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.15",
            },
            # Hora espera
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "68.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 18. SCORA Y SELLTRUCK (FORD) ─────────────────────────────────────────
    {
        "name": "Scora y Selltruck (Ford)",
        "code": "SCORA",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Misma tabla que TVA/ALSA. "
            "Nocturno desde las 18:00h hasta las 08:00h. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "Cargado 25 porciento. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "3.500KG - 8.000KG P.M.A.", "sort_order": 1},
            {"name": "8.001KG - 14.000KG P.M.A.", "sort_order": 2},
            {"name": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)", "sort_order": 3},
            {"name": "DE 18.001 A 26.000KG. P.M.A.", "sort_order": 4},
            {"name": "DE 26.001 A 38.000KG. P.M.A.", "sort_order": 5},
            {"name": "AUTOBUS", "sort_order": 6},
            {"name": "TRAILER COMPLETO", "sort_order": 7},
            {"name": "COCHE TALLER", "sort_order": 8},
        ],
        "tariff_lines": [
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "168.00",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "190.00",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "255.00",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "275.00",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "290.00",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "350.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "90.00",
            },
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.68",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.60",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.75",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.90",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.50",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.15",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "68.00",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 19. VEINLUC ──────────────────────────────────────────────────────────
    {
        "name": "Veinluc",
        "code": "VEINLUC",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Misma tabla que TVA/ALSA/Scora. "
            "Nocturno desde las 18:00h hasta las 08:00h. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "Cargado 25 porciento. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "3.500KG - 8.000KG P.M.A.", "sort_order": 1},
            {"name": "8.001KG - 14.000KG P.M.A.", "sort_order": 2},
            {"name": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)", "sort_order": 3},
            {"name": "DE 18.001 A 26.000KG. P.M.A.", "sort_order": 4},
            {"name": "DE 26.001 A 38.000KG. P.M.A.", "sort_order": 5},
            {"name": "AUTOBUS", "sort_order": 6},
            {"name": "TRAILER COMPLETO", "sort_order": 7},
            {"name": "COCHE TALLER", "sort_order": 8},
        ],
        "tariff_lines": [
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "168.00",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "190.00",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "255.00",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "275.00",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "290.00",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "350.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "90.00",
            },
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.68",
            },
            {
                "vt": "8.001KG - 14.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "14.001 A 18.000KG P.M.A. (Cabeza Tract.)",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "DE 18.001 A 26.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.60",
            },
            {
                "vt": "DE 26.001 A 38.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.75",
            },
            {
                "vt": "AUTOBUS",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.90",
            },
            {
                "vt": "TRAILER COMPLETO",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.50",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.15",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_WAIT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "68.00",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 20. UTE ENVASES LIGEROS ──────────────────────────────────────────────
    {
        "name": "UTE Envases Ligeros",
        "code": "UTE_ENVASES",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Bases: Malaga y Antequera. "
            "Nocturno desde las 18:00h hasta las 08:00h. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "Cargado 25 porciento. NYF 50 porciento. Ayudante 50 EUR."
        ),
        "vehicle_types": [
            {"name": "3.500KG - 8.000KG P.M.A.", "sort_order": 1},
            {"name": "18.001KG - 26.000KG P.M.A.", "sort_order": 2},
            {"name": "DE 26.001 A 36.000KG. P.M.A.", "sort_order": 3},
            {"name": "COCHE TALLER", "sort_order": 4},
        ],
        "tariff_lines": [
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "175.00",
            },
            {
                "vt": "18.001KG - 26.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "265.00",
            },
            {
                "vt": "DE 26.001 A 36.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "295.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "90.00",
            },
            {
                "vt": "3.500KG - 8.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.75",
            },
            {
                "vt": "18.001KG - 26.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.65",
            },
            {
                "vt": "DE 26.001 A 36.000KG. P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.95",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.10",
            },
            # Desbloqueo
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "65.00",
            },
            # Ayudante
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_ASSISTANT_HOUR,
                "unit": TariffLine.UNIT_PER_HOUR,
                "price": "50.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },

    # ── 21. PROSEGUR ─────────────────────────────────────────────────────────
    {
        "name": "Prosegur",
        "code": "PROSEGUR",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. "
            "Nocturno desde las 18:00h hasta las 08:00h. "
            "Festivo desde las 18:00h del viernes hasta las 08:00h del lunes. "
            "NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "6.500KG P.M.A.", "sort_order": 1},
            {"name": "9.000KG P.M.A.", "sort_order": 2},
            {"name": "COCHE TALLER", "sort_order": 3},
        ],
        "tariff_lines": [
            {
                "vt": "6.500KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "170.00",
            },
            {
                "vt": "9.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "185.00",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "90.00",
            },
            {
                "vt": "6.500KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.80",
            },
            {
                "vt": "9.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.95",
            },
            {
                "vt": "COCHE TALLER",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.12",
            },
            # Desbloqueo
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "60.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
        ],
    },

    # ── 22. F.C.C. ───────────────────────────────────────────────────────────
    {
        "name": "F.C.C.",
        "code": "FCC",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. "
            "Nocturno/festivo desde las 18:00h hasta las 08:00h, "
            "dias festivos y fines de semana. NYF 50 porciento. "
            "Desbloqueo frenos/enganche/hora espera a partir de las 18:00h: "
            "65 EUR. Cargado 15 porciento."
        ),
        "vehicle_types": [
            {"name": "500KG - 1.500KG P.M.A.", "sort_order": 1},
            {"name": "1.501KG - 4.000KG P.M.A.", "sort_order": 2},
            {"name": "4.001KG - 8.500KG P.M.A.", "sort_order": 3},
            {"name": "8.501KG - 18.000KG P.M.A.", "sort_order": 4},
            {"name": "18.001KG - 26.000KG P.M.A.", "sort_order": 5},
        ],
        "tariff_lines": [
            {
                "vt": "500KG - 1.500KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "135.00",
            },
            {
                "vt": "1.501KG - 4.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "160.00",
            },
            {
                "vt": "4.001KG - 8.500KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "190.00",
            },
            {
                "vt": "8.501KG - 18.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "235.00",
            },
            {
                "vt": "18.001KG - 26.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "285.00",
            },
            {
                "vt": "500KG - 1.500KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.35",
            },
            {
                "vt": "1.501KG - 4.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.60",
            },
            {
                "vt": "4.001KG - 8.500KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.90",
            },
            {
                "vt": "8.501KG - 18.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.60",
            },
            {
                "vt": "18.001KG - 26.000KG P.M.A.",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.90",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 15%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "15",
            },
        ],
    },

    # ── 23. ANGAL TRUCK ──────────────────────────────────────────────────────
    {
        "name": "Angal Truck",
        "code": "ANGAL",
        "management_fee": 0,
        "surcharges_cumulative": False,
        "notes": (
            "Tarifa 2026. Horario diurno 08:00-18:00h. "
            "Nocturno desde las 18:00h hasta las 08:00h del sabado. "
            "Festivos en fines de semana +50 porciento. "
            "Cargado 25 porciento. NYF 50 porciento."
        ),
        "vehicle_types": [
            {"name": "Furgon hasta 3500 kgs", "sort_order": 1},
            {"name": "3501 hasta 5000", "sort_order": 2},
            {"name": "5001 hasta 8000", "sort_order": 3},
            {"name": "8001 hasta 10000", "sort_order": 4},
            {"name": "10001 hasta 14000", "sort_order": 5},
            {"name": "14001 hasta 18000", "sort_order": 6},
            {"name": "18001 hasta 26000", "sort_order": 7},
            {"name": "26001 hasta 38000", "sort_order": 8},
            {"name": "Autocares", "sort_order": 9},
            {"name": "Autocares tres ejes articulados", "sort_order": 10},
            {"name": "Remolques y bateeas trailer", "sort_order": 11},
        ],
        "tariff_lines": [
            {
                "vt": "Furgon hasta 3500 kgs",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "75.00",
            },
            {
                "vt": "3501 hasta 5000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "105.00",
            },
            {
                "vt": "5001 hasta 8000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "135.00",
            },
            {
                "vt": "8001 hasta 10000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "145.00",
            },
            {
                "vt": "10001 hasta 14000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "166.00",
            },
            {
                "vt": "14001 hasta 18000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            {
                "vt": "18001 hasta 26000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "250.00",
            },
            {
                "vt": "26001 hasta 38000",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "285.00",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "295.00",
            },
            {
                "vt": "Autocares tres ejes articulados",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "350.00",
            },
            {
                "vt": "Remolques y bateeas trailer",
                "concept": TariffLine.CONCEPT_DEPARTURE,
                "unit": TariffLine.UNIT_FIXED,
                "price": "220.00",
            },
            # Km
            {
                "vt": "Furgon hasta 3500 kgs",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.15",
            },
            {
                "vt": "3501 hasta 5000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.25",
            },
            {
                "vt": "5001 hasta 8000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.45",
            },
            {
                "vt": "8001 hasta 10000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.55",
            },
            {
                "vt": "10001 hasta 14000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "1.76",
            },
            {
                "vt": "14001 hasta 18000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            {
                "vt": "18001 hasta 26000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.50",
            },
            {
                "vt": "26001 hasta 38000",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.85",
            },
            {
                "vt": "Autocares",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.95",
            },
            {
                "vt": "Autocares tres ejes articulados",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "3.50",
            },
            {
                "vt": "Remolques y bateeas trailer",
                "concept": TariffLine.CONCEPT_KM_NORMAL,
                "unit": TariffLine.UNIT_PER_KM,
                "price": "2.25",
            },
            # Desbloqueo transmision
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_UNLOCK,
                "unit": TariffLine.UNIT_FIXED,
                "price": "65.00",
            },
            # Recargo NYF 50%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_NYF_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "50",
            },
            # Recargo cargado 25%
            {
                "vt": None,
                "concept": TariffLine.CONCEPT_LOADED_PERCENT,
                "unit": TariffLine.UNIT_PERCENT,
                "price": "25",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Command implementation
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    """
    Management command: seed_insurer_tariffs.
    Loads 2026 ASISTENCIA insurer tariffs into the database.
    Idempotent — safe to run multiple times.
    ---
    Comando de gestion: seed_insurer_tariffs.
    Carga las tarifas 2026 de aseguradoras ASISTENCIA en la base de datos.
    Idempotente — seguro para ejecutar multiples veces.
    """

    help = (
        "Carga todas las tarifas 2026 de aseguradoras para la seccion "
        "ASISTENCIA. Idempotente: usa get_or_create y update_or_create "
        "en todos los niveles. Usa --dry-run para previsualizar sin escribir."
    )

    def add_arguments(self, parser):
        """
        Register --dry-run flag.
        ---
        Registra el flag --dry-run.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Ejecuta el comando sin escribir nada en la base de datos. "
                "Muestra un resumen de lo que se crearia o actualizaria."
            ),
        )

    def handle(self, *args, **options):
        """
        Main entry point. Resolves the company, then iterates TARIFF_DATA
        loading each insurer, vehicle types, tariff and tariff lines.
        ---
        Punto de entrada principal. Resuelve la empresa, luego itera TARIFF_DATA
        cargando cada aseguradora, tipos de vehiculo, tarifa y lineas de tarifa.
        """
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "# MODO DRY-RUN — no se escribira nada en la base de datos."
                )
            )

        # Resolve company — first active company in the system.
        # Resolver empresa — primera empresa activa del sistema.
        company = Company.objects.filter(is_active=True).first()
        if not company:
            raise CommandError(
                "No existe ninguna Company activa. Crea una primero."
            )

        self.stdout.write(
            f"# Empresa: {company.name}"
        )
        self.stdout.write(
            f"# Total aseguradoras a procesar: {len(TARIFF_DATA)}"
        )

        total_insurers_created = 0
        total_insurers_updated = 0
        total_vt_created = 0
        total_lines_created = 0
        total_lines_updated = 0

        try:
            with transaction.atomic():
                for entry in TARIFF_DATA:
                    (
                        ins_created,
                        vt_created,
                        lines_created,
                        lines_updated,
                    ) = self._process_insurer(
                        company, entry, dry_run
                    )
                    if ins_created:
                        total_insurers_created += 1
                    else:
                        total_insurers_updated += 1
                    total_vt_created += vt_created
                    total_lines_created += lines_created
                    total_lines_updated += lines_updated

                if dry_run:
                    # Roll back everything in dry-run mode.
                    # Revertir todo en modo dry-run.
                    raise _DryRunRollback()

        except _DryRunRollback:
            self.stdout.write(
                self.style.WARNING(
                    "# Dry-run completado — transaccion revertida. "
                    "Ningun dato fue escrito."
                )
            )
        except Exception as exc:
            raise CommandError(f"Error durante la carga: {exc}") from exc

        self.stdout.write("")
        self.stdout.write("# --- RESUMEN ---")
        self.stdout.write(
            f"# Aseguradoras creadas:     {total_insurers_created}"
        )
        self.stdout.write(
            f"# Aseguradoras actualizadas: {total_insurers_updated}"
        )
        self.stdout.write(
            f"# Tipos de vehiculo creados: {total_vt_created}"
        )
        self.stdout.write(
            f"# Lineas de tarifa creadas:  {total_lines_created}"
        )
        self.stdout.write(
            f"# Lineas de tarifa actualizadas: {total_lines_updated}"
        )
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS("# Carga completada correctamente.")
            )

    def _process_insurer(self, company, entry, dry_run):
        """
        Process a single insurer entry from TARIFF_DATA.
        Returns (ins_created, vt_created, lines_created, lines_updated).
        ---
        Procesa una entrada de aseguradora de TARIFF_DATA.
        Devuelve (ins_created, vt_created, lines_created, lines_updated).
        """
        # 1. Insurer
        insurer, ins_created = Insurer.objects.get_or_create(
            company=company,
            code=entry["code"],
            defaults={
                "name": entry["name"],
                "management_fee_percent": entry["management_fee"],
                "surcharges_are_cumulative": entry[
                    "surcharges_cumulative"
                ],
                "notes": entry["notes"],
                "is_active": True,
            },
        )
        if not ins_created:
            # Update mutable fields if insurer already exists.
            # Actualizar campos mutables si la aseguradora ya existe.
            insurer.name = entry["name"]
            insurer.management_fee_percent = entry["management_fee"]
            insurer.surcharges_are_cumulative = entry[
                "surcharges_cumulative"
            ]
            insurer.notes = entry["notes"]
            insurer.save()

        action = "CREADA" if ins_created else "ACTUALIZADA"
        self.stdout.write(
            f"  [{action}] {insurer.name} ({insurer.code})"
        )

        # 2. Vehicle types
        vt_map = {}
        vt_created_count = 0
        for vt_data in entry["vehicle_types"]:
            vt, vt_new = VehicleType.objects.get_or_create(
                insurer=insurer,
                name=vt_data["name"],
                defaults={
                    "sort_order": vt_data["sort_order"],
                    "is_active": True,
                },
            )
            if not vt_new:
                vt.sort_order = vt_data["sort_order"]
                vt.save()
            else:
                vt_created_count += 1
            vt_map[vt_data["name"]] = vt

        # 3. Active tariff (get or create for this year)
        tariff, _ = InsurerTariff.objects.get_or_create(
            insurer=insurer,
            year=YEAR,
            valid_to__isnull=True,
            defaults={"valid_from": VALID_FROM},
        )

        # 4. Tariff lines
        lines_created = 0
        lines_updated = 0
        for line_data in entry["tariff_lines"]:
            vt_name = line_data.get("vt")
            vt_obj = vt_map[vt_name] if vt_name else None

            defaults = {
                "unit": line_data["unit"],
                "price": line_data["price"],
                "km_threshold": line_data.get("km_threshold"),
                "min_units": line_data.get("min_units"),
                "requires_authorization": line_data.get(
                    "requires_authorization", False
                ),
            }

            _, line_created = TariffLine.objects.update_or_create(
                tariff=tariff,
                vehicle_type=vt_obj,
                concept=line_data["concept"],
                defaults=defaults,
            )
            if line_created:
                lines_created += 1
            else:
                lines_updated += 1

        self.stdout.write(
            f"    Tipos vehiculo: {vt_created_count} creados | "
            f"Lineas: {lines_created} creadas, {lines_updated} actualizadas"
        )

        return ins_created, vt_created_count, lines_created, lines_updated


class _DryRunRollback(Exception):
    """
    Internal sentinel exception used to roll back the dry-run transaction.
    ---
    Excepcion centinela interna usada para revertir la transaccion dry-run.
    """
