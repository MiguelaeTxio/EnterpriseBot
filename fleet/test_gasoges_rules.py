# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/test_gasoges_rules.py
"""
H30 (S135). Tests of the GasoGes rules with real cases of S135.

---

H30 (S135). Pruebas de las reglas de GasoGes con casos reales de S135
(EnterpriseBot_006.txt y EnterpriseBot_007.txt).
"""
import unittest
from datetime import datetime

from fleet.gasoges_rules import UNIT_HOURS
from fleet.gasoges_rules import UNIT_KM
from fleet.gasoges_rules import UNIT_UNKNOWN
from fleet.gasoges_rules import check_reading
from fleet.gasoges_rules import deduce_unit
from fleet.gasoges_rules import name_matches
from fleet.gasoges_rules import normalize


def _d(text):
    """
    Parse a supply datetime.

    ---

    Convierte una fecha y hora de suministro.
    """
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


# A30 (horómetro y odómetro): sube unos 900 en 12 días -> km.
A30 = [
    (_d("2026-06-04 19:52:11"), 22081), (_d("2026-06-05 11:55:21"), 22118),
    (_d("2026-06-05 18:55:16"), 22219), (_d("2026-06-09 00:47:54"), 22376),
    (_d("2026-06-10 23:53:20"), 22507), (_d("2026-06-11 19:05:29"), 22694),
    (_d("2026-06-13 16:24:11"), 22937), (_d("2026-06-16 14:18:56"), 23005),
]
# A44 (horómetro y odómetro): horas con ruido y un 0.
A44 = [
    (_d("2026-05-13 12:32:00"), 0), (_d("2026-05-15 06:38:33"), 21849),
    (_d("2026-05-15 18:37:13"), 21581), (_d("2026-05-21 13:46:23"), 21881),
    (_d("2026-05-29 06:38:51"), 22555), (_d("2026-05-29 15:37:15"), 21989),
    (_d("2026-06-02 17:00:10"), 21942), (_d("2026-06-05 07:01:50"), 21333),
]


class NameMatchTests(unittest.TestCase):
    """
    GasoGes user names against worker names.

    ---

    Nombres de usuarios de GasoGes contra nombres de fichas.
    """

    def test_exact_words_any_order(self):
        self.assertTrue(name_matches(
            "LOPEZ RAMOS JOSE ANTONIO", "JOSE ANTONIO LOPEZ RAMOS"))

    def test_accents_and_enye(self):
        self.assertTrue(name_matches(
            "CAÑAMERO NAVARRO PABLO     ", "Pablo Cañamero Navarro"))

    def test_truncated_last_word(self):
        self.assertTrue(name_matches(
            "GONZALEZ MILLAN SALVADOR DAVI",
            "SALVADOR DAVID GONZALEZ MILLAN"))

    def test_short_name_needs_whole_words(self):
        self.assertFalse(name_matches(
            "MENA RUIZ DAV", "DAVID MENA RUIZ"))

    def test_repeated_surname_counts_twice(self):
        self.assertTrue(name_matches(
            "GOMEZ GOMEZ FRANCISCO", "FRANCISCO GOMEZ GOMEZ"))
        self.assertFalse(name_matches(
            "GOMEZ GOMEZ FRANCISCO", "FRANCISCO GOMEZ RIVERO"))

    def test_normalize(self):
        self.assertEqual(normalize(" z-01 "), "Z01")


class DeduceUnitTests(unittest.TestCase):
    """
    Unit deduction from the meter flags and the supplies.

    ---

    Deducción de la unidad por los contadores y los suministros.
    """

    def test_only_odometer(self):
        self.assertEqual(deduce_unit(True, False, [])[0], UNIT_KM)

    def test_only_hour_meter(self):
        self.assertEqual(deduce_unit(False, True, [])[0], UNIT_HOURS)

    def test_both_fast_growth_is_km(self):
        self.assertEqual(deduce_unit(True, True, A30)[0], UNIT_KM)

    def test_both_noisy_slow_is_unknown(self):
        self.assertEqual(deduce_unit(True, True, A44)[0], UNIT_UNKNOWN)

    def test_few_supplies(self):
        self.assertEqual(deduce_unit(True, True, A30[:2])[0], UNIT_UNKNOWN)


class CheckReadingTests(unittest.TestCase):
    """
    Credibility of one typed value against the previous reading.

    ---

    Si un valor tecleado vale como lectura frente a la anterior.
    """

    def setUp(self):
        self.before = _d("2026-06-01 08:00:00")
        self.after = _d("2026-06-03 08:00:00")

    def test_zero_is_doubtful(self):
        self.assertFalse(check_reading(
            0, UNIT_KM, 100, self.before, self.after)[0])

    def test_first_reading_accepted(self):
        self.assertTrue(check_reading(
            555, UNIT_KM, None, None, self.after)[0])

    def test_lower_than_previous(self):
        self.assertFalse(check_reading(
            21333, UNIT_HOURS, 21942, self.before, self.after)[0])

    def test_extra_zero(self):
        self.assertFalse(check_reading(
            1000040, UNIT_KM, 100004, self.before, self.after)[0])

    def test_hours_too_fast(self):
        self.assertFalse(check_reading(
            17600, UNIT_HOURS, 17500, self.before, self.after)[0])

    def test_normal_km(self):
        self.assertTrue(check_reading(
            100900, UNIT_KM, 100004, self.before, self.after)[0])


if __name__ == "__main__":
    unittest.main()
