# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/refresh_employer_companies.py
"""
H30 (S125). Recalculates every worker's employer company from his/her
own contracts (see document_explorer.employer_service).

---

H30 (S125). Recalcula la empresa de todos los trabajadores con algún
contrato a partir de sus propios contratos (ver
document_explorer.employer_service): manda el más reciente que la
identifique, por CIF en el texto o, si da problemas, por Gemini.

Además (punto 4 de S125): todo trabajador ACTIVO que no esté en su
carpeta ACTIVOS/{EMPRESA}/ (p. ej. Farraces en PTE CONTRATACION) pasa
allí con toda su documentación (movimiento virtual, solo índice).

Con --dry-run no guarda nada: solo informa de lo que cambiaría.
Salida en pantalla y en archivo a la vez (--log-file).
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from django.db import transaction

from document_explorer.employer_service import (
    ACTIVATING_TYPE_CODES, refresh_employer_company,
)
from document_explorer.person_folder_service import (
    expected_base_folder, free_folder_for, is_in_expected_folder,
    move_person_documents,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity


class Command(BaseCommand):
    """
    Refresh employer_company from contracts.

    ---

    Refresca employer_company desde los contratos.
    """

    help = "Recalcula la empresa de cada trabajador según sus contratos."

    def add_arguments(self, parser):
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
            self._run(options["dry_run"])
        finally:
            if self._log_handle:
                self._log_handle.close()

    def _run(self, dry_run):
        person_ids = set(
            DocumentIndexEntry.objects.filter(
                document_type__code__in=ACTIVATING_TYPE_CODES,
                domain_object_id__isnull=False,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            ).values_list("domain_object_id", flat=True)
        )
        people = PersonIdentity.objects.filter(pk__in=person_ids).order_by(
            "first_surname", "second_surname", "given_name",
        )
        self._log(
            "Inicio%s: %d trabajadores con contrato o alta." % (
                " (SIMULACIÓN, no se guarda nada)" if dry_run else "",
                people.count(),
            )
        )
        changed = unchanged = unresolved = relocated = 0
        by_method = {"CIF": 0, "Gemini": 0}
        for position, person in enumerate(people, start=1):
            result = refresh_employer_company(person, save=not dry_run)
            # En simulación la empresa nueva no se guarda, pero la carpeta
            # de destino se calcula con ella.
            person.employer_company = result["new"]
            name = "%s %s, %s (pk %s)" % (
                person.first_surname, person.second_surname,
                person.given_name, person.pk,
            )
            self._log("%d. %s: %s." % (
                position, name, self._employer_text(result),
            ))
            if result["profile"] is None:
                unresolved += 1
            else:
                by_method[result["method"]] += 1
                if result["changed"]:
                    changed += 1
                else:
                    unchanged += 1
            if person.is_active_employee and not is_in_expected_folder(
                person,
            ):
                relocated += 1
                target = free_folder_for(person, expected_base_folder(person))
                self._log("   carpeta '%s' -> '%s'%s." % (
                    person.folder_path, target,
                    "" if dry_run else self._move(person, target),
                ))
        self._log(
            "Fin. Empresa: cambian %d, sin cambio %d, sin identificar %d "
            "(por CIF %d, por Gemini %d). Carpetas movidas a ACTIVOS: %d." % (
                changed, unchanged, unresolved,
                by_method["CIF"], by_method["Gemini"], relocated,
            )
        )

    def _move(self, person, target):
        """
        Move the person's documentation; returns a log suffix.

        ---

        Mueve la documentación de la persona; devuelve el sufijo del log.
        """
        with transaction.atomic():
            moved = move_person_documents(person, target)
        return " (%d archivo(s) movidos)" % moved

    def _employer_text(self, result):
        """
        One log line about the employer result.

        ---

        Una línea de log con el resultado de la empresa.
        """
        if result["profile"] is None:
            return (
                "NINGÚN contrato identifica la empresa (%d contrato(s)) "
                "-- se queda '%s'" % (
                    len(result["unresolved"]), result["old"] or "vacía",
                )
            )
        contract = result["contract"]
        detail = "contrato %s (%s, %s, por %s)" % (
            contract.pk, contract.document_type.code,
            contract.issue_date or "sin fecha", result["method"],
        )
        if result["unresolved"]:
            detail += "; %d contrato(s) más reciente(s) sin empresa " \
                "legible: %s" % (
                    len(result["unresolved"]),
                    ", ".join(str(c.pk) for c in result["unresolved"]),
                )
        if result["changed"]:
            return "'%s' -> '%s' -- %s" % (
                result["old"] or "vacía", result["new"], detail,
            )
        return "sin cambio ('%s') -- %s" % (result["new"], detail)
