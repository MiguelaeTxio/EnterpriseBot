# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/move_assistance_groups_s153.py
"""
S153. New assistance subgroups (Comercial, Loja, Mollina) and moves.

---

Miguel Ángel (S153): en los grupos de Asistencia se distingue
Comercial (5080MZV), Loja (A60, B30, G09, G15, P22, P27, X06),
Mollina (G11) y Málaga (X09, A30, G16, G14, G12).

Cada máquina se saca de los demás subgrupos de «Asistencia» y se mete
en el suyo y en «Asistencia» (quien está en un subgrupo está también en
el de encima). Los grupos de fuera de «Asistencia» no se tocan (la A30
sigue en «Grúas y Camiones / Producción»). Los subgrupos que falten se
crean en Generales (de alvarez_admin); los que se queden vacíos no se
borran.

Sin --apply solo informa. Log propio con pantalla y archivo a la vez
(com-standards 0bis).
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

ROOT = "Asistencia"
MOVES = [
    ("5080MZV", "Comercial"),
    ("A60", "Loja"),
    ("B30", "Loja"),
    ("G09", "Loja"),
    ("G15", "Loja"),
    ("P22", "Loja"),
    ("P27", "Loja"),
    ("X06", "Loja"),
    ("G11", "Mollina"),
    ("X09", "Málaga"),
    ("A30", "Málaga"),
    ("G16", "Málaga"),
    ("G14", "Málaga"),
    ("G12", "Málaga"),
]


def descendants(group):
    """
    All groups below one (any depth).
    ---
    Todos los grupos que cuelgan de uno, a cualquier profundidad.
    """
    result, pending = [], list(group.children.all())
    while pending:
        node = pending.pop()
        result.append(node)
        pending.extend(node.children.all())
    return result


class Command(BaseCommand):
    """
    Move assistance machines to their subgroups (dry run by default).
    ---
    Reparte las máquinas de Asistencia en sus subgrupos.
    """

    help = "Asistencia: Comercial, Loja, Mollina y Málaga (S153)."

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

        from fleet.models import MachineAsset, MachineGroupTemplate
        from panel.person_groups import GENERAL_USERNAME

        self._log("Subgrupos de «%s» (%s)" % (
            ROOT, "APLICANDO" if apply_changes
            else "simulación, sin cambios"))
        admin = get_user_model().objects.get(
            username=GENERAL_USERNAME).company_user
        root = MachineGroupTemplate.objects.get(name=ROOT, parent=None)
        lines, missing, created = [], [], []
        with transaction.atomic():
            for code, leaf_name in MOVES:
                machine = MachineAsset.objects.filter(
                    company=admin.company, code=code).first()
                if machine is None:
                    missing.append(code)
                    continue
                leaf = MachineGroupTemplate.objects.filter(
                    name=leaf_name, parent=root).first()
                if leaf is None:
                    if leaf_name not in created:
                        created.append(leaf_name)
                    if apply_changes:
                        leaf = MachineGroupTemplate.objects.create(
                            name=leaf_name, parent=root, created_by=admin)
                below = descendants(root)
                old = [g for g in below if leaf is None or g.pk != leaf.pk
                       if g.members.filter(pk=machine.pk).exists()]
                if apply_changes:
                    for group in old:
                        group.members.remove(machine)
                    root.members.add(machine)
                    leaf.members.add(machine)
                lines.append("%s -> «%s / %s»%s" % (
                    code, ROOT, leaf_name,
                    " (sale de %s)" % ", ".join(
                        "«%s»" % g.path_label() for g in old)
                    if old else ""))
            self._plain("")
            self._plain("RESUMEN")
            for line in lines:
                self._plain(line)
            self._plain("Subgrupos nuevos: %s" % (
                ", ".join("«%s / %s»" % (ROOT, c) for c in created)
                or "ninguno"))
            if missing:
                self._plain("No encontradas: %s" % ", ".join(missing))
            self._plain("")
            self._plain("Subgrupos de «%s» después:" % ROOT)
            for group in sorted(descendants(root),
                                key=lambda g: g.path_label()):
                codes = sorted(group.members.values_list("code",
                                                         flat=True))
                self._plain("«%s» -- %d: %s" % (
                    group.path_label(), len(codes),
                    " ".join(codes) or "(vacío)"))
            self._plain("Aplicado." if apply_changes
                        else "Simulación: no se ha cambiado nada.")
