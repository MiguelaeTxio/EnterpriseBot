# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/infer_machine_groups_s153.py
"""
Infer the machine selection groups from who refuels each machine.

---

S153 (Miguel Ángel: "hay que crear los grupos de centros de gasto
infiriéndolos de los repostajes, es decir si la A66 es repostada el 90%
de las veces por Jesús y este pertenece al grupo de asistencia, entonces
la A66 es de asistencia. También sería de ayuda la sección o familia del
vehículo").

Para cada máquina activa con repostajes (GasoGes) en el periodo:
1. Reparte sus repostajes entre los grupos Generales de personas
   (raíz del árbol) de quien repostó; si un grupo llega al umbral
   (--threshold, 0,6 por defecto), la máquina es de ese grupo
   ("repostajes").
2. Si no llega ninguno, la sección vigente de quien repostó, por el
   mismo reparto; si una sección llega al umbral, la máquina va al grupo
   que más personas de esa sección tiene ("sección").
3. Si tampoco, la familia: el grupo que tienen la mayoría de máquinas
   de su familia ya decididas (al menos 3), si llega al umbral
   ("familia").
4. Si no, queda "sin decidir" y se lista para decidirla a mano.

Sin --apply solo informa. Con --apply crea en Generales (de
alvarez_admin) los grupos de centros de gasto con el mismo nombre que
los de personas y AÑADE las máquinas (nunca quita las que ya tengan).
Log propio con pantalla y archivo a la vez (com-standards 0bis).
"""
import datetime
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    """
    Infer machine groups from refuels (dry run unless --apply).
    ---
    Infiere los grupos de centros de gasto de los repostajes.
    """

    help = "Infiere los grupos de centros de gasto de los repostajes."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--threshold", type=float, default=0.6)
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
    def _run(self, options):
        from django.contrib.auth import get_user_model

        from document_explorer.models import PersonGroupTemplate
        from fleet.models import (
            GasoGesSupply, MachineAsset, MachineGroupTemplate,
        )
        from hr_calendar.models import PersonSectionAssignment
        from panel.person_groups import GENERAL_USERNAME

        threshold = options["threshold"]
        since = timezone.now() - datetime.timedelta(days=options["days"])
        today = datetime.date.today()
        self._log("Inferencia de grupos de centros de gasto (%s)" % (
            "APLICANDO" if options["apply"] else "simulación, sin cambios"))
        self._log("Repostajes desde %s, umbral %d %%" % (
            since.date().strftime("%d/%m/%Y"), round(threshold * 100)))

        admin_user = get_user_model().objects.get(username=GENERAL_USERNAME)
        admin = admin_user.company_user
        # Grupos Generales de personas: raíz de cada persona.
        groups = list(PersonGroupTemplate.objects.select_related(
            "created_by__user").prefetch_related("members"))
        by_pk = {g.pk: g for g in groups}

        def is_general(group):
            user = group.created_by.user if group.created_by_id else None
            return user is None or user.username == GENERAL_USERNAME

        def root(group):
            seen = set()
            while group.parent_id and group.parent_id in by_pk \
                    and group.pk not in seen:
                seen.add(group.pk)
                group = by_pk[group.parent_id]
            return group

        person_roots = defaultdict(set)
        for group in groups:
            top = root(group)
            if not is_general(top):
                continue
            for person in group.members.all():
                person_roots[person.pk].add(top.name)
        self._log("Grupos Generales de personas: %s" % ", ".join(sorted(
            {name for names in person_roots.values() for name in names})))

        # Sección vigente hoy de cada persona.
        section_of = {}
        for assignment in PersonSectionAssignment.objects.filter(
                valid_from__lte=today).select_related("section").order_by(
                "person_id", "valid_from", "pk"):
            section_of[assignment.person_id] = (
                assignment.section.name if assignment.section_id else None)
        # Grupo con más personas de cada sección.
        section_group = {}
        tally = defaultdict(Counter)
        for person_pk, names in person_roots.items():
            section = section_of.get(person_pk)
            if section:
                for name in names:
                    tally[section][name] += 1
        for section, counter in tally.items():
            section_group[section] = counter.most_common(1)[0][0]

        machines = list(MachineAsset.objects.filter(
            company=admin.company, is_active=True).order_by("code"))
        refuels = defaultdict(Counter)
        names = {}
        for machine_id, person_id, given, surname in (
                GasoGesSupply.objects.filter(
                    supplied_at__gte=since,
                    vehicle__machine__isnull=False,
                    user__person__isnull=False,
                ).values_list(
                    "vehicle__machine_id", "user__person_id",
                    "user__person__given_name",
                    "user__person__first_surname")):
            refuels[machine_id][person_id] += 1
            names[person_id] = ("%s %s" % (given or "", surname or "")
                                ).strip()

        decided, undecided = {}, []
        total = len(machines)
        for index, machine in enumerate(machines, 1):
            counts = refuels.get(machine.pk)
            if not counts:
                undecided.append((machine, "sin repostajes con persona"))
                continue
            n = sum(counts.values())
            by_group = Counter()
            by_section = Counter()
            for person_id, times in counts.items():
                for name in person_roots.get(person_id, ()):
                    by_group[name] += times
                section = section_of.get(person_id)
                if section:
                    by_section[section] += times
            top = ", ".join("%s %d%%" % (names[p], round(100 * t / n))
                            for p, t in counts.most_common(3))
            self._plain("%s (%s) -- %d repostajes: %s" % (
                machine.code, machine.family or "sin familia", n, top))
            choice = None
            if by_group:
                name, times = by_group.most_common(1)[0]
                if times / n >= threshold:
                    choice = (name, "repostajes %d%%" % round(
                        100 * times / n))
            if choice is None and by_section:
                section, times = by_section.most_common(1)[0]
                if times / n >= threshold and section in section_group:
                    choice = (section_group[section],
                              "sección %s %d%%" % (section, round(
                                  100 * times / n)))
            if choice:
                decided[machine.pk] = (machine,) + choice
                self._plain("    -> %s (%s)" % choice)
            else:
                undecided.append((machine, "ningún grupo llega al umbral"))
                self._plain("    -> sin decidir")
            if index % 25 == 0:
                self._log("Progreso: %d/%d" % (index, total))

        # Familia, para las que quedan.
        family_votes = defaultdict(Counter)
        for machine, name, _why in decided.values():
            if machine.family:
                family_votes[machine.family][name] += 1
        still = []
        for machine, why in undecided:
            votes = family_votes.get(machine.family)
            # Al menos 3 máquinas de la familia ya decididas: con una
            # o dos, la familia no dice nada.
            if votes and sum(votes.values()) >= 3:
                name, times = votes.most_common(1)[0]
                if times / sum(votes.values()) >= threshold:
                    decided[machine.pk] = (machine, name, "familia %s" % (
                        machine.family))
                    continue
            still.append((machine, why))

        self._plain()
        self._plain("RESUMEN")
        per_group = defaultdict(list)
        for machine, name, why in decided.values():
            per_group[name].append("%s (%s)" % (machine.code, why))
        for name in sorted(per_group):
            self._plain("%s (%d): %s" % (name, len(per_group[name]),
                                         "; ".join(sorted(per_group[name]))))
        self._plain("Sin decidir (%d): %s" % (len(still), ", ".join(
            "%s [%s]" % (m.code, why) for m, why in still)))

        if not options["apply"]:
            self._plain("Simulación: no se ha cambiado nada.")
            return
        with transaction.atomic():
            for name, items in per_group.items():
                group, created = MachineGroupTemplate.objects.get_or_create(
                    name=name, parent=None, created_by=admin)
                pks = [machine.pk for machine, gname, _w in decided.values()
                       if gname == name]
                group.members.add(*pks)
                self._plain("%s «%s»: %d centros de gasto añadidos." % (
                    "Creado" if created else "Ya existía", name, len(pks)))
        self._plain("Aplicado.")
