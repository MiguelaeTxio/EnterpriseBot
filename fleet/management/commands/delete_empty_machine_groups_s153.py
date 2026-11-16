# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/delete_empty_machine_groups_s153.py
"""
S153. Delete the machine groups left empty after the assistance split.

---

Miguel Ángel (S153): "Elimina el grupo ese que se ha quedado vacío, el
de Granada y Granada Administración". Solo borra los grupos de la lista
si están vacíos (sin máquinas ni subgrupos con máquinas); si alguno
tiene algo, no borra nada y lo dice.

Sin --apply solo informa. Log propio con pantalla y archivo a la vez
(com-standards 0bis).
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# De dentro a fuera: primero los subgrupos.
PATHS = [
    ("Asistencia", "Granada", "Administración"),
    ("Asistencia", "Granada"),
]


class Command(BaseCommand):
    """
    Delete the listed machine groups if they are empty (dry run).
    ---
    Borra los grupos de la lista si están vacíos.
    """

    help = "Borra los grupos vacíos de Asistencia / Granada (S153)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        stamp = timezone.localtime().strftime("%H:%M:%S")
        line = "[%s] %s" % (stamp, text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["apply"])

    def _find(self, path):
        from fleet.models import MachineGroupTemplate

        node = None
        for name in path:
            node = MachineGroupTemplate.objects.filter(
                name=name, parent=node).first()
            if node is None:
                return None
        return node

    def _run(self, apply_changes):
        self._log("Borrar grupos vacíos (%s)" % (
            "APLICANDO" if apply_changes else "simulación, sin cambios"))
        groups, blocked = [], []
        for path in PATHS:
            label = " / ".join(path)
            group = self._find(path)
            if group is None:
                self._log("«%s»: no existe" % label)
                continue
            count = group.members.count()
            # Subgrupos que no están en la lista (esos se comprueban solos).
            children = [c for c in group.children.all()
                        if path + (c.name,) not in PATHS]
            if count or children:
                blocked.append("«%s»: %d máquinas, subgrupos: %s" % (
                    label, count, ", ".join(c.name for c in children)
                    or "ninguno"))
            groups.append((label, group))
        if blocked:
            for line in blocked:
                self._log("NO SE BORRA NADA -- " + line)
            return
        with transaction.atomic():
            for label, group in groups:
                if apply_changes:
                    group.delete()
                self._log("«%s»: %s" % (
                    label, "borrado" if apply_changes else "se borraría"))
        self._log("Aplicado." if apply_changes
                  else "Simulación: no se ha cambiado nada.")
