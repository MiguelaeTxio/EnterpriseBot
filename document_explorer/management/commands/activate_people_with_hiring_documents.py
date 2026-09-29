# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/activate_people_with_hiring_documents.py
"""
H30 (S124), roadmap item 3. Activates workers whose hiring documents
are later than their last termination.

---

H30 (S124), punto 3 de la hoja de ruta. Pasa a activas
(`is_active_employee=True`) las personas no activas (NULL o False) que
tengan un CONTRATO o un ALTA vinculados y posteriores a su última baja.
Decisión de Miguel Ángel: el Excel de plantilla es un histórico y ya no
decide quién es activo.

Criterios:
- Alta: tipos `CONTRATO` y `ALTA` (sin subtipos).
- Baja: `BAJA_PERSONAL` y `CARTA_BAJA_VOLUNTARIA` (fin de la relación
  laboral; `PARTE_BAJA_MEDICA` no cuenta).
- Fecha de cada documento: `issue_date`; si no la tiene, la del nombre
  canónico (`..._AAAAMMDD[_N]`), salvo la ficticia 2021-01-01.
- Sin ninguna baja: basta con un contrato o alta, con o sin fecha.
- Con baja: hace falta un contrato o alta con fecha posterior a la
  última baja. Una persona que solo tiene altas/contratos sin fecha se
  lista aparte, sin activarla.

DRY-RUN POR DEFECTO (lista a quién activaría). `--apply` escribe.
`--log-file` obligatorio: log propio en pantalla y en archivo a la vez.
"""
import datetime
import re
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry, PersonIdentity

HIRING_CODES = ("CONTRATO", "ALTA")
TERMINATION_CODES = ("BAJA_PERSONAL", "CARTA_BAJA_VOLUNTARIA")
FICTITIOUS_DATE = datetime.date(2021, 1, 1)
_NAME_DATE_RE = re.compile(r"_(\d{8})(?:_\d+)?\.[^.]+$")


def document_date(entry):
    """
    Date of a document: issue_date, else the canonical name date.

    ---

    Fecha de un documento: `issue_date`; si no, la del nombre canónico
    (nunca la ficticia 2021-01-01). None si no hay ninguna.
    """
    if entry.issue_date:
        return entry.issue_date
    match = _NAME_DATE_RE.search(entry.name or "")
    if not match:
        return None
    try:
        found = datetime.datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None
    return None if found == FICTITIOUS_DATE else found


class Command(BaseCommand):
    """
    Activate people with a hiring document after their last termination.

    ---

    Activa a las personas con contrato o alta posterior a su última baja.
    """

    help = (
        "Activa a las personas no activas con CONTRATO o ALTA posterior "
        "a su última baja (H30, S124). Dry-run por defecto; --apply "
        "escribe."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.

        ---

        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (
            datetime.datetime.now().strftime("%H:%M:%S"), message,
        )
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def _log_plain(self, message):
        """
        Print and append one line without timestamp (final summary).

        ---

        Igual que `_log`, sin hora (resumen final, com-standards 0ter).
        """
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(options["apply"])

    def _run(self, apply_changes):
        """
        Main pass.

        ---

        Pasada principal.
        """
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        people = {
            person.pk: person
            for person in PersonIdentity.objects.exclude(
                is_active_employee=True,
            )
        }
        self._log(
            "Modo: %s -- %d personas no activas (NULL o False)."
            % ("APPLY" if apply_changes else "DRY-RUN", len(people))
        )

        hiring = defaultdict(list)
        terminations = defaultdict(list)
        entries = DocumentIndexEntry.objects.filter(
            domain_content_type=person_ct,
            domain_object_id__in=list(people),
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code__in=HIRING_CODES + TERMINATION_CODES,
        ).select_related("document_type")
        for entry in entries:
            bucket = (
                hiring if entry.document_type.code in HIRING_CODES
                else terminations
            )
            bucket[entry.domain_object_id].append(entry)

        activated, undated_only, later_termination = [], [], []
        for person_pk in sorted(hiring):
            person = people[person_pk]
            label = "%d %s %s, %s (DNI %s, activo=%s)" % (
                person.pk, person.first_surname,
                person.second_surname or "", person.given_name,
                person.dni, person.is_active_employee,
            )
            last_termination = max(
                (
                    found for found in (
                        document_date(e) for e in terminations[person_pk]
                    ) if found
                ),
                default=None,
            )
            dated_hiring = [
                (document_date(e), e) for e in hiring[person_pk]
                if document_date(e)
            ]
            if not terminations[person_pk]:
                reason = "sin ninguna baja; %s" % ", ".join(
                    "%s #%d" % (e.document_type.code, e.pk)
                    for e in hiring[person_pk]
                )
                activated.append((person, label, reason))
                continue
            if not dated_hiring:
                undated_only.append((label, "altas/contratos sin fecha"))
                continue
            newest_date, newest = max(dated_hiring, key=lambda pair: pair[0])
            if last_termination is None or newest_date > last_termination:
                reason = "%s #%d del %s > última baja %s" % (
                    newest.document_type.code, newest.pk, newest_date,
                    last_termination or "sin fecha",
                )
                activated.append((person, label, reason))
            else:
                later_termination.append((
                    label, "último %s del %s <= última baja %s" % (
                        newest.document_type.code, newest_date,
                        last_termination,
                    ),
                ))

        for person, label, reason in activated:
            if apply_changes:
                person.is_active_employee = True
                person.save(update_fields=["is_active_employee", "updated_at"])
            self._log("ACTIVAR %s -- %s" % (label, reason))
        for label, reason in undated_only:
            self._log("NO ACTIVADA (revisar) %s -- %s" % (label, reason))

        self._log_plain("")
        self._log_plain("RESUMEN (%s)" % (
            "APPLY" if apply_changes else "DRY-RUN"
        ))
        self._log_plain("  Personas no activas: %d" % len(people))
        self._log_plain("  Con CONTRATO o ALTA: %d" % len(hiring))
        self._log_plain("  Activadas: %d" % len(activated))
        self._log_plain(
            "  Sin activar, baja posterior: %d" % len(later_termination)
        )
        self._log_plain(
            "  Sin activar, altas sin fecha: %d" % len(undated_only)
        )
        for label, reason in later_termination:
            self._log_plain("    BAJA POSTERIOR %s -- %s" % (label, reason))
