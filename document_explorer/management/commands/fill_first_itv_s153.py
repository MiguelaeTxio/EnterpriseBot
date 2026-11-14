# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fill_first_itv_s153.py
"""
S153. Fill the first registration date and the ITV kind of the cost
centres from their registration documents.

---

S153. Miguel Ángel: "como podemos saber si un vehículo es nuevo y por
eso aún no tenemos documento de ITV" -> "Prepáralo". Para cada centro
de gasto activo con matrícula al que le falte la fecha de primera
matriculación o el tipo de vehículo para la ITV, lee sus documentos de
matriculación (permiso de circulación, ficha técnica, ITV, autorización
provisional; el permiso primero) con el mismo `document_check_service`
que la subida desde la ficha, y rellena los campos VACÍOS -- nunca
sobrescribe. Se para en cuanto tiene los dos.

Sin --apply solo informa de lo que haría. --code limita a uno o varios
centros (separados por comas). Al final lista los que quedan exentos
(primera ITV aún por llegar) y los que siguen sin fecha o sin tipo.
Verboso (com-standards 0bis/0ter): cada línea va a pantalla y al
--log-file con flush, con latido por centro y ETA con hora de fin.
"""
from datetime import date, datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.document_check_service import (
    MACHINE_FACTS_BY_TYPE, apply_machine_facts, check_document,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

# Permiso primero: trae la fecha de primera matriculación (campo B).
_TYPE_ORDER = {
    "PERMISO_CIRCULACION": 0, "FICHA_TECNICA": 1,
    "AUTORIZACION_PROVISIONAL_CIRCULACION": 2, "ITV": 3,
}


class Command(BaseCommand):
    help = (
        "S153: rellena la primera matriculación y el tipo para la ITV de "
        "los centros de gasto desde sus documentos."
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
        machines = MachineAsset.objects.filter(is_active=True).exclude(
            Q(plate="") | Q(plate__isnull=True),
        ).exclude(itv_category=MachineAsset.ITV_NONE).filter(
            Q(first_registration_date__isnull=True) | Q(itv_category=""),
        )
        if options["code"]:
            codes = [
                code.strip().upper()
                for code in options["code"].split(",") if code.strip()
            ]
            machines = machines.filter(code__in=codes)
        machines = list(machines.order_by("code"))
        total = len(machines)
        self._log("%s -- %d centros de gasto sin fecha o sin tipo" % (
            "APLICANDO" if apply else "SOLO INFORME", total,
        ))
        start = datetime.now()
        counters = {"completos": 0, "sin_docs": 0, "incompletos": 0}
        for index, machine in enumerate(machines, start=1):
            self._process(machine, ct, apply, counters)
            elapsed = (datetime.now() - start).total_seconds()
            eta = elapsed / index * (total - index)
            self._log(
                "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                "-- completos=%d, sin_docs=%d, incompletos=%d" % (
                    index, total, index * 100 // total,
                    int(eta // 60), int(eta % 60),
                    (datetime.now() + timedelta(seconds=eta)).strftime(
                        "%H:%M:%S",
                    ),
                    counters["completos"], counters["sin_docs"],
                    counters["incompletos"],
                ),
            )
        today = date.today()
        exempt = sorted(
            (m.itv_exempt_until, m.code) for m in machines
            if m.itv_exempt_until and m.itv_exempt_until >= today
        )
        missing = [
            "%s (%s)" % (m.code, ", ".join(
                part for part, empty in (
                    ("sin fecha", not m.first_registration_date),
                    ("sin tipo", not m.itv_category),
                ) if empty))
            for m in machines
            if not m.first_registration_date or not m.itv_category
        ]
        self._log("RESUMEN", stamp=False)
        self._log(
            "Con fecha y tipo %s: %d. Sin documentos de matriculación: %d. "
            "Con documentos pero sin los dos datos: %d." % (
                "rellenados" if apply else "que se rellenarían",
                counters["completos"], counters["sin_docs"],
                counters["incompletos"],
            ),
            stamp=False,
        )
        self._log("Aún exentos de ITV (%d): %s" % (
            len(exempt), "; ".join(
                "%s hasta %s" % (code, until.strftime("%d/%m/%Y"))
                for until, code in exempt) or "ninguno"), stamp=False)
        self._log("Siguen incompletos (%d): %s" % (
            len(missing), ", ".join(missing) or "ninguno"), stamp=False)

    def _process(self, machine, ct, apply, counters):
        entries = list(DocumentIndexEntry.objects.filter(
            domain_content_type=ct, domain_object_id=machine.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code__in=_TYPE_ORDER.keys(),
        ).select_related("document_type").order_by("-indexed_at"))
        entries.sort(key=lambda e: _TYPE_ORDER.get(e.document_type.code, 9))
        if not entries:
            counters["sin_docs"] += 1
            self._log("%s: sin documentos de matriculación" % machine.code)
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
            facts_type = entry.document_type.code
            mismatch = result.get("type_mismatch")
            if mismatch:
                if mismatch["code"] not in MACHINE_FACTS_BY_TYPE:
                    self._log("%s: %s parece %s, no se usa" % (
                        machine.code, entry.name, mismatch["label"],
                    ))
                    continue
                facts_type = mismatch["code"]
            outcome = apply_machine_facts(
                machine, facts_type, result["facts"], save=apply,
            )
            if outcome["filled"] or outcome["different"]:
                self._log("%s: %s -> rellena %s; distinto %s" % (
                    machine.code, entry.name, outcome["filled"],
                    outcome["different"],
                ))
            if machine.first_registration_date and machine.itv_category:
                counters["completos"] += 1
                return
        counters["incompletos"] += 1
        self._log("%s: le falta %s" % (machine.code, " y ".join(
            part for part, empty in (
                ("la fecha", not machine.first_registration_date),
                ("el tipo", not machine.itv_category),
            ) if empty)))
