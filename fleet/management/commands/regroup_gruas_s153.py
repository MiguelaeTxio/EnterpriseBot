# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/regroup_gruas_s153.py
"""
S153. Restore "Comerciales" inside "Grúas y Camiones" and put the rest
of its machines in a new working subgroup.

---

Miguel Ángel (S153): sacó sin querer del grupo «Grúas y Camiones» el
vehículo de «Grúas y Camiones / Comerciales» (0672KKZ); hay que
volverlo a meter, y todos los demás de «Grúas y Camiones» van a un
subgrupo nuevo dentro de él, con los que están trabajando
(«Grúas y Camiones / Producción»; el nombre se cambia en el panel).

Reglas de los grupos (S147): quien está en un subgrupo está también en
el de encima, y una máquina solo está en un subgrupo de cada grupo. Por
eso los que ya están en «Comerciales» no van a «Producción». Solo
añade: nunca quita ni mueve nada.

Sin --apply solo informa. Log propio con pantalla y archivo a la vez
(com-standards 0bis).
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

PARENT = "Grúas y Camiones"
COMMERCIAL = "Comerciales"
WORKING = "Producción"


class Command(BaseCommand):
    """
    Restore Comerciales and create the working subgroup (dry run).
    ---
    Recompone «Grúas y Camiones»: Comerciales y Producción.
    """

    help = "Recompone «Grúas y Camiones»: Comerciales y Producción (S153)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text=""):
        stamp = timezone.localtime().strftime("%H:%M:%S")
        line = "[%s] %s" % (stamp, text) if text else ""
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def _plain(self, text=""):
        print(text, flush=True)
        self._out.write(text + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["apply"])

    def _run(self, apply_changes):
        from django.contrib.auth import get_user_model

        from fleet.models import MachineGroupTemplate
        from panel.person_groups import GENERAL_USERNAME

        self._log("Recomponer «%s» (%s)" % (
            PARENT, "APLICANDO" if apply_changes
            else "simulación, sin cambios"))
        admin = get_user_model().objects.get(
            username=GENERAL_USERNAME).company_user
        parent = MachineGroupTemplate.objects.get(name=PARENT,
                                                  parent=None)
        commercial = MachineGroupTemplate.objects.get(name=COMMERCIAL,
                                                      parent=parent)
        working = MachineGroupTemplate.objects.filter(
            name=WORKING, parent=parent).first()
        in_parent = set(parent.members.all())
        in_commercial = set(commercial.members.all())
        in_working = set(working.members.all()) if working else set()
        # Los de otros subgrupos de «Grúas y Camiones» no se tocan.
        in_other = set()
        for child in parent.children.exclude(
                pk__in=[commercial.pk] + ([working.pk] if working else [])):
            in_other |= set(child.members.all())
        back = sorted(in_commercial - in_parent, key=lambda m: m.code)
        to_working = sorted(in_parent - in_commercial - in_other
                            - in_working, key=lambda m: m.code)
        self._log("«%s»: %d máquinas; «%s»: %d; otros subgrupos: %d" % (
            PARENT, len(in_parent), COMMERCIAL, len(in_commercial),
            len(in_other)))
        with transaction.atomic():
            if apply_changes:
                if working is None:
                    working = MachineGroupTemplate.objects.create(
                        name=WORKING, parent=parent, created_by=admin)
                parent.members.add(*back)
                working.members.add(*to_working)
        self._plain("")
        self._plain("RESUMEN")
        self._plain("Vuelven a «%s» (están en «%s / %s») -- %d: %s" % (
            PARENT, PARENT, COMMERCIAL, len(back),
            " ".join(m.code for m in back) or "ninguna"))
        self._plain("A «%s / %s»%s -- %d: %s" % (
            PARENT, WORKING, "" if working else " (grupo nuevo)",
            len(to_working),
            " ".join(m.code for m in to_working) or "ninguna"))
        if in_other:
            self._plain("En otros subgrupos, no se tocan: %s" % " ".join(
                sorted(m.code for m in in_other)))
        self._plain("Aplicado." if apply_changes
                    else "Simulación: no se ha cambiado nada.")
