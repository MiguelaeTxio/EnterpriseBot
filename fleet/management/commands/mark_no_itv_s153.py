# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/mark_no_itv_s153.py
"""
S153. Mark as "No pasa ITV" the cost centres whose plate field does not
hold a real plate.

---

S153. Tras el relleno de la primera ITV (EnterpriseBot_317), Miguel
Ángel: "Márcalas" -- las máquinas activas sin tipo para la ITV cuyo
campo matrícula no tiene una matrícula de verdad (plataformas Z con
"Z-91", grupos V, S, contenedores, cuba, tanqueta...) pasan a «No pasa
ITV», para que no queden pendientes ni avisen de la ITV.

Solo toca las que tienen el tipo vacío: nunca cambia un tipo ya puesto.
Una matrícula con algo detrás ("7386BNH A") cuenta como de verdad.
Las que tienen el campo matrícula vacío no se tocan.

Sin --apply solo lista. Log propio con pantalla y archivo a la vez
(com-standards 0bis).
"""
import re

from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.document_check_service import normalize_plate

_EMBEDDED_PLATE = re.compile(r"[0-9]{4}[A-Z]{3}")


def has_real_plate(value):
    """
    True when the plate field holds a real Spanish plate.
    ---
    True si el campo matrícula tiene una matrícula española de verdad.
    """
    if normalize_plate(value):
        return True
    clean = re.sub(r"[\s\-.]", "", (value or "").upper())
    return bool(_EMBEDDED_PLATE.search(clean))


class Command(BaseCommand):
    help = "S153: marca «No pasa ITV» las máquinas sin matrícula de verdad."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def _plain(self, text):
        print(text, flush=True)
        self._out.write(text + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["apply"])

    def _run(self, apply_changes):
        from fleet.models import MachineAsset

        self._log("Marcar «No pasa ITV» (%s)" % (
            "APLICANDO" if apply_changes else "simulación, sin cambios"))
        candidates = MachineAsset.objects.filter(
            is_active=True, itv_category="",
        ).exclude(plate="").exclude(plate__isnull=True).order_by("code")
        marked, kept = [], []
        for machine in candidates:
            if has_real_plate(machine.plate):
                kept.append(machine.code)
                continue
            marked.append("%s [%s] %s" % (
                machine.code, machine.plate, machine.family or "sin familia"))
            if apply_changes:
                machine.itv_category = MachineAsset.ITV_NONE
                machine.save(update_fields=["itv_category"])
        self._plain("")
        self._plain("RESUMEN")
        self._plain("%s «No pasa ITV» (%d): %s" % (
            "Marcadas" if apply_changes else "Se marcarían",
            len(marked), "; ".join(marked) or "ninguna"))
        self._plain("Con matrícula de verdad, sin tocar (%d): %s" % (
            len(kept), ", ".join(kept) or "ninguna"))
        self._plain("Aplicado." if apply_changes
                    else "Simulación: no se ha cambiado nada.")
