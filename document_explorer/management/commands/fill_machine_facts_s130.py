# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fill_machine_facts_s130.py
"""
S130. Fill the empty plate (and chassis, make/model, insurance) of the
cost centres from the documents they already have.

---

S130. Miguel Ángel: "tenemos CDG sin matrícula". Para cada centro de
gasto sin matrícula, lee sus documentos que la acreditan (permiso de
circulación, ficha técnica, ITV, autorización provisional y los de
seguro; del más reciente al más antiguo) con el mismo
`document_check_service` que la subida desde la ficha, y rellena los
campos VACÍOS -- nunca sobrescribe. Se para en cuanto tiene matrícula.
Un documento que no parece de su tipo no se usa.

Sin --apply solo informa de lo que haría. --code limita a un centro.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.document_check_service import (
    MACHINE_FACTS_BY_TYPE, apply_machine_facts, check_document,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

# Registration documents first: they state the plate officially.
# Primero los de matriculación: acreditan la matrícula.
_TYPE_ORDER = {
    "PERMISO_CIRCULACION": 0, "FICHA_TECNICA": 1, "ITV": 2,
    "AUTORIZACION_PROVISIONAL_CIRCULACION": 3,
}


class Command(BaseCommand):
    help = "S130: rellena la matrícula vacía de los centros de gasto desde sus documentos."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--code", default="")

    def handle(self, *args, **options):
        apply = options["apply"]
        ct = ContentType.objects.get_for_model(MachineAsset)
        machines = MachineAsset.objects.filter(Q(plate="") | Q(plate__isnull=True))
        if options["code"]:
            machines = machines.filter(code=options["code"].upper())
        machines = list(machines.order_by("code"))
        self.stdout.write(
            "%s -- %d centros de gasto sin matrícula"
            % ("APLICANDO" if apply else "SOLO INFORME", len(machines)),
        )
        filled_count = 0
        for machine in machines:
            entries = list(DocumentIndexEntry.objects.filter(
                domain_content_type=ct, domain_object_id=machine.pk,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
                document_type__code__in=MACHINE_FACTS_BY_TYPE.keys(),
            ).select_related("document_type").order_by("-indexed_at"))
            entries.sort(key=lambda e: _TYPE_ORDER.get(e.document_type.code, 9))
            if not entries:
                self.stdout.write("%s: sin documentos que acrediten la matrícula" % machine.code)
                continue
            got_plate = False
            for entry in entries:
                try:
                    data = download_bytes(entry.bucket, entry.blob_name)
                except Exception as exc:  # noqa: BLE001
                    self.stdout.write("%s: %s no se pudo descargar (%s)" % (machine.code, entry.name, exc))
                    continue
                result = check_document(
                    document_type=entry.document_type, is_machine=True,
                    data=data, filename=entry.name, text=entry.ocr_text or "",
                )
                if not result:
                    self.stdout.write("%s: %s sin lectura" % (machine.code, entry.name))
                    continue
                if result.get("type_mismatch"):
                    self.stdout.write(
                        "%s: %s parece %s, no se usa"
                        % (machine.code, entry.name, result["type_mismatch"]["label"]),
                    )
                    continue
                outcome = apply_machine_facts(
                    machine, entry.document_type.code, result["facts"], save=apply,
                )
                if outcome["filled"] or outcome["different"]:
                    self.stdout.write("%s: %s -> rellena %s; distinto %s" % (
                        machine.code, entry.name, outcome["filled"], outcome["different"],
                    ))
                if machine.plate:
                    got_plate = True
                    filled_count += 1
                    break
            if not got_plate:
                self.stdout.write("%s: ningún documento trae su matrícula" % machine.code)
        self.stdout.write("Matrículas %s: %d" % ("rellenadas" if apply else "que se rellenarían", filled_count))
