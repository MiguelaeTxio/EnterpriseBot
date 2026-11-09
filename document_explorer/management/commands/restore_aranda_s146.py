# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/restore_aranda_s146.py
"""
Management command: restore_aranda_s146.

One-off (H24, S146): leaves ARANDA REYES, ANTONIO (PersonIdentity 153)
as he was before the alta/baja tests of S146, with the values of the
backup EnterpriseBot_BD_20261108_0300.

---

Comando de gestión: restore_aranda_s146 (H24, S146).

Deja a ARANDA REYES, ANTONIO (pk 153) como estaba antes de las pruebas
de alta y baja de S146, con los valores de la copia de seguridad del
08/11 a las 3:00 (leídos restaurándola en el runner):
- empresa GRUAS ADOLFO ALVAREZ SL, alta 10/07/2026, baja 23/09/2026,
  inactivo (ya lo está);
- sin asignación de sección (las creó el alta de prueba);
- su documentación del cubo ya está en INACTIVOS/ARANDA_REYES_ANTONIO,
  como en la copia (no se toca);
- carpeta local de vuelta a OPERARIOS/TRABAJADORES INACTIVOS/ARANDA
  REYES, ANTONIO, con su nombre original sin código de empresa (trabajo
  para el agente H28).
Sin --apply solo dice lo que haría.
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from document_explorer.local_download_service import current_local_folder
from document_explorer.models import LocalDownloadJob, PersonIdentity
from hr_calendar.models import PersonSectionAssignment

PERSON_ID = 153
ORIGINAL = {
    "employer_company": "GRUAS ADOLFO ALVAREZ SL",
    "hire_date": datetime.date(2026, 7, 10),
    "termination_date": datetime.date(2026, 9, 23),
    "is_active_employee": False,
}
ORIGINAL_FOLDER = ("DOC. PERSONAL/PERSONAL/INACTIVOS/"
                   "ARANDA_REYES_ANTONIO")
LOCAL_FOLDER = ("DOC. PERSONAL/PERSONAL/OPERARIOS/TRABAJADORES INACTIVOS/"
                "ARANDA REYES, ANTONIO")


class Command(BaseCommand):
    help = "Deja a ARANDA REYES como estaba antes de las pruebas de S146."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        log = open(options["log_file"], "a", encoding="utf-8") \
            if options["log_file"] else None

        def say(text):
            line = "[%s] %s" % (
                timezone.localtime().strftime("%H:%M:%S"), text)
            self.stdout.write(line)
            self.stdout.flush()
            if log:
                log.write(line + "\n")
                log.flush()

        apply = options["apply"]
        person = PersonIdentity.objects.filter(pk=PERSON_ID).first()
        if person is None:
            raise CommandError("No existe la persona %d." % PERSON_ID)
        say("# restore_aranda_s146 %s: %s %s, %s" % (
            "APLICANDO" if apply else "SIMULACIÓN", person.first_surname,
            person.second_surname, person.given_name))
        changes = []
        for field, value in ORIGINAL.items():
            now = getattr(person, field)
            say("   %s: %s -> %s%s" % (
                field, now, value, "" if now != value else " (igual)"))
            if now != value:
                changes.append(field)
        say("   carpeta del cubo: %s%s" % (
            person.folder_path,
            " (igual)" if person.folder_path == ORIGINAL_FOLDER
            else " -> DISTINTA de la copia, no se toca"))
        assignments = list(PersonSectionAssignment.objects.filter(
            person=person))
        for assignment in assignments:
            say("   borrar asignación de sección #%d (sección #%d desde "
                "%s)" % (assignment.pk, assignment.section_id,
                         assignment.valid_from))
        local_now = current_local_folder(person)
        move_local = local_now != LOCAL_FOLDER
        say("   carpeta local: %s -> %s%s" % (
            local_now, LOCAL_FOLDER, "" if move_local else " (igual)"))
        if not apply:
            say("# Fin (simulación: nada escrito).")
            return
        with transaction.atomic():
            for field in changes:
                setattr(person, field, ORIGINAL[field])
            if changes:
                person.save(update_fields=changes + ["updated_at"])
            PersonSectionAssignment.objects.filter(
                pk__in=[a.pk for a in assignments]).delete()
            job = None
            if move_local:
                job = LocalDownloadJob.objects.create(
                    person=person, files=[], folder=LOCAL_FOLDER,
                    previous_folder=local_now,
                )
        say("   Ficha restaurada (%s); %d asignación(es) borrada(s)." % (
            ", ".join(changes) or "sin cambios", len(assignments)))
        if job is not None:
            say("   Trabajo local #%d creado para el agente H28." % job.pk)
        say("# Fin.")
