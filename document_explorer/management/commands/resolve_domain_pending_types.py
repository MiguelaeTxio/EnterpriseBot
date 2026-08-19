# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_domain_pending_types.py
"""
H30 (S58) -- resuelve `domain_object_id` PERSONAL para entradas que ya
tienen `document_type` asignado de una pasada anterior (Fase A/OCR),
usando los tres resolutores ya existentes de `run_fase_a_sweep.py` en
el mismo orden de prioridad que usa el flujo principal de esa
herramienta: `_resolve_person_by_folder()` ->
`_resolve_person_by_name()` -> `_resolve_person_by_sliding_window()`.

Motivo real de este comando (hoja de ruta H30, punto 1 dejado por
S57): el "Bloque 4/5" de S56/S57 que resolvio RECONOCIMIENTO_MEDICO
(146 -> 77 sin dominio) se ejecuto como script suelto, nunca
comiteado -- cada sesion futura que necesitara repetir el patron
tendria que reescribirlo de memoria. Este comando fija ese patron como
herramienta reutilizable de verdad, parametrizada por lista de codigos
de tipo documental, en vez de volver a perderse tras el cierre de
sesion.

A diferencia de `run_fase_a_sweep.py` (que filtra
`document_type__isnull=True`, solo archivos SIN tipo todavia), este
comando filtra exactamente lo contrario: `document_type__code__in=TYPES`,
`domain_object_id__isnull=True` -- archivos que YA tienen tipo pero
cuyo dominio quedo pendiente ("TIPO OK, DOMINIO PENDIENTE"). Nunca
reasigna ni reevalua el tipo documental ya guardado.

Dominio unico: PERSONAL. Los seis tipos objetivo de la hoja de ruta
(PAGO_CORRIENTE, INVESTIGACION_ACCIDENTE, ENTREGA_INFORMACION,
BAJA_PERSONAL, AUTORIZACION_USO_MAQUINARIA, PARTE_BAJA_MEDICA) son
todos de dominio PERSONAL, confirmado contra
`document_explorer/heuristic_type_service.py` (S58).

DRY-RUN POR DEFECTO. Con `--apply` escribe de verdad
(`domain_content_type`/`domain_object_id`). Nunca toca `document_type`
ni GCS (4.12).
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET,
)
from document_explorer.management.commands.run_fase_a_sweep import (
    _build_person_name_index, _resolve_person_by_folder,
    _resolve_person_by_name, _resolve_person_by_sliding_window,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity

# Hoja de ruta H30, punto 1 (dejado por S57) -- mayores volumenes de
# tipo_ok_dominio_pendiente sin tocar, en el mismo orden de prioridad
# indicado en el anexo.
DEFAULT_TYPES = [
    "PAGO_CORRIENTE",
    "INVESTIGACION_ACCIDENTE",
    "ENTREGA_INFORMACION",
    "BAJA_PERSONAL",
    "AUTORIZACION_USO_MAQUINARIA",
    "PARTE_BAJA_MEDICA",
]


class Command(BaseCommand):
    help = (
        "H30 (S58) -- resuelve domain_object_id PERSONAL para tipos "
        "documentales ya asignados (tipo_ok_dominio_pendiente), via "
        "_resolve_person_by_folder/_by_name/_by_sliding_window, en "
        "ese orden. Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--types", nargs="+", default=DEFAULT_TYPES,
            help=(
                "Codigos de DocumentTypeCatalog a procesar (por "
                "defecto, los seis de la hoja de ruta H30 punto 1)."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        types = options["types"]
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        person_name_index = _build_person_name_index()

        totals = {"antes": 0, "resueltos": 0, "sin_resolver": 0}

        for code in types:
            entries = list(
                DocumentIndexEntry.objects.filter(
                    bucket=BUCKET,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    document_type__code=code,
                    domain_object_id__isnull=True,
                    deleted_at__isnull=True, purged_at__isnull=True,
                ).only("id", "name", "parent_path")
            )
            antes = len(entries)
            resueltos = 0

            self.stdout.write(
                "--- %s: %d archivos con tipo OK, dominio pendiente ---"
                % (code, antes)
            )

            for entry in entries:
                obj = _resolve_person_by_folder(entry)
                if not obj:
                    obj = _resolve_person_by_name(entry, person_name_index)
                if not obj:
                    obj = _resolve_person_by_sliding_window(
                        entry, person_name_index,
                    )

                if not obj:
                    continue

                resueltos += 1
                self.stdout.write(
                    "RESUELTO [%s] %s -> %s (%s)"
                    % (
                        entry.parent_path, entry.name, code,
                        obj.get_full_name()
                        if hasattr(obj, "get_full_name") else obj.pk,
                    )
                )
                if apply_changes:
                    entry.domain_content_type = person_ct
                    entry.domain_object_id = obj.pk
                    entry.save(update_fields=[
                        "domain_content_type", "domain_object_id",
                    ])

            self.stdout.write(
                "    %s: antes=%d resueltos=%d sin_resolver=%d"
                % (code, antes, resueltos, antes - resueltos)
            )
            totals["antes"] += antes
            totals["resueltos"] += resueltos
            totals["sin_resolver"] += antes - resueltos

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
