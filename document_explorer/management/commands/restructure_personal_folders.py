# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/restructure_personal_folders.py
"""
H31 (S99) -- reorganizacion de la estructura de carpetas VIRTUALES del
dominio PERSONAL para que refleje la clasificacion real de BD en vez
de la organizacion historica heredada del cubo. Instruccion explicita
de Miguel Angel al cierre de S98.

Estructura nueva, verbatim del anexo H31, corregida en la misma
sesion (S99) tras feedback explicito de Miguel Angel sobre ACTIVOS:
- DOC. PERSONAL/PERSONAL/ACTIVOS/{EMPRESA}/{PRIMER_APELLIDO}_
  {SEGUNDO_APELLIDO}_{NOMBRE}/ -- is_active_employee=True, subdividido
  por empresa real (`PersonIdentity.employer_company`, refrescado
  desde el Excel real via `import_worker_machine_excel`, NUNCA
  fusionando variantes de texto -- "TRANSGRUAL SL" y "TRANSGRUAL
  S.L." son carpetas distintas a proposito, decision explicita de
  Miguel Angel: la normalizacion real vive en el Excel, no se inventa
  aqui). Caso especial confirmado por Miguel Angel: la familia
  ALVAREZ DIAZ (5 personas, dueños de la empresa, sin
  employer_company en el Excel porque no son plantilla) va a
  `GERENCIA` en vez de a una carpeta de empresa.
- DOC. PERSONAL/PERSONAL/INACTIVOS/{...}/ -- mismo criterio para
  is_active_employee=False, SIN subdivision por empresa -- decision
  explicita de Miguel Angel ("Sólo a ACTIVOS"). Confirmado con datos
  reales (Comando S, S99): 0 PersonIdentity en is_active_employee=
  None sobre 229 totales -- la regla por defecto de la hoja de ruta
  para el caso None no aplica, no hay ningun caso real.
- DOC. PERSONAL/PERSONAL/EPIS/ -- carpeta unica y compartida (no una
  por persona) para las fichas tecnicas de EPI reales
  (DocumentTypeCatalog.code == "FICHA_TECNICA_EPI"), confirmadas por
  Miguel Angel en S98 como documentacion real, no un registro
  transaccional (eso ya vive en EpiDelivery).

El nombre de carpeta de cada persona se construye con
`naming_service.build_person_folder_name()`, y el de cada empresa con
`naming_service.build_company_folder_name()` (misma normalizacion --
acentos fuera, mayusculas, guion bajo -- que los nombres de archivo
PERSONAL, para que carpeta y archivo salgan siempre de la misma
regla).

**Correccion real S99, tras el primer dry-run:** el movimiento NO se
hace por `PersonIdentity.folder_path` (ese campo solo refleja donde
aterriza un archivo NUEVO resuelto por `apply_quarantine_classification`,
nunca se usa para relocar documentos ya existentes -- el renombrado
canonico de S98, `apply_personal_canonical_rename()`, cambia
unicamente `entry.name`, jamas `parent_path`). Dry-run real (S99):
solo 5.284 de los 8.358 documentos con `domain_object` de tipo
`PersonIdentity` vivian bajo el `folder_path` de su persona -- el
resto (3.074) vive disperso en sus ubicaciones historicas originales
del cubo. El propio anexo ya fija el criterio real de pertenencia:
"documentos con `domain_object` de tipo `PersonIdentity`" -- no
`folder_path`. Por eso este comando mueve, por cada persona, TODOS
los `DocumentIndexEntry` vivos cuyo `domain_content_type`/
`domain_object_id` apunten a su `PersonIdentity`, sea cual sea su
`parent_path` actual, via `move_service.move_entries()` (lote
eficiente a un unico destino, pensado exactamente para esto -- a
diferencia de `merge_folders()`, que asume un unico subarbol origen
con profundidad relativa a conservar, aqui los documentos de una
persona estan dispersos en carpetas sin relacion entre si, así que
aterrizan todos DIRECTAMENTE en la carpeta de la persona, sin
subcarpetas). Mismo contrato "solo virtual" que el resto del modulo:
`blob_name`/GCS nunca se tocan, solo `parent_path`/`name` en base de
datos, con renombrado ordinal automatico si dos documentos de la
misma persona colisionan de nombre en el destino.

Colisiones ENTRE PERSONAS (dos PersonIdentity distintas cuyo nombre
canonico de carpeta coincidiria en la misma categoria/empresa) se
resuelven con un ordinal propio de este comando (`_2`, `_3`...
anadido al nombre de carpeta, orden estable por DNI) -- nunca visto
todavia sobre datos reales a fecha de escribir esto, pero el codigo
no asume que no pueda pasar.

DRY-RUN POR DEFECTO. Con --apply escribe y mueve de verdad. En
dry-run nunca se llama a `move_entries()` (esa funcion siempre
escribe de verdad, no tiene modo de simulacion propio) -- se cuenta
por separado cuantos documentos tiene cada persona por `domain_object`
real.

Verboso por diseno (`com-standards` 0bis/0ter): heartbeat con ETA
cada 10 elementos procesados (229 personas, ~5% del total).
"""
import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_explorer.move_service import move_entries, move_entry
from document_explorer import naming_service

PERSONAL_ROOT = "DOC. PERSONAL/PERSONAL"
ACTIVOS_ROOT = "%s/ACTIVOS" % PERSONAL_ROOT
INACTIVOS_ROOT = "%s/INACTIVOS" % PERSONAL_ROOT
EPIS_FOLDER = "%s/EPIS" % PERSONAL_ROOT
FICHA_TECNICA_EPI_CODE = "FICHA_TECNICA_EPI"

# H31 (S99). Familia propietaria confirmada por Miguel Angel --
# ACTIVOS/GERENCIA en vez de una carpeta de empresa, precisamente
# porque no son plantilla y por eso el Excel nunca les rellena
# employer_company. Match por apellidos exactos (normalizados),
# nunca por lista fija de DNI -- cualquier PersonIdentity futura con
# estos mismos dos apellidos entra en la misma regla, sin tocar este
# comando.
GERENCIA_FOLDER_NAME = "GERENCIA"
GERENCIA_FIRST_SURNAME = "ALVAREZ"
GERENCIA_SECOND_SURNAME = "DIAZ"

# H31 (S99). Fallback defensivo -- no deberia ocurrir tras resolver
# los 5 de GERENCIA y refrescar employer_company desde el Excel real,
# pero el comando nunca debe fallar ni inventar una empresa si algun
# activo futuro llega sin ninguna de las dos condiciones resueltas.
SIN_EMPRESA_FOLDER_NAME = "SIN_EMPRESA"

# com-standards, seccion 0bis: N=25 o el 5% del total, lo que sea
# menor. Con 229 personas, el 5% real es el valor menor.
HEARTBEAT_EVERY = 10


class Command(BaseCommand):
    help = (
        "H31 (S99) -- reorganiza las carpetas virtuales de PERSONAL "
        "a ACTIVOS/{EMPRESA|GERENCIA}, INACTIVOS y EPIS segun "
        "clasificacion real de BD. Dry-run por defecto, --apply para "
        "escribir y mover de verdad."
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

    def _category_root_for(self, identity):
        if not identity.is_active_employee:
            return INACTIVOS_ROOT

        is_gerencia = (
            identity.first_surname.strip().upper() == GERENCIA_FIRST_SURNAME
            and identity.second_surname.strip().upper()
            == GERENCIA_SECOND_SURNAME
        )
        if is_gerencia:
            return "%s/%s" % (ACTIVOS_ROOT, GERENCIA_FOLDER_NAME)

        if identity.employer_company:
            empresa_folder = naming_service.build_company_folder_name(
                identity.employer_company,
            )
            return "%s/%s" % (ACTIVOS_ROOT, empresa_folder)

        self.stdout.write(
            "AVISO: dni=%s activo sin employer_company y sin coincidir "
            "con GERENCIA -- asignado a %s/%s, revisar dato real."
            % (identity.dni, ACTIVOS_ROOT, SIN_EMPRESA_FOLDER_NAME)
        )
        return "%s/%s" % (ACTIVOS_ROOT, SIN_EMPRESA_FOLDER_NAME)

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        bucket = PRIMARY_BUCKET
        person_ct = ContentType.objects.get_for_model(PersonIdentity)

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

            category_root = self._category_root_for(identity)
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
            plan.append((identity, new_folder_path))

        # --- Paso 2: ejecutar (o simular) el movimiento por persona,
        # SIEMPRE por domain_object real (nunca por folder_path -- ver
        # docstring del modulo, correccion S99). ---
        stats = {
            "personas_con_documentos": 0, "personas_sin_documentos": 0,
            "documentos_movidos": 0,
        }
        start_time = datetime.datetime.now()
        procesados = 0

        for identity, new_folder_path in plan:
            procesados += 1
            person_entries = list(
                DocumentIndexEntry.objects.filter(
                    bucket=bucket,
                    domain_content_type=person_ct,
                    domain_object_id=identity.pk,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    deleted_at__isnull=True, purged_at__isnull=True,
                )
            )
            if not person_entries:
                stats["personas_sin_documentos"] += 1
            else:
                stats["personas_con_documentos"] += 1
                if apply_changes:
                    results = move_entries(person_entries, new_folder_path)
                    moved_count = len(results)
                    identity.folder_path = new_folder_path
                    identity.save(
                        update_fields=["folder_path", "updated_at"],
                    )
                else:
                    moved_count = len(person_entries)
                stats["documentos_movidos"] += moved_count
                self.stdout.write(
                    "%s  dni=%s  -> %s  (%d documento(s) por domain_object)"
                    % (
                        "MOVIDA" if apply_changes else "CANDIDATA",
                        identity.dni, new_folder_path, moved_count,
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
                    "(fin aprox. %s) -- personas_con_documentos=%d "
                    "documentos_movidos=%d"
                    % (
                        datetime.datetime.now().strftime("%H:%M:%S"),
                        procesados, total_personas, pct,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        stats["personas_con_documentos"],
                        stats["documentos_movidos"],
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
