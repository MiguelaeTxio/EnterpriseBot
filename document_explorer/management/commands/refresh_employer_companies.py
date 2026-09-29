# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/refresh_employer_companies.py
"""
H30 (S125). Applies, to the given ACTIVE workers only, the same step a
new contract or ALTA triggers: employer from their documents and folder
under ACTIVOS/{EMPRESA}/.

---

H30 (S125). Aplica, SOLO a los trabajadores ACTIVOS que se indiquen
(--person), el mismo paso que dispara un contrato o alta al entrar:
empresa según sus documentos y carpeta en ACTIVOS/{EMPRESA}/. Pensado
para los nuevos ya activados antes de existir el enganche (Farraces).

Nunca es un barrido: Miguel Ángel (S125) -- lo que ya constaba se queda
como estaba; recorrerlo todo hacia atrás con los contratos que tenga el
sistema rompería lo que estaba bien (faltan contratos). Un inactivo no
se toca.

Con --dry-run no guarda nada. Salida en pantalla y en archivo a la vez
(--log-file).
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer.employer_service import refresh_employer_company
from document_explorer.models import PersonIdentity
from document_explorer.person_folder_service import (
    expected_base_folder, free_folder_for, is_in_expected_folder,
    move_person_documents,
)


class Command(BaseCommand):
    """
    Employer and folder for the given active workers.

    ---

    Empresa y carpeta para los trabajadores activos indicados.
    """

    help = (
        "Empresa según documentos y carpeta ACTIVOS/{EMPRESA}/ para los "
        "trabajadores ACTIVOS indicados con --person (nunca un barrido)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--person", type=int, action="append", required=True,
            help="pk de PersonIdentity (se puede repetir).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="No guarda nada; solo informa.",
        )
        parser.add_argument(
            "--log-file", default="",
            help="Ruta del log (además de la pantalla).",
        )

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        self.stdout.write(line)
        if self._log_handle:
            self._log_handle.write(line + "\n")
            self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = (
            open(options["log_file"], "w", encoding="utf-8")
            if options["log_file"] else None
        )
        try:
            self._run(options["person"], options["dry_run"])
        finally:
            if self._log_handle:
                self._log_handle.close()

    def _run(self, person_pks, dry_run):
        people = list(PersonIdentity.objects.filter(pk__in=person_pks))
        missing = set(person_pks) - {person.pk for person in people}
        if missing:
            raise CommandError("No existen: %s" % sorted(missing))
        self._log("Inicio%s: %d trabajador(es)." % (
            " (SIMULACIÓN, no se guarda nada)" if dry_run else "",
            len(people),
        ))
        for position, person in enumerate(people, start=1):
            name = "%s %s, %s (pk %s)" % (
                person.first_surname, person.second_surname,
                person.given_name, person.pk,
            )
            if person.is_active_employee is not True:
                self._log("%d. %s: no está activo -- no se toca." % (
                    position, name,
                ))
                continue
            result = refresh_employer_company(person, save=not dry_run)
            person.employer_company = result["new"]
            if result["profile"] is None:
                self._log(
                    "%d. %s: ningún contrato ni alta identifica la empresa "
                    "-- se queda '%s'." % (
                        position, name, result["old"] or "vacía",
                    )
                )
            else:
                document = result["contract"]
                self._log("%d. %s: '%s' -> '%s' -- %s %s (%s, por %s)." % (
                    position, name, result["old"] or "vacía",
                    result["new"], document.document_type.code,
                    document.pk, document.issue_date or "sin fecha",
                    result["method"],
                ))
            if is_in_expected_folder(person):
                self._log("   carpeta ya correcta: '%s'." % person.folder_path)
                continue
            target = free_folder_for(person, expected_base_folder(person))
            origin = person.folder_path
            suffix = ""
            if not dry_run:
                with transaction.atomic():
                    moved = move_person_documents(person, target)
                suffix = " (%d archivo(s) movidos)" % moved
            self._log("   carpeta '%s' -> '%s'%s." % (
                origin, target, suffix,
            ))
        self._log("Fin.")
