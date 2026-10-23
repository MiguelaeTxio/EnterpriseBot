# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/gasoges_client.py
"""
H30 (S135). Read-only client for the GasoGes API (fuel pump software):
vehicles and fuel supplies between dates.

---

H30 (S135). Cliente de solo lectura de la API de GasoGes (programa del
surtidor): vehículos y suministros entre fechas. Es el enlace con el
surtidor que el punto 1 de S131 dejó para más adelante ("Más adelante
se tomarán del programa del surtidor").

Según la documentación de GasoGes (v1.3, anexo
`DOCS_ATTACHED_2_ANNEX_V30/Documentacion_API_GasoGes_v1.3.pdf`):
- URL `https://api.gasoges.es/v1/...`, autenticación básica HTTP, solo
  GET, fechas `YYYY-MM-DD`.
- Las respuestas son listas JSON sin nombres de campo: el orden de cada
  lista es lo que da el significado. Aquí se convierten a diccionarios
  con nombre por esa posición documentada.
- 400 = parámetros o fechas mal formados; 401 = credenciales; 403 =
  método distinto de GET.

Credenciales en el `.env` del servidor: `GASOGES_API_USER` y
`GASOGES_API_PASSWORD` (nunca en el repositorio).
"""
import os
from datetime import date
from datetime import datetime

import requests

BASE_URL = "https://api.gasoges.es/v1"
DEFAULT_TIMEOUT = 30
SUPPLY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Documented position of each field in the lists returned by the API.
# ---
# Posición documentada de cada campo en las listas que devuelve la API.
VEHICLE_FIELDS = (
    "vehicle_id",
    "plate",
    "name",
    "pin",
    "key",
    "professional_diesel",
    "site_company",
    "group",
    "last_km",
    "average_calculation",
)
# Solo ID y nombre: el PIN y la llave nunca salen del cliente.
# ---
# Only id and name: PIN and key never leave the client.
USER_FIELDS = (
    "user_id",
    "name",
)
SUPPLY_FIELDS = (
    "user_id",
    "vehicle_id",
    "km",
    "litres",
    "price",
    "datetime",
    "pump_serial",
    "tank_id",
    "fuel_id",
)

_ERROR_MESSAGES = {
    400: (
        "GasoGes rechazó la petición (400): parámetros o fechas mal "
        "formados, o fecha de inicio posterior a la de fin."
    ),
    401: (
        "GasoGes rechazó las credenciales (401): revisar "
        "GASOGES_API_USER y GASOGES_API_PASSWORD en el .env."
    ),
    403: (
        "GasoGes denegó la petición (403): la API solo admite GET."
    ),
}


class GasoGesError(Exception):
    """
    Any failure talking to the GasoGes API, with a clear message.

    ---

    Cualquier fallo al hablar con la API de GasoGes, con mensaje claro.
    """


def _to_dict(row, fields):
    """
    Map a positional list to a dict; missing trailing items are None.

    ---

    Convierte una lista posicional en diccionario; los elementos que
    falten al final quedan a None (el ejemplo de suministros del PDF
    trae 7 de los 9 campos de la estructura).
    """
    values = list(row) + [None] * (len(fields) - len(row))
    return dict(zip(fields, values))


def _format_date(value):
    """
    Return a date as `YYYY-MM-DD`, the only format the API accepts.

    ---

    Devuelve una fecha como `YYYY-MM-DD`, el único formato que acepta
    la API.
    """
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


class GasoGesClient:
    """
    Read-only GasoGes API client (basic HTTP auth, GET only).

    ---

    Cliente de solo lectura de la API de GasoGes (autenticación básica
    HTTP, solo GET). Sin credenciales explícitas, las toma del entorno
    (`GASOGES_API_USER`, `GASOGES_API_PASSWORD`).
    """

    def __init__(self, user=None, password=None,
                 timeout=DEFAULT_TIMEOUT, base_url=BASE_URL):
        self.user = user or os.environ.get("GASOGES_API_USER", "")
        self.password = (
            password or os.environ.get("GASOGES_API_PASSWORD", "")
        )
        if not self.user or not self.password:
            raise GasoGesError(
                "Faltan GASOGES_API_USER o GASOGES_API_PASSWORD en el "
                ".env del servidor."
            )
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    def _get(self, path):
        """
        GET a path and return the decoded JSON list.

        ---

        Hace GET a una ruta y devuelve la lista JSON decodificada.
        """
        url = "%s/%s" % (self.base_url, path.lstrip("/"))
        try:
            response = requests.get(
                url,
                auth=(self.user, self.password),
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise GasoGesError(
                "GasoGes no respondió en %s s (%s)." % (self.timeout, url)
            ) from exc
        except requests.RequestException as exc:
            raise GasoGesError(
                "No se pudo conectar con GasoGes (%s): %s"
                % (url, exc.__class__.__name__)
            ) from exc
        if response.status_code in _ERROR_MESSAGES:
            raise GasoGesError(_ERROR_MESSAGES[response.status_code])
        if response.status_code != 200:
            raise GasoGesError(
                "GasoGes devolvió un estado inesperado (%s) en %s."
                % (response.status_code, url)
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise GasoGesError(
                "GasoGes devolvió una respuesta que no es JSON (%s)." % url
            ) from exc
        if not isinstance(data, list):
            raise GasoGesError(
                "GasoGes devolvió JSON que no es una lista (%s): %s"
                % (url, str(data)[:200])
            )
        return data

    def vehicles(self):
        """
        Return every vehicle as a dict keyed by VEHICLE_FIELDS.

        ---

        Devuelve todos los vehículos como diccionarios con las claves de
        VEHICLE_FIELDS.
        """
        return [_to_dict(row, VEHICLE_FIELDS)
                for row in self._get("vehiculos")]

    def users(self):
        """
        Return every user as {user_id, name} (never PIN or key).

        ---

        Devuelve todos los usuarios como {user_id, name}; el PIN y la
        llave se descartan aquí mismo.
        """
        return [_to_dict(row[:2], USER_FIELDS)
                for row in self._get("usuarios")]

    def supplies(self, start, end):
        """
        Return every supply between two dates (both included).

        The `datetime` field is parsed to a naive datetime when it has
        the documented `YYYY-MM-DD hh:mm:ss` format.

        ---

        Devuelve todos los suministros entre dos fechas. El campo
        `datetime` se convierte a datetime (sin zona) cuando trae el
        formato documentado `YYYY-MM-DD hh:mm:ss`.
        """
        path = "suministros/todos/%s/%s" % (
            _format_date(start), _format_date(end))
        rows = []
        for row in self._get(path):
            item = _to_dict(row, SUPPLY_FIELDS)
            raw = item["datetime"]
            if isinstance(raw, str):
                try:
                    item["datetime"] = datetime.strptime(
                        raw, SUPPLY_DATETIME_FORMAT)
                except ValueError:
                    pass
            rows.append(item)
        return rows
