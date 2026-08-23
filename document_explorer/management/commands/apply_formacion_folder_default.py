# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/apply_formacion_folder_default.py
"""
H30 (sesion S63) -- FALLBACK POST-FASE-A, no forma parte del
framework de prioridades de resolve_document_type_heuristic (nunca se
toca ese orden, ver heuristic_type_service.py). Se ejecuta SIEMPRE
DESPUES de run_fase_a_sweep --apply, nunca antes: solo actua sobre lo
que quede sin tipo en el momento de ejecutarse
(document_type__isnull=True), asi que jamas puede sobreescribir un
tipo mas especifico ya resuelto por keyword/carpeta (CAP, MOD_145,
AUTONOMO, RECONOCIMIENTO_MEDICO... dentro del mismo arbol).

Origen real: pedido explicito de Miguel Angel de dejar de calibrar
palabra a palabra (4 en 4) y resolver bloques grandes de una vez.
Confirmado con datos reales antes de escribir nada (ver
EnterpriseBot_013_GET.txt / EnterpriseBot_014_GET.txt, 30 archivos de
muestra de subcarpetas distintas): el 100% de lo que queda sin tipo
bajo DOC. PERSONAL/FORMACION TRABAJADORES es documentacion de soporte
de formacion (fichas de inscripcion, contratos de encomienda,
condiciones de venta, diplomas, presupuestos, facturas de curso,
evaluaciones, titulos usados para inscripcion, fotos de sede de
curso, correos de finalizacion) -- ninguna es documentacion de otro
dominio (nomina, seguro, maquinaria...) colada por error. 1.256
archivos reales en el momento de escribir esto.

Reutiliza sin modificar la resolucion de dominio de run_fase_a_sweep
(_resolve_person_by_folder / _resolve_person_by_name / ventana
deslizante) -- mismo criterio de siempre: nunca crea una
PersonIdentity nueva, nunca resuelve con ambiguedad. La mayoria de
estos archivos no resuelven a una persona concreta (facturas/diplomas
de varios trabajadores a la vez) y quedan con dominio pendiente,
exactamente igual que el resto de Fase A.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET,
)
from document_explorer.management.commands.run_fase_a_sweep import (
    _build_person_name_index, _resolve_person_by_folder,
    _resolve_person_by_name, _resolve_person_by_sliding_window,
)
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)

ROOT = "DOC. PERSONAL/FORMACION TRABAJADORES"


class Command(BaseCommand):
    help = (
        "Fallback post-Fase A: asigna FORMACION a todo lo que quede "
        "sin tipo bajo '%s' (confirmado 100%% formacion en muestra "
        "real, ver EnterpriseBot_014_GET.txt). Dry-run por defecto, "
        "usar --apply para escribir de verdad." % ROOT
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        formacion = DocumentTypeCatalog.objects.get(code="FORMACION")
        person_name_index = _build_person_name_index()

        qs = DocumentIndexEntry.objects.filter(
            Q(parent_path=ROOT) | Q(parent_path__startswith=ROOT + "/"),
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=True,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).only("id", "name", "parent_path")

        stats = {"asignados_con_persona": 0, "asignados_dominio_pendiente": 0}

        for entry in qs:
            obj = _resolve_person_by_folder(entry)
            if not obj:
                obj = _resolve_person_by_name(entry, person_name_index)
            if not obj:
                obj = _resolve_person_by_sliding_window(
                    entry, person_name_index,
                )

            if obj:
                stats["asignados_con_persona"] += 1
            else:
                stats["asignados_dominio_pendiente"] += 1

            if apply_changes:
                entry.document_type = formacion
                if obj:
                    entry.domain_content_type = person_ct
                    entry.domain_object_id = obj.pk
                    entry.save(update_fields=[
                        "document_type", "domain_content_type",
                        "domain_object_id",
                    ])
                else:
                    entry.save(update_fields=["document_type"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
