# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/restructure_personal_folders.py
"""
H31 (S99) -- reorganizacion de la estructura de carpetas VIRTUALES del
dominio PERSONAL para que refleje la clasificacion real de BD en vez
de la organizacion historica heredada del cubo. Instruccion explicita
de Miguel Angel al cierre de S98.

Estructura nueva, verbatim del anexo H31:
- DOC. PERSONAL/PERSONAL/ACTIVOS/{PRIMER_APELLIDO}_{SEGUNDO_APELLIDO}_
  {NOMBRE}/ -- un PersonIdentity real por carpeta, is_active_employee
  =True, con toda su documentacion dentro.
- DOC. PERSONAL/PERSONAL/INACTIVOS/{...}/ -- mismo criterio para
  is_active_employee=False. Confirmado con datos reales (Comando S,
  S99): 0 PersonIdentity en is_active_employee=None sobre 229 totales
  (80 activos, 149 inactivos) -- la regla por defecto de la hoja de
  ruta para el caso None no aplica, no hay ningun caso real.
- DOC. PERSONAL/PERSONAL/EPIS/ -- carpeta unica y compartida (no una
  por persona) para las fichas tecnicas de EPI reales
  (DocumentTypeCatalog.code == "FICHA_TECNICA_EPI"), confirmadas por
  Miguel Angel en S98 como documentacion real, no un registro
  transaccional (eso ya vive en EpiDelivery).

El nombre de carpeta de cada persona se construye con
`naming_service.build_person_folder_name()` (misma normalizacion --
acentos fuera, mayusculas, guion bajo -- que los nombres de archivo
PERSONAL, para que carpeta y archivo salgan siempre de la misma
regla). El movimiento real de documentos reutiliza
`move_service.merge_folders()` (H29, S043): mueve todo archivo vivo
bajo la carpeta ANTIGUA de la persona a la carpeta NUEVA, preservando
la profundidad relativa (una foto de carnet en una subcarpeta anidada
de la persona aterriza en la misma subcarpeta relativa dentro de
ACTIVOS/INACTIVOS, nunca aplanada), con renombrado ordinal automatico
si dos archivos colisionan en el mismo destino -- igual contrato
"solo virtual" que el resto del modulo: `blob_name`/GCS nunca se
tocan, solo `parent_path`/`name` en base de datos.

Colisiones ENTRE PERSONAS (dos PersonIdentity distintas cuyo nombre
canonico de carpeta coincidiria en la misma categoria) se resuelven
con un ordinal propio de este comando (`_2`, `_3`... anadido al
nombre de carpeta, orden estable por DNI) -- nunca visto todavia
sobre datos reales a fecha de escribir esto, pero el codigo no asume
que no pueda pasar.

DRY-RUN POR DEFECTO. Con --apply escribe y mueve de verdad. En
dry-run nunca se llama a `merge_folders()` (esa funcion siempre
escribe de verdad, no tiene modo de simulacion propio) -- se cuenta
por separado cuantos archivos viven hoy bajo la carpeta antigua de
cada persona, via el mismo filtro que `merge_folders()` usaria.

Verboso por diseno (`com-standards` 0bis/0ter): heartbeat con ETA
cada 10 elementos procesados (229 personas, ~5% del total).
"""
import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_explorer.move_service import merge_folders, move_entry
from document_explorer import naming_service

PERSONAL_ROOT = "DOC. PERSONAL/PERSONAL"
ACTIVOS_ROOT = "%s/ACTIVOS" % PERSONAL_ROOT
INACTIVOS_ROOT = "%s/INACTIVOS" % PERSONAL_ROOT
EPIS_FOLDER = "%s/EPIS" % PERSONAL_ROOT
FICHA_TECNICA_EPI_CODE = "FICHA_TECNICA_EPI"

# com-standards, seccion 0bis: N=25 o el 5% del total, lo que sea
# menor. Con 229 personas, el 5% real es el valor menor.
HEARTBEAT_EVERY = 10


class Command(BaseCommand):
    help = (
        "H31 (S99) -- reorganiza las carpetas virtuales de PERSONAL "
        "a ACTIVOS/INACTIVOS/EPIS segun clasificacion real de BD. "
        "Dry-run por defecto, --apply para escribir y mover de "
        "verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe y mueve de verdad. Sin esta flag, solo informa.",
        )

    def _folder_name_for(self, identity):
        return naming_service.build_person_folder_name(
            identity.first_surname, identity.second_surname,
            identity.given_name,
        )

    def _count_files_under(self, bucket, folder_path):
        return DocumentIndexEntry.objects.filter(
            bucket=bucket,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(
            Q(parent_path=folder_path)
            | Q(parent_path__startswith=folder_path + "/"),
        ).count()

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        bucket = PRIMARY_BUCKET

        identities = list(PersonIdentity.objects.order_by("dni"))
        total_personas = len(identities)

        self.stdout.write(
            "=== INICIO (%s) -- %d PersonIdentity en alcance ==="
            % (
                "APLICADO" if apply_changes else "DRY-RUN, nada escrito",
                total_personas,
            )
        )

        # --- Paso 1: calcular la ruta nueva de cada persona y
        # detectar colisiones ENTRE personas antes de tocar nada. ---
        plan = []
        seen_paths = {}
        for identity in identities:
            if identity.is_active_employee is None:
                # No deberia ocurrir -- confirmado 0/229 en S99 -- pero
                # si aparece uno nuevo despues de esta sesion, se dej
                # a fuera de alcance en vez de adivinar, nunca se
                # fuerza a ACTIVOS/INACTIVOS sin dato real.
                self.stdout.write(
                    "AVISO: PersonIdentity dni=%s sin is_active_employee "
                    "resuelto -- se deja FUERA de alcance de este "
                    "comando, revision manual." % identity.dni
                )
                continue

            category_root = (
                ACTIVOS_ROOT if identity.is_active_employee
                else INACTIVOS_ROOT
            )
            base_name = self._folder_name_for(identity)
            final_name = base_name
            ordinal = 2
            while (category_root, final_name) in seen_paths:
                final_name = "%s_%d" % (base_name, ordinal)
                ordinal += 1
            seen_paths[(category_root, final_name)] = identity.dni

            if final_name != base_name:
                self.stdout.write(
                    "COLISION DE CARPETA: dni=%s -- nombre base %s ya "
                    "usado por dni=%s, asignado %s"
                    % (
                        identity.dni, base_name,
                        seen_paths.get((category_root, base_name), "?"),
                        final_name,
                    )
                )

            new_folder_path = "%s/%s" % (category_root, final_name)
            old_folder_path = identity.folder_path.strip("/")
            plan.append((identity, old_folder_path, new_folder_path))

        # --- Paso 2: ejecutar (o simular) el movimiento por persona. ---
        stats = {"movidas": 0, "sin_cambio": 0, "archivos_movidos": 0}
        start_time = datetime.datetime.now()
        procesados = 0

        for identity, old_folder_path, new_folder_path in plan:
            procesados += 1
            if old_folder_path == new_folder_path:
                stats["sin_cambio"] += 1
            else:
                if apply_changes:
                    results, _removed = merge_folders(
                        bucket, old_folder_path, new_folder_path,
                    )
                    moved_count = len(results)
                    identity.folder_path = new_folder_path
                    identity.save(
                        update_fields=["folder_path", "updated_at"],
                    )
                else:
                    moved_count = self._count_files_under(
                        bucket, old_folder_path,
                    )
                stats["movidas"] += 1
                stats["archivos_movidos"] += moved_count
                self.stdout.write(
                    "%s  dni=%s  %s -> %s  (%d archivo(s))"
                    % (
                        "MOVIDA" if apply_changes else "CANDIDATA",
                        identity.dni, old_folder_path, new_folder_path,
                        moved_count,
                    )
                )

            if procesados % HEARTBEAT_EVERY == 0 or procesados == total_personas:
                elapsed = (
                    datetime.datetime.now() - start_time
                ).total_seconds()
                eta_seg = (
                    (elapsed / procesados) * (total_personas - procesados)
                    if procesados else 0
                )
                hora_fin = (
                    datetime.datetime.now()
                    + datetime.timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                pct = int(procesados * 100 / total_personas) if total_personas else 100
                self.stdout.write(
                    "[%s] Progreso: %d/%d (%d%%) -- ETA %dm%02ds "
                    "(fin aprox. %s) -- movidas=%d archivos_movidos=%d"
                    % (
                        datetime.datetime.now().strftime("%H:%M:%S"),
                        procesados, total_personas, pct,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        stats["movidas"], stats["archivos_movidos"],
                    )
                )

        # --- Paso 3: FICHA_TECNICA_EPI -> carpeta unica EPIS. ---
        self.stdout.write("--- FICHA_TECNICA_EPI -> %s ---" % EPIS_FOLDER)
        ficha_epi_entries = list(
            DocumentIndexEntry.objects.filter(
                document_type__code=FICHA_TECNICA_EPI_CODE,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
            ).order_by("id")
        )
        epis_movidas = 0
        for entry in ficha_epi_entries:
            if entry.parent_path == EPIS_FOLDER:
                self.stdout.write(
                    "id=%d %s -- ya en %s, sin cambio"
                    % (entry.pk, entry.name, EPIS_FOLDER)
                )
                continue
            self.stdout.write(
                "%s  id=%d  %s (parent actual: %s)"
                % (
                    "MOVIDA" if apply_changes else "CANDIDATA",
                    entry.pk, entry.name, entry.parent_path,
                )
            )
            if apply_changes:
                move_entry(entry, EPIS_FOLDER)
            epis_movidas += 1

        # --- Paso 4: verificacion de cierre del Punto 1. ---
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        fuera_de_estructura = DocumentIndexEntry.objects.filter(
            domain_content_type=person_ct,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).exclude(
            Q(parent_path=ACTIVOS_ROOT)
            | Q(parent_path__startswith=ACTIVOS_ROOT + "/")
            | Q(parent_path=INACTIVOS_ROOT)
            | Q(parent_path__startswith=INACTIVOS_ROOT + "/")
            | Q(parent_path=EPIS_FOLDER)
            | Q(parent_path__startswith=EPIS_FOLDER + "/"),
        ).count()

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
        self.stdout.write("    fichas_epi_movidas: %d" % epis_movidas)
        self.stdout.write(
            "    documentos PersonIdentity fuera de "
            "ACTIVOS/INACTIVOS/EPIS: %d" % fuera_de_estructura
        )
