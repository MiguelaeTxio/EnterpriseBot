# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/refresh_employer_companies.py
"""
H30 (S125). Recalculates every worker's employer company from his/her
own contracts (see document_explorer.employer_service).

---

H30 (S125). Recalcula la empresa de todos los trabajadores con algún
contrato a partir de sus propios contratos (ver
document_explorer.employer_service): manda el más reciente que la
identifique, por CIF en el texto o, si da problemas, por Gemini.

Con --dry-run no guarda nada: solo informa de lo que cambiaría.
Salida en pantalla y en archivo a la vez (--log-file).
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from document_explorer.employer_service import (
    CONTRACT_TYPE_CODES, refresh_employer_company,
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
                document_type__code__in=CONTRACT_TYPE_CODES,
                domain_object_id__isnull=False,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            ).values_list("domain_object_id", flat=True)
        )
        people = PersonIdentity.objects.filter(pk__in=person_ids).order_by(
            "first_surname", "second_surname", "given_name",
        )
        self._log(
            "Inicio%s: %d trabajadores con contrato." % (
                " (SIMULACIÓN, no se guarda nada)" if dry_run else "",
                people.count(),
            )
        )
        changed = unchanged = unresolved = 0
        by_method = {"CIF": 0, "Gemini": 0}
        for position, person in enumerate(people, start=1):
            result = refresh_employer_company(person, save=not dry_run)
            name = "%s %s, %s (pk %s)" % (
                person.first_surname, person.second_surname,
                person.given_name, person.pk,
            )
            if result["profile"] is None:
                unresolved += 1
                self._log(
                    "%d. %s: NINGÚN contrato identifica la empresa "
                    "(%d contratos) -- se queda '%s'." % (
                        position, name, len(result["unresolved"]),
                        result["old"] or "vacía",
                    )
                )
                continue
            by_method[result["method"]] += 1
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
                changed += 1
                self._log("%d. %s: '%s' -> '%s' -- %s." % (
                    position, name, result["old"] or "vacía",
                    result["new"], detail,
                ))
            else:
                unchanged += 1
                self._log("%d. %s: sin cambio ('%s') -- %s." % (
                    position, name, result["new"], detail,
                ))
        self._log(
            "Fin. Cambian: %d. Sin cambio: %d. Sin empresa identificable: "
            "%d. Resueltos por CIF: %d, por Gemini: %d." % (
                changed, unchanged, unresolved,
                by_method["CIF"], by_method["Gemini"],
            )
        )
