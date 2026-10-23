# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/test_gasoges_client.py
"""
H30 (S135). Tests of the GasoGes client with responses copied from the
format of the API documentation (v1.3).

---

H30 (S135). Pruebas del cliente de GasoGes con respuestas copiadas del
formato de la documentación de la API (v1.3): los dos endpoints y una
respuesta 401. Sin red: `requests.get` simulado.
"""
import unittest
from datetime import date
from datetime import datetime
from unittest import mock

import requests

from fleet.gasoges_client import GasoGesClient
from fleet.gasoges_client import GasoGesError

# Example of `GET /v1/vehiculos` in the documentation.
# ---
# Ejemplo de `GET /v1/vehiculos` de la documentación.
VEHICLES_EXAMPLE = [
    [1, "1111-ABC", "VEHICULO DE PRUEBA", "1111", "NINGUNA", "SI",
     1, 0, 0, 100],
]

# Example of `GET /v1/suministros/todos/2024-01-01/2024-05-14` (7 of the
# 9 documented fields) plus one row with the 9 fields.
# ---
# Ejemplo de suministros de la documentación (7 de los 9 campos de la
# estructura) y una fila con los 9 campos.
SUPPLIES_EXAMPLE = [
    [1, 1, 50000, 100, 1.5, "2024-05-10 07:14:00", 111111],
    [1, 1, 51000, 30, 1.1, "2024-05-11 08:00:00", 222111, 2, 3],
]


def _response(status, payload=None):
    """
    Build a fake `requests` response.

    ---

    Construye una respuesta de `requests` simulada.
    """
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = payload
    return resp


class GasoGesClientTests(unittest.TestCase):
    """
    GasoGes client against the documented response format.

    ---

    Cliente de GasoGes contra el formato de respuesta documentado.
    """

    def setUp(self):
        self.client = GasoGesClient(user="u", password="p")

    @mock.patch("fleet.gasoges_client.requests.get")
    def test_vehicles(self, get):
        get.return_value = _response(200, VEHICLES_EXAMPLE)
        vehicles = self.client.vehicles()
        self.assertEqual(len(vehicles), 1)
        vehicle = vehicles[0]
        self.assertEqual(vehicle["vehicle_id"], 1)
        self.assertEqual(vehicle["plate"], "1111-ABC")
        self.assertEqual(vehicle["name"], "VEHICULO DE PRUEBA")
        self.assertEqual(vehicle["last_km"], 0)
        self.assertEqual(vehicle["average_calculation"], 100)
        get.assert_called_once_with(
            "https://api.gasoges.es/v1/vehiculos",
            auth=("u", "p"), timeout=30)

    @mock.patch("fleet.gasoges_client.requests.get")
    def test_supplies(self, get):
        get.return_value = _response(200, SUPPLIES_EXAMPLE)
        supplies = self.client.supplies(
            date(2024, 1, 1), date(2024, 5, 14))
        self.assertEqual(len(supplies), 2)
        first, second = supplies
        self.assertEqual(first["vehicle_id"], 1)
        self.assertEqual(first["km"], 50000)
        self.assertEqual(first["litres"], 100)
        self.assertEqual(
            first["datetime"], datetime(2024, 5, 10, 7, 14))
        self.assertEqual(first["pump_serial"], 111111)
        self.assertIsNone(first["tank_id"])
        self.assertIsNone(first["fuel_id"])
        self.assertEqual(second["tank_id"], 2)
        self.assertEqual(second["fuel_id"], 3)
        get.assert_called_once_with(
            "https://api.gasoges.es/v1/suministros/todos/"
            "2024-01-01/2024-05-14",
            auth=("u", "p"), timeout=30)

    @mock.patch("fleet.gasoges_client.requests.get")
    def test_users_drop_pin_and_key(self, get):
        get.return_value = _response(
            200, [[7, "PEREZ PEREZ JUAN", "1234", "ABCD"]])
        users = self.client.users()
        self.assertEqual(users, [{"user_id": 7,
                                  "name": "PEREZ PEREZ JUAN"}])

    @mock.patch("fleet.gasoges_client.requests.get")
    def test_unauthorized(self, get):
        get.return_value = _response(401)
        with self.assertRaises(GasoGesError) as ctx:
            self.client.vehicles()
        self.assertIn("401", str(ctx.exception))
        self.assertIn("GASOGES_API_USER", str(ctx.exception))

    @mock.patch("fleet.gasoges_client.requests.get")
    def test_bad_request_and_forbidden(self, get):
        for status in (400, 403):
            get.return_value = _response(status)
            with self.assertRaises(GasoGesError) as ctx:
                self.client.supplies("2024-05-14", "2024-01-01")
            self.assertIn(str(status), str(ctx.exception))

    @mock.patch("fleet.gasoges_client.requests.get")
    def test_timeout(self, get):
        get.side_effect = requests.Timeout()
        with self.assertRaises(GasoGesError) as ctx:
            self.client.vehicles()
        self.assertIn("30 s", str(ctx.exception))

    def test_missing_credentials(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(GasoGesError):
                GasoGesClient()


if __name__ == "__main__":
    unittest.main()
