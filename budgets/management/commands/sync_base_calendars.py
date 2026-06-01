# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/sync_base_calendars.py
"""
Management command: sync_base_calendars.
Fetches public holiday calendars for all active Base records from the
calendariosnacionales.com public JSON API and persists the holiday dates
in Base.labor_calendar as a JSON list of ISO date strings.

Supports:
  --year YYYY     : target year (default: current year + 1 if after October,
                    otherwise current year).
  --base-id ID    : sync only the base with the given primary key.
  --dry-run       : fetch and print without writing to the database.
  --force         : re-sync bases whose calendar_synced_at is already set.

Idempotent: safe to run multiple times. Existing calendars are overwritten.
Requires: requests (already in requirements.in).
---
Comando de gestion: sync_base_calendars.
Obtiene los calendarios de festivos publicos para todos los registros Base
activos desde la API JSON publica de calendariosnacionales.com y persiste
las fechas de festivos en Base.labor_calendar como lista JSON de fechas ISO.

Soporta:
  --year YYYY     : anio objetivo (por defecto: anio actual + 1 si es despues
                    de octubre, si no el anio actual).
  --base-id ID    : sincroniza solo la base con el pk indicado.
  --dry-run       : obtiene e imprime sin escribir en la base de datos.
  --force         : re-sincroniza bases cuyo calendar_synced_at ya esta establecido.

Idempotente: seguro para ejecutar multiples veces. Los calendarios existentes
se sobreescriben.
Requiere: requests (ya en requirements.in).
"""

import json
import datetime

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from budgets.models import Base


# ---------------------------------------------------------------------------
# API constants
# API de calendariosnacionales.com — sin registro, sin API key, sin limites.
# ---------------------------------------------------------------------------

BASE_URL = "https://calendariosnacionales.com/es/v1/{year}/localidades/{ccaa}/{provincia}/{municipio}.json"

# Mapping of known Andalusian municipalities to their API path components.
# Only municipalities used by active bases need to be covered.
# Add more entries as new municipalities are added to bases.
# Mapeo de municipios conocidos de Andalucia a sus componentes de ruta API.
# Solo es necesario cubrir los municipios usados por bases activas.
# Anadir mas entradas a medida que se incorporen nuevos municipios a las bases.
MUNICIPALITY_MAP: dict[str, dict] = {
    # Format: "Nombre municipio en Base.municipality" -> {ccaa, provincia, municipio}
    # The API uses lowercase slugs without accents for ccaa, provincia and municipio.
    "sevilla":              {"ccaa": "and", "provincia": "sevilla",  "municipio": "sevilla"},
    "granada":              {"ccaa": "and", "provincia": "granada",  "municipio": "granada"},
    "malaga":               {"ccaa": "and", "provincia": "malaga",   "municipio": "malaga"},
    "cordoba":              {"ccaa": "and", "provincia": "cordoba",  "municipio": "cordoba"},
    "cadiz":                {"ccaa": "and", "provincia": "cadiz",    "municipio": "cadiz"},
    "huelva":               {"ccaa": "and", "provincia": "huelva",   "municipio": "huelva"},
    "almeria":              {"ccaa": "and", "provincia": "almeria",  "municipio": "almeria"},
    "jaen":                 {"ccaa": "and", "provincia": "jaen",     "municipio": "jaen"},
    "jerez de la frontera": {"ccaa": "and", "provincia": "cadiz",    "municipio": "jerez-de-la-frontera"},
    "algeciras":            {"ccaa": "and", "provincia": "cadiz",    "municipio": "algeciras"},
    "marbella":             {"ccaa": "and", "provincia": "malaga",   "municipio": "marbella"},
    "dos hermanas":         {"ccaa": "and", "provincia": "sevilla",  "municipio": "dos-hermanas"},
    "alcala de guadaira":   {"ccaa": "and", "provincia": "sevilla",  "municipio": "alcala-de-guadaira"},
    "linares":              {"ccaa": "and", "provincia": "jaen",     "municipio": "linares"},
    "el ejido":             {"ccaa": "and", "provincia": "almeria",  "municipio": "el-ejido"},
    # Municipios incorporados en S004 (2026-06-01)
    # Municipalities added in S004 (2026-06-01)
    "antequera":            {"ccaa": "and", "provincia": "malaga",   "municipio": "antequera"},
    "carratraca":           {"ccaa": "and", "provincia": "malaga",   "municipio": "carratraca"},
    "coin":                 {"ccaa": "and", "provincia": "malaga",   "municipio": "coin"},
    "fuengirola":           {"ccaa": "and", "provincia": "malaga",   "municipio": "fuengirola"},
    "loja":                 {"ccaa": "and", "provincia": "granada",  "municipio": "loja"},
    "moraleda de zafayona": {"ccaa": "and", "provincia": "granada",  "municipio": "moraleda-de-zafayona"},
    "velez-malaga":         {"ccaa": "and", "provincia": "malaga",   "municipio": "velez-malaga"},
    # Villanueva del Cauche es pedania de Antequera — se usa el municipio cabecera.
    # Villanueva del Cauche is a hamlet of Antequera — uses the parent municipality.
    "villanueva del cauche": {"ccaa": "and", "provincia": "malaga",  "municipio": "antequera"},
    # La Roda de Andalucia no existe en la API — se usa Estepa como cabecera comarcal.
    # La Roda de Andalucia not in API — Estepa used as comarca capital (same national/regional holidays).
    "la roda de andalucia": {"ccaa": "and", "provincia": "sevilla",  "municipio": "estepa"},
}


def _resolve_municipality(municipality: str) -> dict | None:
    """
    Resolve a municipality name to its API path components using MUNICIPALITY_MAP.
    Lookup is case-insensitive and strips leading/trailing whitespace.
    Returns None if the municipality is not found in the map.
    ---
    Resuelve un nombre de municipio a sus componentes de ruta API usando MUNICIPALITY_MAP.
    La busqueda es insensible a mayusculas y elimina espacios al inicio/final.
    Devuelve None si el municipio no se encuentra en el mapa.
    """
    return MUNICIPALITY_MAP.get(municipality.strip().lower())


def _fetch_holidays(municipality: str, year: int) -> list[str]:
    """
    Fetch the public holiday list for the given municipality and year from the
    calendariosnacionales.com API. Returns a sorted list of ISO date strings.
    Raises requests.HTTPError on non-2xx responses.
    Raises KeyError if the municipality is not in MUNICIPALITY_MAP.
    ---
    Obtiene la lista de festivos publicos para el municipio y anio dados desde
    la API de calendariosnacionales.com. Devuelve una lista ordenada de fechas ISO.
    Lanza requests.HTTPError en respuestas no-2xx.
    Lanza KeyError si el municipio no esta en MUNICIPALITY_MAP.
    """
    coords = _resolve_municipality(municipality)
    if coords is None:
        raise KeyError(
            f"Municipio '{municipality}' no encontrado en MUNICIPALITY_MAP. "
            f"Aniadelo a sync_base_calendars.MUNICIPALITY_MAP antes de continuar."
        )

    url = BASE_URL.format(year=year, **coords)
    # Send browser-like headers to avoid 403 from PythonAnywhere IP.
    # Enviar cabeceras de navegador para evitar el 403 desde PythonAnywhere.
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Referer': 'https://calendariosnacionales.com/',
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    data = response.json()
    # The API returns a nested object. The consolidated holiday list
    # (national + regional + local, deduplicated by date) is in
    # data['holidays']['calendar']. Dates may appear more than once
    # (e.g. duplicate local entries from different sources) so we
    # deduplicate using a set before sorting.
    # La API devuelve un objeto anidado. La lista consolidada de festivos
    # (nacionales + autonomicos + locales, sin duplicados por fecha) esta en
    # data['holidays']['calendar']. Las fechas pueden aparecer mas de una vez
    # (festivos locales de distintas fuentes) por lo que deduplicamos con set.
    calendar_items = data.get("holidays", {}).get("calendar", [])
    holidays = sorted({
        item["date"]
        for item in calendar_items
        if "date" in item
    })
    return holidays


class Command(BaseCommand):
    """
    Sync public holiday calendars for all active Base records.
    ---
    Sincroniza los calendarios de festivos publicos para todos los registros Base activos.
    """

    help = (
        "Sincroniza el calendario laboral de las bases activas desde "
        "la API publica de calendariosnacionales.com."
    )

    def add_arguments(self, parser):
        """
        Register command-line arguments.
        ---
        Registra los argumentos de linea de comandos.
        """
        current_year = datetime.date.today().year
        # Default target year: next year if we are in Q4, otherwise current year.
        # Anio objetivo por defecto: siguiente si estamos en Q4, si no el actual.
        default_year = current_year + 1 if datetime.date.today().month >= 10 else current_year
        parser.add_argument(
            "--year",
            type=int,
            default=default_year,
            help=f"Anio objetivo del calendario (por defecto: {default_year}).",
        )
        parser.add_argument(
            "--base-id",
            type=int,
            default=None,
            dest="base_id",
            help="Sincroniza solo la base con el pk indicado.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            dest="dry_run",
            help="Obtiene e imprime sin escribir en la base de datos.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-sincroniza bases cuyo calendario ya habia sido sincronizado.",
        )

    def handle(self, *args, **options):
        """
        Main command handler. Iterates active bases and syncs their calendars.
        ---
        Manejador principal del comando. Itera las bases activas y sincroniza sus calendarios.
        """
        year = options["year"]
        base_id = options["base_id"]
        dry_run = options["dry_run"]
        force = options["force"]

        # Build queryset.
        # Construir queryset.
        qs = Base.objects.filter(is_active=True)
        if base_id is not None:
            qs = qs.filter(pk=base_id)
        if not force:
            qs = qs.filter(calendar_synced_at__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(
                "# No hay bases pendientes de sincronizacion. "
                "Usa --force para re-sincronizar todas."
            )
            return

        self.stdout.write(
            f"# Sincronizando {total} base(s) para el anio {year}..."
        )
        if dry_run:
            self.stdout.write("# MODO DRY-RUN: no se escribira en la base de datos.")

        ok_count = 0
        error_count = 0

        for base in qs.select_related("company"):
            try:
                holidays = _fetch_holidays(base.municipality, year)
                self.stdout.write(
                    f"# [{base.pk}] {base} — {len(holidays)} festivos obtenidos."
                )
                if not dry_run:
                    base.labor_calendar = json.dumps(holidays, ensure_ascii=False)
                    base.calendar_synced_at = timezone.now()
                    base.save(update_fields=["labor_calendar", "calendar_synced_at"])
                ok_count += 1
            except KeyError as exc:
                self.stderr.write(f"# [{base.pk}] {base} — ERROR: {exc}")
                error_count += 1
            except requests.HTTPError as exc:
                self.stderr.write(
                    f"# [{base.pk}] {base} — ERROR HTTP {exc.response.status_code}: {exc}"
                )
                error_count += 1
            except Exception as exc:
                self.stderr.write(f"# [{base.pk}] {base} — ERROR inesperado: {exc}")
                error_count += 1

        self.stdout.write(
            f"# Completado: {ok_count} OK, {error_count} errores."
        )
        if error_count > 0:
            raise CommandError(
                f"{error_count} base(s) no pudieron sincronizarse. "
                f"Revisa los errores anteriores y anade los municipios "
                f"faltantes a MUNICIPALITY_MAP en sync_base_calendars.py."
            )
