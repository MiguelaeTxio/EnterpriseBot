# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/assign_machine_groups_s153.py
"""
Put machines in the selection groups Miguel Ángel decided by hand.

---

S153. Tras la prueba de inferencia por repostajes (EnterpriseBot_310),
Miguel Ángel decidió a mano el primer lote ("De momento asignamos
esto"):

- 8029BZV (Mercedes ML270, vehículo de socios) -> Gerentes, con los
  Porsche y los otros de alta gama (BMW X5, Audi Q7, Lexus).
- 5080MZV (coche de Pepe) -> Asistencia / Granada / Administración.
- 7245GBM (el coche que lleva él) -> Administración / Informática.
- 0672KKZ (el de Miguel Ángel, comercial) -> Grúas y Camiones /
  Comerciales.
- 9843KBZ (Tomás) y 0067JDK (Carlín) -> Plataformas / Comerciales.
- "Los demás de asistencia pueden ir a Asistencia:Málaga": todas las
  máquinas activas de familia ASISTENCIA que no estén en la lista de
  arriba (X02 incluida, ya unificada con 7386BNH); las de ASISTENCIA
  sin repostajes van a Asistencia / Granada ("ponlas en Granada").
- La A30 espera al lunes (está en «Grúas y Camiones», no se toca) y
  las carretillas T quedan sin asignar.
- P23: a Asistencia / Granada si reposta con Francisco Miguel o con
  Antonio de Granada; si no, con las demás a Asistencia / Málaga.

"Grúas" es el grupo «Grúas y Camiones» que ya hizo él.

Reglas de los grupos (S147, panel/person_groups.py): quien entra en un
subgrupo entra también en todos los de encima, y una máquina solo está
en un subgrupo de cada grupo. Por eso:
- se añade la máquina al grupo final y a todos los de encima;
- si ya está en un subgrupo hermano (p. ej. en otro subgrupo de
  Asistencia), no se toca y se lista;
- una máquina que ya está en otro grupo hecho a mano (A30 en «Grúas y
  Camiones») no se toca y se lista, para que decida él.
Nunca quita ni mueve nada. Los grupos que falten se crean en Generales
(de alvarez_admin).

Sin --apply solo informa. Log propio con pantalla y archivo a la vez
(com-standards 0bis).
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

ASSIGNMENTS = [
    ("8029BZV", "Gerentes"),
    # S153: "Mete solo los Porsche y los otros de alta gama" (sin los
    # Mercedes GLA/B180 ni las furgonetas de taller).
    ("2667LMK", "Gerentes"),
    ("4089LDP", "Gerentes"),
    ("ALE", "Gerentes"),
    ("ADOLFO", "Gerentes"),
    ("ADOLFO2", "Gerentes"),
    ("2119NGV", "Gerentes"),
    ("0168DZS", "Gerentes"),
    ("6951HZS", "Gerentes"),
    # S153: "Las de Asistencia sin repostajes ponlas en Granada".
    ("A60", "Asistencia / Granada"),
    ("B30", "Asistencia / Granada"),
    ("G09", "Asistencia / Granada"),
    ("G11", "Asistencia / Granada"),
    ("G12", "Asistencia / Granada"),
    ("G14", "Asistencia / Granada"),
    ("G15", "Asistencia / Granada"),
    ("G16", "Asistencia / Granada"),
    ("P22", "Asistencia / Granada"),
    ("P27", "Asistencia / Granada"),
    ("X06", "Asistencia / Granada"),
    ("X09", "Asistencia / Granada"),
    ("5080MZV", "Asistencia / Granada / Administración"),
    ("7245GBM", "Administración / Informática"),
    ("0672KKZ", "Grúas y Camiones / Comerciales"),
    ("9843KBZ", "Plataformas / Comerciales"),
    ("0067JDK", "Plataformas / Comerciales"),
]
ASSISTANCE_FAMILY = "ASISTENCIA"
ASSISTANCE_PATH = "Asistencia / Málaga"
GRANADA_PATH = "Asistencia / Granada"
P23_CODE = "P23"
# Quien manda la P23 a Granada (palabras del nombre en GasoGes).
GRANADA_DRIVERS = (("FRANCISCO", "MIGUEL"), ("ANTONIO", "GRANADA"))


class Command(BaseCommand):
    """
    Assign machines to groups by hand-made rules (dry run by default).
    ---
    Mete máquinas en los grupos que decidió Miguel Ángel.
    """

    help = "Mete máquinas en los grupos decididos a mano (S153)."

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
            self._run(options)

    # ------------------------------------------------------------------
    def _plan(self, admin):
        from fleet.models import GasoGesSupply, MachineAsset

        machines = {m.code: m for m in MachineAsset.objects.filter(
            company=admin.company, is_active=True)}
        plan, missing = [], []
        for code, path in ASSIGNMENTS:
            if code in machines:
                plan.append((machines[code], path, "decidido a mano"))
            else:
                missing.append(code)
        taken = {code for code, _p in ASSIGNMENTS}
        for code in sorted(machines):
            machine = machines[code]
            if code in taken or machine.family != ASSISTANCE_FAMILY:
                continue
            path, why = ASSISTANCE_PATH, "familia ASISTENCIA"
            if code == P23_CODE:
                names = set(GasoGesSupply.objects.filter(
                    vehicle__machine=machine).values_list(
                    "user__name", flat=True))
                hit = [n for n in names if n and any(
                    all(w in n.upper() for w in words)
                    for words in GRANADA_DRIVERS)]
                if hit:
                    path, why = GRANADA_PATH, "reposta con %s" % (
                        ", ".join(sorted(hit)))
                else:
                    why = "no reposta con Francisco Miguel ni Antonio " \
                          "de Granada (repostan: %s)" % ", ".join(
                              sorted(n for n in names if n) or ["nadie"])
            plan.append((machine, path, why))
        return plan, missing

    def _chain(self, path, admin, apply_changes, created):
        from fleet.models import MachineGroupTemplate

        parts = [p.strip() for p in path.split("/")]
        chain, parent = [], None
        for depth, name in enumerate(parts):
            found = MachineGroupTemplate.objects.filter(
                name=name, parent=parent).order_by("pk").first()
            if found is None:
                label = " / ".join(parts[:depth + 1])
                if label not in created:
                    created.append(label)
                if not apply_changes:
                    return chain + [None] * (len(parts) - depth)
                found = MachineGroupTemplate.objects.create(
                    name=name, parent=parent, created_by=admin)
            chain.append(found)
            parent = found
        return chain

    def _run(self, options):
        from django.contrib.auth import get_user_model

        from panel.person_groups import GENERAL_USERNAME

        apply_changes = options["apply"]
        self._log("Asignación a mano de grupos de centros de gasto (%s)" % (
            "APLICANDO" if apply_changes else "simulación, sin cambios"))
        admin = get_user_model().objects.get(
            username=GENERAL_USERNAME).company_user
        plan, missing = self._plan(admin)
        created, added, skipped = [], {}, []
        with transaction.atomic():
            for machine, path, why in plan:
                current = list(machine.group_templates.all())
                chain = self._chain(path, admin, apply_changes, created)
                wanted = {g.pk for g in chain if g is not None}
                foreign = [g for g in current if g.pk not in wanted]
                if foreign:
                    skipped.append("%s: ya está en %s; iría a «%s» (%s)" % (
                        machine.code, ", ".join(
                            "«%s»" % g.path_label() for g in foreign),
                        path, why))
                    continue
                for group in chain:
                    if group is not None and apply_changes:
                        group.members.add(machine)
                added.setdefault(path, []).append(
                    "%s %s (%s)" % (machine.code, machine.family or "", why))
            self._plain("")
            self._plain("RESUMEN")
            for path in sorted(added):
                self._plain("«%s» -- %d: %s" % (
                    path, len(added[path]), "; ".join(added[path])))
            self._plain("Grupos nuevos: %s" % (
                ", ".join("«%s»" % c for c in created) or "ninguno"))
            if skipped:
                self._plain("No se tocan (%d):" % len(skipped))
                for line in skipped:
                    self._plain("  " + line)
            if missing:
                self._plain("No encontradas activas: %s" % ", ".join(missing))
            self._plain("Aplicado." if apply_changes
                        else "Simulación: no se ha cambiado nada.")
