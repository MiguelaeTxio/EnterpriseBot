# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/rescue_dossier_documents_s127.py
"""
H30 (S127). Bring to light essential documents hidden inside dossiers.

---

H30 (S127). Saca a la luz los documentos esenciales escondidos dentro
de dossiers -- los que la regla S041 tiró a la papelera y los que se
archivaron con un solo tipo llevando más documentos dentro (causa de
raíz y arreglo del pipeline: `dossier_service`).

Lista CERRADA de casos, cada uno verificado a mano con la imagen del
documento (sin Gemini, Miguel Ángel: "no quiero gastar 300 euros en
llamadas a Gemini"), solo de trabajadores activos. Tres acciones:

- EXTRAER: archivo nuevo con su tipo en la ficha de la persona, con
  las páginas y fechas leídas en el propio documento
  (`dossier_service.extract_document`). El original no se toca.
- RESTAURAR: el archivo vuelve de la papelera y se archiva con su tipo,
  su dueño y sus fechas.
- RETIPAR: archivo vivo con el tipo equivocado; se archiva con el
  bueno y sus fechas.

Idempotente: lo ya archivado (mismo tipo con la misma caducidad o
posterior) no se vuelve a sacar. Sin --apply solo informa. Log propio
con --log-file (pantalla y archivo a la vez, una línea por caso).
"""
import datetime

from django.core.management.base import BaseCommand

from document_explorer import dossier_service
from document_explorer.classification_service import file_entry_manually
from document_explorer.models import DocumentIndexEntry, PersonIdentity

EXTRACT, RESTORE, RETYPE = "EXTRAER", "RESTAURAR", "RETIPAR"

# (acción, archivo, persona, tipo, páginas, expedición, caducidad, nota)
CASES = (
    # Gutiérrez Mateo Cristhian: escaneo de 4 tarjetas tirado por la
    # regla S041; el DNI vence el 24/11/2027 (en la BD ponía 2032).
    (RESTORE, 35943, 222, "DNI", None, "2022-11-24", "2027-11-24",
     "DNI en el escaneo de tarjetas que fue a la papelera"),
    (EXTRACT, 35943, 222, "TACOGRAFO", None, "2023-04-02", "2028-04-02",
     "tarjeta de conductor en el mismo escaneo"),
    (EXTRACT, 35943, 222, "TARJETA_CUALIF_CONDUCTOR", None, "2023-04-17",
     "2028-04-17", "CAP en el mismo escaneo"),
    # Campos Román: el "carnet de conducir" lleva su DNI en la misma hoja.
    (EXTRACT, 34899, 224, "DNI", [1], "2022-03-11", "2032-03-11",
     "DNI en la hoja del permiso de conducción"),
    # Correa Munhoz: archivado como NIE (es español); lleva su DNI, la
    # tarjeta de conductor y el permiso vigentes.
    (RETYPE, 39306, 198, "DNI", None, "2023-08-31", "2033-08-31",
     "archivado como NIE; es su DNI vigente"),
    (EXTRACT, 39306, 198, "TACOGRAFO", None, "2024-12-16", "2029-12-16",
     "tarjeta de conductor en la misma hoja"),
    (EXTRACT, 39306, 198, "CARNET_CONDUCIR", None, "2022-05-12",
     "2032-05-23", "permiso de conducción en la misma hoja"),
    # Núñez Carmona: su DNI de 2024 lleva en la página 1 el permiso.
    (EXTRACT, 28577, 30, "CARNET_CONDUCIR", [1], "2011-12-21",
     "2021-12-21", "permiso en la página 1 del DNI"),
    # Triviño Benítez: habilitación de operador de grúa móvil
    # autopropulsada, categoría A (Junta, 24/06/2022), en la papelera
    # desde el borrado del árbol antiguo del 31/07.
    (RESTORE, 39202, 190, "CARNET_GRUISTA", None, "2022-06-24",
     "2027-06-23", "habilitación de gruista en la papelera"),
    # Dossiers "DOCUMENTACION ..." tirados por la regla S041 (OCR de
    # EnterpriseBot_042, búsqueda 043, cada página vista a mano). Las
    # habilitaciones de gruista de la Junta valen 5 años desde la
    # resolución (lo dice su punto SEGUNDO).
    (EXTRACT, 47392, 164, "DNI", [9], "2024-04-12", "2034-04-12",
     "DNI en el dossier de Gutiérrez Mateo Alejandro"),
    (EXTRACT, 47392, 164, "CARNET_CONDUCIR", [11], "2022-05-16",
     "2032-04-27", "permiso de conducción en el mismo dossier"),
    (EXTRACT, 47392, 164, "TARJETA_CUALIF_CONDUCTOR", [12], "2021-10-10",
     "2026-10-10", "CAP en el mismo dossier"),
    (EXTRACT, 37301, 74, "TARJETA_CUALIF_CONDUCTOR", [15], "2024-07-14",
     "2029-07-14", "CAP en el dossier de Rebollo"),
    (EXTRACT, 41188, 177, "TACOGRAFO", [3], "2026-02-06", "2031-02-06",
     "tarjeta de conductor en el dossier de Rosas"),
    (EXTRACT, 41188, 177, "TARJETA_CUALIF_CONDUCTOR", [5], "2026-01-18",
     "2031-01-18", "CAP en el dossier de Rosas"),
    (EXTRACT, 42127, 161, "CARNET_GRUISTA", [13, 14, 15], "2022-01-04",
     "2027-01-04", "renovación de gruista A en el dossier de Gómez "
     "Rivero"),
    (EXTRACT, 43251, 152, "CARNET_GRUISTA", [10, 11], "2026-06-15",
     "2031-06-15", "renovación de gruista B de junio de 2026"),
    (EXTRACT, 43088, 157, "CARNET_GRUISTA", [11, 12, 13], "2024-06-26",
     "2029-06-26", "renovación de gruista A de junio de 2024"),
    (EXTRACT, 41185, 168, "CARNET_GRUISTA", [11, 12, 13], "2024-01-05",
     "2029-01-05", "renovación de gruista B de enero de 2024"),
    (EXTRACT, 43977, 39, "CARNET_GRUISTA", [13, 14, 15, 16], "2021-09-27",
     "2026-09-27", "renovación de gruista torre de 2021"),
    (EXTRACT, 37080, 175, "CARNET_GRUISTA", [16, 17, 18], "2018-11-19",
     "2023-11-19", "habilitación de gruista B de 2018"),
)


class Command(BaseCommand):
    help = (
        "S127: saca a la luz documentos esenciales escondidos en "
        "dossiers (lista cerrada verificada). Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", default="")

    def _log(self, text):
        line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"),
                            text)
        self.stdout.write(line)
        self.stdout.flush()
        if self._handle:
            self._handle.write(line + "\n")
            self._handle.flush()

    def handle(self, *args, **options):
        apply = options["apply"]
        self._handle = (
            open(options["log_file"], "a", encoding="utf-8")
            if options["log_file"] else None
        )
        try:
            self._run(apply)
        finally:
            if self._handle:
                self._handle.close()

    def _run(self, apply):
        self._log("# [S127] Documentos escondidos en dossiers -- %s, %d "
                  "caso(s)." % ("APLICANDO" if apply else "MODO PRUEBA",
                               len(CASES)))
        counts = {"hecho": 0, "ya estaba": 0, "parada": 0}
        for number, case in enumerate(CASES, 1):
            outcome = self._case(number, case, apply)
            counts[outcome] += 1
        self._log("# [S127] Fin. Hechos: %d, ya estaban: %d, paradas: %d."
                  % (counts["hecho"], counts["ya estaba"],
                     counts["parada"]))

    def _case(self, number, case, apply):
        action, source_pk, person_pk, code, pages, issue, expiry, note = (
            case
        )
        issue = dossier_service.parse_date(issue)
        expiry = dossier_service.parse_date(expiry)
        source = DocumentIndexEntry.objects.filter(pk=source_pk).first()
        person = PersonIdentity.objects.filter(pk=person_pk).first()
        document_type = dossier_service.person_type(code)
        head = "%d/%d %s #%s -> %s (%s), %s: %s" % (
            number, len(CASES), action, source_pk,
            person or person_pk, code, expiry or issue, note,
        )
        if not source or not person or not document_type:
            self._log("%s -- [PARADA] falta el archivo, la persona o el "
                      "tipo." % head)
            return "parada"
        if source.purged_at:
            self._log("%s -- [PARADA] el archivo se vació de la papelera."
                      % head)
            return "parada"
        if person.is_active_employee is not True:
            self._log("%s -- [PARADA] la persona no está activa." % head)
            return "parada"

        if action == EXTRACT:
            existing = dossier_service.already_filed(
                person, document_type, expiry, issue,
            )
            if existing is not None:
                self._log("%s -- ya archivado (#%d %s)."
                          % (head, existing.pk, existing.name))
                return "ya estaba"
            if not apply:
                self._log("%s -- se sacaría a un archivo nuevo." % head)
                return "hecho"
            new_entry = dossier_service.extract_document(
                source, person, document_type, pages=pages,
                issue_date=issue, expiry_date=expiry,
            )
            self._log("%s -- [OK] #%d %s" % (head, new_entry.pk,
                                            new_entry.name))
            return "hecho"

        owner_ok = (
            source.domain_object_id == person.pk
            and source.document_type_id == document_type.pk
        )
        if (not source.deleted_at and owner_ok
                and source.expiry_date == expiry):
            self._log("%s -- ya estaba bien (#%d %s)."
                      % (head, source.pk, source.name))
            return "ya estaba"
        if action == RETYPE and source.deleted_at:
            self._log("%s -- [PARADA] está en la papelera; el caso es de "
                      "RETIPAR un archivo vivo." % head)
            return "parada"
        plan = file_entry_manually(
            source, person, code,
            date_hint=(expiry or issue).isoformat() if expiry or issue
            else "",
        )
        if plan["reason"]:
            self._log("%s -- [PARADA] %s." % (head, plan["reason"]))
            return "parada"
        if not apply:
            self._log("%s -- quedaría %s/%s." % (
                head, plan["new_parent_path"], plan["new_name"]))
            return "hecho"
        if source.deleted_at:
            source.deleted_at = None
            source.deleted_by = None
            source.save(update_fields=["deleted_at", "deleted_by"])
        file_entry_manually(
            source, person, code,
            date_hint=(expiry or issue).isoformat() if expiry or issue
            else "", apply_changes=True,
        )
        source.refresh_from_db()
        source.issue_date = issue
        source.expiry_date = expiry if document_type.tracks_expiry else None
        source.is_obsolete = False
        source.save(update_fields=["issue_date", "expiry_date",
                                   "is_obsolete"])
        self._log("%s -- [OK] #%d %s/%s" % (head, source.pk,
                                           source.parent_path, source.name))
        return "hecho"
