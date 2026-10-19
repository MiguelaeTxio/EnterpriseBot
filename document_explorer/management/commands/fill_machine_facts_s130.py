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
Verboso (com-standards 0bis/0ter): cada línea va a pantalla y al
--log-file con flush, con latido por centro y ETA con hora de fin.
"""
from datetime import datetime, timedelta

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
    help = (
        "S130: rellena la matrícula vacía de los centros de gasto desde "
        "sus documentos."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--code", default="")
        parser.add_argument("--log-file", default="")

    def _log(self, text, stamp=True):
        line = (
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
            if stamp else text
        )
        print(line, flush=True)
        if self._log_handle:
            self._log_handle.write(line + "\n")
            self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = (
            open(options["log_file"], "a", encoding="utf-8")
            if options["log_file"] else None
        )
        try:
            self._run(options)
        finally:
            if self._log_handle:
                self._log_handle.close()

    def _run(self, options):
        apply = options["apply"]
        ct = ContentType.objects.get_for_model(MachineAsset)
        machines = MachineAsset.objects.filter(
            Q(plate="") | Q(plate__isnull=True),
        )
        if options["code"]:
            machines = machines.filter(code=options["code"].upper())
        machines = list(machines.order_by("code"))
        total = len(machines)
        self._log("%s -- %d centros de gasto sin matrícula" % (
            "APLICANDO" if apply else "SOLO INFORME", total,
        ))
        start = datetime.now()
        counters = {"rellenadas": 0, "sin_docs": 0, "sin_matricula": 0}
        for index, machine in enumerate(machines, start=1):
            self._process(machine, ct, apply, counters)
            elapsed = (datetime.now() - start).total_seconds()
            eta = elapsed / index * (total - index)
            self._log(
                "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                "-- rellenadas=%d, sin_docs=%d, sin_matricula=%d" % (
                    index, total, index * 100 // total,
                    int(eta // 60), int(eta % 60),
                    (datetime.now() + timedelta(seconds=eta)).strftime(
                        "%H:%M:%S",
                    ),
                    counters["rellenadas"], counters["sin_docs"],
                    counters["sin_matricula"],
                ),
            )
        self._log("RESUMEN", stamp=False)
        self._log(
            "Matrículas %s: %d. Sin documentos que la acrediten: %d. "
            "Con documentos pero sin matrícula legible: %d." % (
                "rellenadas" if apply else "que se rellenarían",
                counters["rellenadas"], counters["sin_docs"],
                counters["sin_matricula"],
            ),
            stamp=False,
        )

    def _process(self, machine, ct, apply, counters):
        entries = list(DocumentIndexEntry.objects.filter(
            domain_content_type=ct, domain_object_id=machine.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code__in=MACHINE_FACTS_BY_TYPE.keys(),
        ).select_related("document_type").order_by("-indexed_at"))
        entries.sort(key=lambda e: _TYPE_ORDER.get(e.document_type.code, 9))
        if not entries:
            counters["sin_docs"] += 1
            self._log(
                "%s: sin documentos que acrediten la matrícula" % machine.code,
            )
            return
        for entry in entries:
            self._log("%s: leyendo %s" % (machine.code, entry.name))
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
            except Exception as exc:  # noqa: BLE001
                self._log("%s: %s no se pudo descargar (%s)" % (
                    machine.code, entry.name, exc,
                ))
                continue
            result = check_document(
                document_type=entry.document_type, is_machine=True,
                data=data, filename=entry.name, text=entry.ocr_text or "",
            )
            if not result:
                self._log("%s: %s sin lectura" % (machine.code, entry.name))
                continue
            if result.get("type_mismatch"):
                self._log("%s: %s parece %s, no se usa" % (
                    machine.code, entry.name,
                    result["type_mismatch"]["label"],
                ))
                continue
            outcome = apply_machine_facts(
                machine, entry.document_type.code, result["facts"],
                save=apply,
            )
            if outcome["filled"] or outcome["different"]:
                self._log("%s: %s -> rellena %s; distinto %s" % (
                    machine.code, entry.name, outcome["filled"],
                    outcome["different"],
                ))
            if machine.plate:
                counters["rellenadas"] += 1
                return
        counters["sin_matricula"] += 1
        self._log("%s: ningún documento trae su matrícula" % machine.code)
