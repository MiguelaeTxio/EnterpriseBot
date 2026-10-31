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
from fleet.gasoges_rules import best_series
from fleet.gasoges_rules import convention_unit
from fleet.gasoges_rules import deduce_unit
from fleet.gasoges_rules import name_matches
from fleet.gasoges_rules import normalize
from fleet.gasoges_rules import series_reason


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

    def test_junk_values_do_not_fool_it(self):
        junk = A44 + [(_d("2026-06-20 08:00:00"), 33333),
                      (_d("2026-06-28 08:00:00"), 33333),
                      (_d("2026-07-05 08:00:00"), 22100),
                      (_d("2026-07-12 08:00:00"), 33333),
                      (_d("2026-07-20 08:00:00"), 22180)]
        self.assertEqual(deduce_unit(True, True, junk)[0], UNIT_UNKNOWN)

    def test_every_z_is_hours(self):
        self.assertEqual(
            deduce_unit(True, False, A30, code="Z134")[0], UNIT_HOURS)

    def test_few_supplies(self):
        self.assertEqual(deduce_unit(True, True, A30[:2])[0], UNIT_UNKNOWN)


# 7245 GBM (S137): Miguel Ángel teclea bien sus km; el 250.000 redondo
# del 10/03 y el 324.624 del 19/05 (234.624 con dos cifras cambiadas)
# hacían dudosas todas las lecturas buenas de detrás.
GBM = [
    (_d("2026-03-10 14:25:00"), 250000), (_d("2026-03-18 14:19:01"), 227482),
    (_d("2026-03-25 16:52:28"), 228304), (_d("2026-04-08 10:40:29"), 226629),
    (_d("2026-04-08 13:16:38"), 229558), (_d("2026-04-17 13:05:02"), 230841),
    (_d("2026-04-28 12:10:16"), 232102), (_d("2026-05-08 13:34:35"), 233399),
    (_d("2026-05-19 12:43:57"), 324624), (_d("2026-05-28 12:48:58"), 235717),
    (_d("2026-06-08 05:24:21"), 237050), (_d("2026-06-15 13:00:29"), 237984),
    (_d("2026-06-23 12:43:22"), 239086), (_d("2026-07-01 12:59:28"), 240231),
    (_d("2026-07-09 09:58:56"), 241345), (_d("2026-07-17 12:33:47"), 242423),
    (_d("2026-07-27 12:29:45"), 243520), (_d("2026-08-03 12:29:39"), 244525),
    (_d("2026-08-14 04:37:44"), 245613), (_d("2026-08-21 07:37:16"), 246362),
    (_d("2026-09-01 13:08:29"), 247493), (_d("2026-09-03 12:30:38"), 247932),
    (_d("2026-09-14 04:13:52"), 249028), (_d("2026-09-25 12:18:28"), 249931),
    (_d("2026-10-19 12:53:55"), 250825),
]

# A43 (S137), tramo real: un 1.015.000 con un cero de más y dos KM
# por debajo de la serie justo después.
A43 = [
    (_d("2026-09-09 15:39:31"), 101650), (_d("2026-09-16 05:04:46"), 101650),
    (_d("2026-09-16 13:23:24"), 1015000), (_d("2026-09-17 18:06:18"), 101560),
    (_d("2026-09-18 08:55:24"), 101100), (_d("2026-09-23 12:27:56"), 102273),
    (_d("2026-09-24 11:44:00"), 102311), (_d("2026-09-25 12:14:07"), 102350),
]


class BestSeriesTests(unittest.TestCase):
    """
    Meter series chosen among the typed values (S137).

    ---

    Serie del contador elegida entre los KM tecleados (S137).
    """

    def test_gbm_drops_only_the_two_wrong_values(self):
        chain = best_series(GBM, UNIT_KM)
        wrong = {i for i in range(len(GBM)) if i not in chain}
        self.assertEqual({GBM[i][1] for i in wrong},
                         {250000, 226629, 324624})

    def test_gbm_reasons(self):
        chain = best_series(GBM, UNIT_KM)
        self.assertEqual(series_reason(GBM, 0, chain, UNIT_KM),
                         "mayor que la lectura siguiente (227482)")
        self.assertEqual(series_reason(GBM, 8, chain, UNIT_KM),
                         "mayor que la lectura siguiente (235717)")

    def test_a43_extra_zero_and_lower_values(self):
        chain = best_series(A43, UNIT_KM)
        self.assertEqual({A43[i][1] for i in range(len(A43))
                          if i not in chain}, {1015000, 101560, 101100})

    def test_zero_and_tiny_never_enter(self):
        points = [(_d("2026-06-01 08:00:00"), 100),
                  (_d("2026-06-02 08:00:00"), 0),
                  (_d("2026-06-03 08:00:00"), 1),
                  (_d("2026-06-04 08:00:00"), 120)]
        chain = best_series(points, UNIT_HOURS)
        self.assertEqual(chain, {0, 3})
        self.assertEqual(series_reason(points, 1, chain, UNIT_HOURS),
                         "KM vacío o a 0")

    def test_hours_too_fast(self):
        points = [(_d("2026-06-01 08:00:00"), 17500),
                  (_d("2026-06-03 08:00:00"), 17600),
                  (_d("2026-06-05 08:00:00"), 17520)]
        chain = best_series(points, UNIT_HOURS)
        self.assertEqual(chain, {0, 2})

    def test_tie_goes_to_the_latest(self):
        points = [(_d("2026-06-01 08:00:00"), 250825),
                  (_d("2026-06-08 08:00:00"), 260000),
                  (_d("2026-06-09 08:00:00"), 252000)]
        self.assertEqual(best_series(points, UNIT_KM), {0, 2})


class ConventionUnitTests(unittest.TestCase):
    """
    Workshop rule (S137): P and cars/vans by km, A and B by hours.

    ---

    Regla del taller (S137): P, turismos y furgonetas por km; A y B por
    horas; el resto, sin regla.
    """

    def test_cranes_and_booms_go_by_hours(self):
        self.assertEqual(convention_unit("A44", "MÓVILES"), UNIT_HOURS)
        self.assertEqual(convention_unit("B42", "AUTOCARGANTES"),
                         UNIT_HOURS)

    def test_p_and_cars_go_by_km(self):
        self.assertEqual(convention_unit("P21", "TRANSPORTES"), UNIT_KM)
        self.assertEqual(convention_unit("FURGLAR", "TURISMOS"), UNIT_KM)
        # ADOLFO empieza por A pero es un turismo: manda la familia.
        self.assertEqual(convention_unit("ADOLFO", "TURISMOS"), UNIT_KM)

    def test_platforms_forklifts_and_mobile_cranes_by_hours(self):
        self.assertEqual(convention_unit("Z14", "PLATAFORMAS"), UNIT_HOURS)
        self.assertEqual(convention_unit("T05", "CARRETILLAS"), UNIT_HOURS)
        self.assertEqual(convention_unit("H04", "MÓVILES"), UNIT_HOURS)
        # PAOLA empieza por P pero es una plataforma: manda la familia.
        self.assertEqual(convention_unit("PAOLA", "PLATAFORMAS"),
                         UNIT_HOURS)

    def test_vans_by_km(self):
        self.assertEqual(convention_unit("X07", "ASISTENCIA"), UNIT_KM)

    def test_assistance_all_by_km(self):
        # S137: en asistencia, las B van por km. S142: las A (grúas de
        # asistencia) también, sus chóferes teclean los km del camión.
        self.assertEqual(convention_unit("B44", "ASISTENCIA"), UNIT_KM)
        self.assertEqual(convention_unit("7245GBM", "ASISTENCIA"),
                         UNIT_KM)
        self.assertEqual(convention_unit("A30", "ASISTENCIA"), UNIT_KM)

    def test_others_have_no_rule(self):
        self.assertIsNone(convention_unit("V05", "ALQUILER"))
        self.assertIsNone(convention_unit("0672KKZ", ""))


if __name__ == "__main__":
    unittest.main()
