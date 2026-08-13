# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_a_sweep_scoped.py
"""
H30 (S50) -- Fase A restringida al mapa de carpetas confirmado
EXPLICITAMENTE por Miguel Angel, carpeta por carpeta, en esta sesion
-- nunca a la heuristica generica de "cualquier carpeta bajo
DOC. MAQUINAS cuyo nombre resuelva a un codigo de MachineAsset".

Origen real: `run_fase_a_sweep` (S48) recorre TODO `DOC. MAQUINAS`,
lo que arrastra carpetas que no son documentacion de ninguna maquina
concreta (ANAPAT, BALANCIN, CARRETONES DE SEVILLANA, SINIESTROS,
MANTENIMIENTO G.ALVAREZ REALIZADO MONICA LARIO, etc. -- ver anexo
H30, registro de S50). Miguel Angel, verbatim (S50): "Nosotros
tenemos que coger la maquina, la A01, buscar la carpeta [...] Miramos
en la base de datos. Empezamos desde el principio [...] Esos
documentos son los que tenemos que tener apuntalados en la base de
datos en la ficha de la A01. Y ningun otro documento." Recorrido
familia por familia confirmado explicitamente el mismo dia, con el
listado real de subcarpetas delante -- ver SCOPE mas abajo,
literalmente esa conversacion convertida en datos.

SCOPE es la unica fuente de verdad de que carpetas se miran. Cada
entrada es (raiz_familia, modo, lista):
- modo="only": SOLO las subcarpetas nombradas en la lista (match
  exacto de segmento, la subcarpeta y todo lo que cuelgue de ella).
- modo="all_except": TODAS las subcarpetas de la raiz EXCEPTO las
  nombradas en la lista.

Deliberadamente NO usa `resolve_machine_asset()`/
`resolve_or_create_machine_asset()` para decidir el ALCANCE (que
carpetas se miran) -- esas funciones siguen usandose, sin cambios,
solo para resolver a que MachineAsset pertenece un archivo YA dentro
de alcance. La diferencia es sutil pero real: antes, una carpeta como
"OBSOLETO/OBSOLETO P07" podia colarse en el alcance simplemente
porque "P07" con forma de codigo aparecia en el path; ahora ninguna
carpeta fuera de SCOPE se toca, tenga o no forma de codigo de
maquina.

Tres exclusiones anadidas tras el primer dry-run real (S50), a
peticion explicita de Miguel Angel viendo los "TIPO OK, DOMINIO SIN
RESOLVER" reales: "el tema de MK100, carretilla HL, Document...
mujer Adolfo, eso lo dejamos fuera. No lo vamos a meter" -- ninguna
de las tres tiene forma reconocible de codigo de flota ni de
matricula completa (MK 100: prefijo ya retirado, es nombre de
modelo; CARRETILLA (HL): sin numero de flota; DOCUMENT 1884JB:
matricula con solo 2 letras en vez de 3). Revision manual pendiente,
nunca heuristica.

RAE (dentro de Grúas Móviles) y CE PLATAFORMAS (dentro de
Plataformas Z) quedan DENTRO de alcance -- Miguel Angel confirmo
(S50) que el codigo de maquina vive en el propio NOMBRE del archivo
("RAE A-01.pdf", "Z06.pdf"...), nunca en la carpeta contenedora
(compartida por varias/todas las maquinas). Resuelto por
`_resolve_machine_by_filename()` como respaldo, solo cuando la
resolucion normal por carpeta falla.

Reutiliza sin modificar la logica de coincidencia/dosier ya probada
de `heuristic_type_service` (S51, extraida de `run_fase_a_sweep`
donde vivio hasta entonces) -- `resolve_document_type_heuristic`,
`folder_based_type` -- mas `_dossier_types_already_filed` y
`_resolve_person_by_folder` de `run_fase_a_sweep` (este ultimo sin
uso aqui, domain=MACHINE unicamente, confirmado por Miguel Angel:
"Vamos a centrarnos en la maquinaria y luego veremos personal").

DRY-RUN POR DEFECTO. Con --apply escribe de verdad (document_type,
domain_content_type, domain_object_id; papelera para dosieres ya
divididos). Nunca toca GCS (4.12), nunca toca nada fuera de SCOPE.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.classification_service import (
    _FOLDER_MACHINE_CODE_RE, resolve_or_create_machine_asset,
    trash_dossier_entry,
)
from document_explorer.heuristic_type_service import (
    folder_based_type, resolve_document_type_heuristic,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET, _strip_accents,
)
from document_explorer.management.commands.run_fase_a_sweep import (
    _dossier_types_already_filed,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from fleet.models import MachineAsset

MACHINE_ROOT = "DOC. MAQUINAS"

# Confirmado por Miguel Angel, familia por familia, con el listado
# real de subcarpetas delante (S50). Nombres EXACTOS del arbol real,
# nunca aproximados.
SCOPE = [
    (
        "%s/CABEZAS TRACTORAS (P)" % MACHINE_ROOT, "only", [
            "P-14 3232-DLM (TR)", "P-16 9184-FNK (TR)",
            "P-17 MA-7810-DB (AGG)", "P-18 7864-DXZ (TR)",
            "P-19 5083-GRV (TR)", "P-20 0964-GTM (TR)",
            "P-21 2455-CDM (TR)", "P-22 8099-JFK (AGG)",
            "P-23 4884-HNB (TR)", "P-24 8233-CKZ",
            "P-25 2323-FJH (PTE)", "P-26 7585-KHG", "P-27 3860-GLY",
            "SE7625CT VEIASA- CABEZ CON PLUMA",
        ],
    ),
    (
        "%s/CAMIONES BRAZO (B)" % MACHINE_ROOT, "all_except",
        ["PROPUESTA SEGURO CAMION BRAZO", "VEHICULOS DE BAJA"],
    ),
    ("%s/CARRETILLAS (T)" % MACHINE_ROOT, "all_except", ["CARRETILLA (HL)"]),
    (
        "%s/GRUAS MOVILES (A)" % MACHINE_ROOT, "all_except",
        ["OBSOLETO", "PROPUESTA SEGURO", "VEHICULOS BAJA", "MK 100"],
    ),
    (
        "%s/GRUPO ELECTROGENOS" % MACHINE_ROOT, "all_except",
        ["PEPE ASISTENCIA"],
    ),
    (
        "%s/PLATAFORMAS (Z)" % MACHINE_ROOT, "all_except",
        [
            "BAJAS",
            # Anadidas S50 tras revisar el contenido real (ver
            # EnterpriseBot_039_GET.txt): ALTESUR es una empresa de
            # alquiler de maquinaria, no documentacion propia -- "ni
            # lo vamos a mirar". ESTIBA PLATAFORMAS son fichas de
            # procedimiento por CATEGORIA de plataforma (tijera
            # pequena, articulada mediana...), no de una maquina
            # concreta -- "de ahi no vamos a sacar nada". POLIZA RC
            # cubre varias maquinas Z Y T a la vez con una sola
            # poliza colectiva -- Miguel Angel confirmo que el
            # tratamiento correcto seria un "puntero" compartido
            # (mismo patron que MANUALES DE USO, pero por codigo de
            # empresa en vez de por modelo de maquina), no
            # reconciliacion por maquina individual -- diseno futuro,
            # fuera de alcance de esta pasada.
            "ALTESUR", "ESTIBA PLATAFORMAS", "POLIZA RC",
        ],
    ),
    (
        "%s/REMOLQUES Y GONDOLAS (R y G)/GONDOLAS" % MACHINE_ROOT,
        "all_except", ["BAJA DEFINITIVA"],
    ),
    (
        "%s/REMOLQUES Y GONDOLAS (R y G)/REMOLQUES" % MACHINE_ROOT,
        "all_except", ["BAJA"],
    ),
    ("%s/VEHICULOS DE EMPRESA" % MACHINE_ROOT, "all_except", ["DOCUMENT 1884JB (MUJER ADOLFO)"]),
    ("%s/VENTOSA" % MACHINE_ROOT, "all_except", []),
]


def _resolve_machine_by_filename(entry):
    """
    Respaldo de dominio SOLO para archivos bajo RAE (H30, S50): Miguel
    Angel confirmo que el codigo de maquina vive en el propio NOMBRE
    del archivo ("RAE A-01.pdf"), nunca en la carpeta contenedora
    (compartida por todas las maquinas: "RAE", "RAE/SOLICITUD BAJA
    INDUSTRIA"). Mismo patron de deteccion palabra a palabra que
    `resolve_machine_asset()` ya usa sobre `parent_path`, aplicado
    aqui sobre `entry.name` en su lugar. Nunca crea una MachineAsset
    nueva -- solo lookup contra lo que ya existe, igual que
    `resolve_machine_asset()`.
    """
    for word in entry.name.upper().replace(".PDF", "").split():
        match = _FOLDER_MACHINE_CODE_RE.match(word)
        if not match:
            continue
        candidate_code = match.group(1).replace("-", "")
        asset = MachineAsset.objects.filter(code__iexact=candidate_code).first()
        if asset:
            return asset
    return None


def _scoped_files():
    query = Q(pk__in=[])  # falso por defecto, se OR-ea abajo
    exclude_query = Q(pk__in=[])

    for root, mode, names in SCOPE:
        if mode == "only":
            for name in names:
                sub = "%s/%s" % (root, name)
                query |= Q(parent_path=sub) | Q(parent_path__startswith=sub + "/")
        else:
            query |= Q(parent_path=root) | Q(parent_path__startswith=root + "/")
            for name in names:
                sub = "%s/%s" % (root, name)
                exclude_query |= Q(parent_path=sub) | Q(parent_path__startswith=sub + "/")

    qs = DocumentIndexEntry.objects.filter(
        query, bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        document_type__isnull=True,
        deleted_at__isnull=True, purged_at__isnull=True,
    )
    return qs.exclude(exclude_query)


class Command(BaseCommand):
    help = (
        "H30 (S50) -- Fase A restringida al mapa de carpetas de "
        "maquina confirmado explicitamente (ver SCOPE). Solo dominio "
        "MACHINE. Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        type_catalog = {
            t.code: t
            for t in DocumentTypeCatalog.objects.filter(is_active=True)
        }

        stats = {
            "asignados": 0, "dosier_eliminado": 0,
            "dosier_sin_dividir_pendiente": 0, "sin_resolver_tipo": 0,
            "sin_resolver_dominio": 0, "folder_type": 0,
        }

        entries = list(_scoped_files().only("id", "name", "parent_path"))
        self.stdout.write(
            "--- MACHINE (alcance acotado S50): %d archivos candidatos ---"
            % len(entries)
        )

        for entry in entries:
            name_upper = _strip_accents(entry.name).upper()

            folder_code = folder_based_type(entry, "MACHINE")
            if folder_code:
                code, dossier_pair = folder_code, None
                stats["folder_type"] += 1
            else:
                code, dossier_pair = resolve_document_type_heuristic(
                    entry, "MACHINE", name_upper,
                )

            if dossier_pair:
                obj = resolve_or_create_machine_asset(entry, {})
                if _dossier_types_already_filed(obj, machine_ct, dossier_pair):
                    stats["dosier_eliminado"] += 1
                    self.stdout.write(
                        "DOSIER ELIMINADO (ya dividido en %s) [%s] %s"
                        % (sorted(dossier_pair), entry.parent_path, entry.name)
                    )
                    if apply_changes:
                        trash_dossier_entry(entry)
                else:
                    stats["dosier_sin_dividir_pendiente"] += 1
                    self.stdout.write(
                        "DOSIER SIN DIVIDIR, NO SE ELIMINA (revision manual) "
                        "[%s] %s -> %s"
                        % (entry.parent_path, entry.name, sorted(dossier_pair))
                    )
                continue

            if not code:
                stats["sin_resolver_tipo"] += 1
                continue

            asset = resolve_or_create_machine_asset(entry, {})
            if not asset and ("/RAE" in entry.parent_path or "/CE PLATAFORMAS" in entry.parent_path):
                asset = _resolve_machine_by_filename(entry)
            if not asset:
                stats["sin_resolver_dominio"] += 1
                self.stdout.write(
                    "TIPO OK, DOMINIO SIN RESOLVER  [%s] %s -> %s"
                    % (entry.parent_path, entry.name, code)
                )
                continue

            stats["asignados"] += 1
            if apply_changes:
                entry.document_type = type_catalog[code]
                entry.domain_content_type = machine_ct
                entry.domain_object_id = asset.pk
                entry.save(update_fields=[
                    "document_type", "domain_content_type", "domain_object_id",
                ])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
