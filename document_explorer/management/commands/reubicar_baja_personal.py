# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reubicar_baja_personal.py
"""
H30 (S68) -- `DOC. PERSONAL/PERSONAL/BAJAS/BAJA PERSONAL/<persona>/...`
son partes de incapacidad laboral transitoria (ILT), NO bajas
contractuales (ver `trash_contractual_bajas.py` para esas). Miguel
Angel, verbatim: "baja personal son incapacidades laborales
transitorias [...] tienen que ir los documentos a su operario."

Dato real de S68: de 54 carpetas de persona, solo 3 tenian ya carpeta
viva en `OPERARIOS/` y 2 mas correspondian a activos reales del Excel
sin carpeta creada todavia. Las otras 49 (1055 archivos) NO son
activos -- Miguel Angel, verbatim, decision final: "Reubicar y regla
universal" -- es decir, a estas 5 personas activas se les reubica el
ILT en su carpeta; al resto se le aplica la misma regla universal ya
usada en `trash_contractual_bajas.py` (fuera de los 70 activos ->
papelera).

Caso especial confirmado a mano en S68 (nunca automatizar esto de
nuevo): la carpeta "SANCHEZ GARCIA" (sin nombre de pila, 1 archivo)
coincidia por subconjunto de tokens con el activo GARCIA SANCHEZ
ISMAEL (pk=147), pero el archivo real dentro decia "SANCHEZ GARCIA,
JUAN ANT..pdf" -- es la misma persona que la carpeta gemela "SANCHEZ
GARCIA JUAN ANTONIO (GR)" (13 archivos, ya en el grupo sin activo),
no Ismael. Se fuerza a papelera aqui, verificado contra el archivo
real, no contra el solapamiento de tokens.

Reubicacion: `move_service.move_entries()` (escritura de indice pura,
`blob_name` intacto). Si la persona no tiene carpeta ya creada en
`OPERARIOS/` pero es un activo real del Excel, se crea la carpeta
(mismo nombre que traia en BAJA PERSONAL) -- `ensure_folder_chain`
dentro de `move_entries`/`move_entry` se encarga.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
import re

from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.classification_service import _resolve_dossier_trash_user
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_explorer.move_service import move_entries

ROOT_BP = "DOC. PERSONAL/PERSONAL/BAJAS/BAJA PERSONAL/"
ROOT_OPERARIOS = "DOC. PERSONAL/PERSONAL/OPERARIOS"

# Confirmado a mano en S68 contra el archivo real -- ver docstring.
FORZAR_PAPELERA = {"SANCHEZ GARCIA"}

_BATCH_SIZE = 500
_PAREN_RE = re.compile(r"\([^)]*\)")


def _tokens(texto):
    t = _PAREN_RE.sub(" ", texto)
    t = t.replace(",", " ").replace(".", " ")
    return set(
        w for w in re.split(r"\s+", t.strip().upper())
        if len(w) > 1 and w != "NUEVO"
    )


class Command(BaseCommand):
    help = (
        "H30 (S68) -- reubica BAJA PERSONAL (ILT) a la carpeta del "
        "operario si es activo real (creandola si hace falta), o a "
        "papelera con la regla universal si no lo es. Dry-run por "
        "defecto, --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            parent_path__startswith=ROOT_BP,
        ).only("id", "parent_path", "name")

        por_carpeta = {}
        for entry in qs.iterator():
            resto = entry.parent_path[len(ROOT_BP):]
            carpeta = resto.split("/")[0] if resto else ""
            por_carpeta.setdefault(carpeta, []).append(entry)

        carpetas_operarios = list(
            DocumentIndexEntry.objects.filter(
                bucket="cgs_grupo_alvarez",
                entry_kind=DocumentIndexEntry.KIND_FOLDER,
                deleted_at__isnull=True,
                purged_at__isnull=True,
                parent_path=ROOT_OPERARIOS,
            ).values_list("name", flat=True)
        )
        op_tokens = [(n, _tokens(n)) for n in carpetas_operarios]

        activos = list(
            PersonIdentity.objects.filter(is_active_employee=True)
            .values_list("id", "first_surname", "second_surname", "given_name")
        )
        activos_tokens = []
        for pk, fs, ss, gn in activos:
            full = "%s %s %s" % (fs, ss or "", gn)
            activos_tokens.append((pk, full.strip(), _tokens(full)))

        totales = {"reubicados": 0, "a_papelera": 0, "fallos": 0, "carpetas_movidas": 0}
        pks_a_papelera = []
        movimientos = []  # (carpeta_origen, destino, entries)
        carpetas_papelera = 0

        for carpeta, entries in sorted(por_carpeta.items(), key=lambda x: -len(x[1])):
            if carpeta in FORZAR_PAPELERA:
                self.stdout.write(
                    "PAPELERA (forzado a mano, ver docstring): %s (%d archivos)"
                    % (carpeta, len(entries))
                )
                pks_a_papelera.extend(e.pk for e in entries)
                carpetas_papelera += 1
                continue

            t = _tokens(carpeta)
            en_operarios = [n for n, at in op_tokens if at and t.issubset(at)]
            if len(en_operarios) == 1:
                destino = ROOT_OPERARIOS + "/" + en_operarios[0]
                self.stdout.write(
                    "REUBICAR: %s (%d archivos) -> %s"
                    % (carpeta, len(entries), destino)
                )
                movimientos.append((carpeta, destino, entries))
                continue

            en_activos = [(pk, full) for pk, full, at in activos_tokens if at and t.issubset(at)]
            if len(en_activos) == 1:
                destino = ROOT_OPERARIOS + "/" + carpeta
                self.stdout.write(
                    "REUBICAR (carpeta nueva, activo %s): %s (%d archivos) -> %s"
                    % (en_activos[0][1], carpeta, len(entries), destino)
                )
                movimientos.append((carpeta, destino, entries))
                continue

            self.stdout.write(
                "PAPELERA (regla universal, fuera de los 70 activos): %s (%d archivos)"
                % (carpeta, len(entries))
            )
            pks_a_papelera.extend(e.pk for e in entries)
            carpetas_papelera += 1

        if apply_changes:
            for carpeta, destino, entries in movimientos:
                try:
                    move_entries(entries, destino)
                    totales["reubicados"] += len(entries)
                    totales["carpetas_movidas"] += 1
                except Exception:
                    totales["fallos"] += len(entries)
                    self.stdout.write("FALLO AL MOVER: %s -> %s" % (carpeta, destino))

            if pks_a_papelera:
                admin = _resolve_dossier_trash_user()
                if admin is None:
                    self.stdout.write(
                        "FALLO GLOBAL: no se pudo resolver el CompanyUser "
                        "admin de papelera -- nada aplicado, %d pendientes."
                        % len(pks_a_papelera)
                    )
                    totales["fallos"] += len(pks_a_papelera)
                else:
                    ahora = timezone.now()
                    for i in range(0, len(pks_a_papelera), _BATCH_SIZE):
                        lote = pks_a_papelera[i:i + _BATCH_SIZE]
                        n = DocumentIndexEntry.objects.filter(pk__in=lote).update(
                            deleted_at=ahora, deleted_by=admin,
                        )
                        totales["a_papelera"] += n

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self.stdout.write("    carpetas a reubicar: %d (%d archivos)" % (
            len(movimientos), sum(len(e) for _, _, e in movimientos)
        ))
        self.stdout.write("    carpetas a papelera: %d (%d archivos)" % (
            carpetas_papelera, len(pks_a_papelera)
        ))
        for key, value in totales.items():
            self.stdout.write("    %s: %d" % (key, value))
