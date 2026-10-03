# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/file_sweep_no_conformes_s127.py
"""
H30 (S127). Human review of the NO CONFORMES left by the DOC. PERSONAL
sweep, applied.

---

H30 (S127). Aplica la revisión de los 50 NO CONFORMES de la pasada de
DOC. PERSONAL (requeue_unfed_personal_s127), aprobada por Miguel Ángel
letra a letra (A-E). Los dudosos se abrieron por su primera página.

- EMPRESA: documento de empresa con su tipo, archivado por el mismo
  camino que el H28 (`_apply_company_classification`).
- CARPETA: movimiento virtual sin tipo (subcontratas, control...).
- FICHA: a la ficha de su persona (`file_entry_manually`).
- PAPELERA: sin contenido útil.

Lo de la letra E (comprimidos, .docx que LibreOffice no convierte,
.html y .xml) no está aquí: se resuelve en el pipeline. Sin --apply
solo informa; idempotente (solo toca lo que sigue en NO CONFORMES).
"""
from django.core.management.base import BaseCommand

from document_explorer.buckets import COMPANY_ROOT, PRIMARY_BUCKET
from document_explorer.classification_service import (
    _apply_company_classification, file_entry_manually,
    resolve_duplicate_of_filed_document, trash_dossier_entry,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_explorer.move_service import move_entries

SUBCONTRACTORS = COMPANY_ROOT + "/SUBCONTRATAS"

# pk -> (tipo, fecha) -- documentos de empresa con tipo.
COMPANY = {
    # A: listados oficiales de la Junta (admitidos / aprobados).
    24642: ("LISTADO_EXAMEN_OFICIAL", ""),
    24643: ("LISTADO_EXAMEN_OFICIAL", ""),
    24668: ("LISTADO_EXAMEN_OFICIAL", "2022-01-24"),
    24669: ("LISTADO_EXAMEN_OFICIAL", ""),
    24800: ("LISTADO_EXAMEN_OFICIAL", ""),
    24825: ("LISTADO_EXAMEN_OFICIAL", ""),
    24839: ("LISTADO_EXAMEN_OFICIAL", ""),
    24844: ("LISTADO_EXAMEN_OFICIAL", ""),
    24845: ("LISTADO_EXAMEN_OFICIAL", ""),
    24864: ("LISTADO_EXAMEN_OFICIAL", ""),
    24865: ("LISTADO_EXAMEN_OFICIAL", ""),
    # C: material genérico de PRL y relaciones laborales.
    23094: ("MATERIAL_FORMACION", "2020-04-13"),   # cartel COVID
    23500: ("MATERIAL_FORMACION", "2012-12-01"),   # guía EPI INSHT
    35719: ("MATERIAL_FORMACION", ""),             # temario primeros auxilios
    52207: ("MATERIAL_FORMACION", "2026-04-28"),   # plan calor 2026
    23496: ("PLANTILLA", "2007-08-01"),            # Leave Letter ANAGRUAL
    21962: ("DECLARACION_EMPRESA", "2014-12-16"),  # representante trabajadores
}

# pk -> carpeta (movimiento virtual, sin tipo).
MOVES = {
    # B: máquinas de un autónomo subcontratado (no son de la flota).
    28675: SUBCONTRACTORS + "/GOMEZ CARVAJAL",   # ITV camión 9314DSC
    28678: SUBCONTRACTORS + "/GOMEZ CARVAJAL",   # cambio titularidad
    28683: SUBCONTRACTORS + "/GOMEZ CARVAJAL",   # cert. mantenimiento
    28684: SUBCONTRACTORS + "/GOMEZ CARVAJAL",   # manual JCB
    28691: SUBCONTRACTORS + "/GOMEZ CARVAJAL",   # papeles minicargadora
    # B: empresa.
    36683: SUBCONTRACTORS,                       # autorización Elecnor
    25247: COMPANY_ROOT + "/FORMACION",          # presupuesto FLC
    34034: COMPANY_ROOT + "/RELACIONES LABORALES",  # control vencimientos
}

# pk -> (persona pk, tipo, fecha).
PERSONAL = [
    (36277, 168, "EMBARGO_SALARIO", "2018-02-06"),
    (36278, 168, "EMBARGO_SALARIO", "2018-02-16"),
    (36280, 168, "EMBARGO_SALARIO", "2021-03-04"),
    (37953, 190, "CERTIFICADO_MATRIMONIO", ""),
    (43112, 224, "JUSTIFICANTE_ACOMPANAMIENTO", "2026-08-25"),
    (35917, 164, "JUSTIFICANTE_ACOMPANAMIENTO", "2025-10-22"),
    (35051, 3, "INFORME_MEDICO", ""),
    (40280, 191, "CERTIFICADO_BANCARIO", ""),
    # D: abiertos a mano.
    (35128, 3, "CERTIFICADO_GIBRALTAR", "2017-04-18"),
    (35617, 159, "DNI", "2035-03-15"),
    (34656, 153, "TARJETA_CUALIF_CONDUCTOR", "2026-07-02"),
    (39451, 259, "CARNET_GRUISTA", "2016-01-24"),
    (38572, 194, "FORMACION", ""),
]

TRASH = {35461, 38142}   # Word de una línea; .msg con solo la cabecera


def _live(pk):
    entry = DocumentIndexEntry.objects.filter(
        pk=pk, bucket=PRIMARY_BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).first()
    if entry is None or not (entry.parent_path or "").startswith(
        "NO CONFORMES",
    ):
        return None
    return entry


class Command(BaseCommand):
    help = (
        "S127: aplica la revisión de los NO CONFORMES de la pasada de DOC. "
        "PERSONAL. Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def _say(self, text):
        self.stdout.write(text)

    def handle(self, *args, **options):
        apply = options["apply"]
        self._say("# [S127] NO CONFORMES de la pasada -- %s" % (
            "APLICANDO" if apply else "MODO PRUEBA (sin --apply)"))
        done = skipped = 0

        self._say("1. Empresa con tipo:")
        for pk, (code, date_hint) in COMPANY.items():
            entry = _live(pk)
            if entry is None:
                skipped += 1
                continue
            self._say("   - pk=%s %s -> %s" % (pk, entry.name, code))
            if apply:
                outcome = _apply_company_classification(entry, {
                    "document_type_code": code, "date_hint": date_hint,
                })
                if not outcome.get("classified"):
                    self._say("     [ERROR] no se pudo archivar.")
                    continue
                self._say("     -> %s/%s" % (
                    outcome["new_parent_path"], outcome["new_name"]))
            done += 1

        self._say("2. A carpeta:")
        groups = {}
        for pk, destination in MOVES.items():
            entry = _live(pk)
            if entry is None:
                skipped += 1
                continue
            self._say("   - pk=%s %s -> %s" % (pk, entry.name, destination))
            groups.setdefault(destination, []).append(entry)
            done += 1
        if apply:
            for destination, entries in groups.items():
                move_entries(entries, destination)

        self._say("3. A su ficha:")
        people = {p.pk: p for p in PersonIdentity.objects.filter(
            pk__in={row[1] for row in PERSONAL})}
        for pk, person_pk, code, date_hint in PERSONAL:
            entry = _live(pk)
            person = people.get(person_pk)
            if entry is None or person is None:
                skipped += 1
                continue
            if apply and resolve_duplicate_of_filed_document(entry):
                self._say("   - pk=%s copia exacta -> papelera." % pk)
                trash_dossier_entry(entry)
                done += 1
                continue
            outcome = file_entry_manually(
                entry, person, code, date_hint, apply_changes=apply,
            )
            if outcome["reason"]:
                skipped += 1
                self._say("   - pk=%s [SALTADO] %s" % (pk, outcome["reason"]))
                continue
            done += 1
            self._say("   - pk=%s -> %s/%s" % (
                pk, outcome["new_parent_path"], outcome["new_name"]))

        self._say("4. Papelera:")
        for pk in sorted(TRASH):
            entry = _live(pk)
            if entry is None:
                skipped += 1
                continue
            self._say("   - pk=%s %s" % (pk, entry.name))
            if apply:
                trash_dossier_entry(entry)
            done += 1

        self._say("# [S127] Fin. Hechos: %d. Saltados: %d." % (done, skipped))
