# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fill_machine_fields_from_documents.py
"""
S148. Fill the empty data of active cost centres from their documents.

---

S148. Rellena los datos vacíos de los centros de gasto activos con sus
propios documentos. Miguel Ángel: "mejorar el pipeline de extracción
de información para dejar la base de datos correcta a través de los
documentos que se cargan". Desde S130 cada documento subido desde la
ficha rellena matrícula, bastidor, marca y modelo y seguro; los que
llegaron con la migración nunca pasaron por esa lectura (S148: seguro
vacío en casi todas las máquinas con póliza subida).

Misma lectura que la subida (`document_check_service`): una llamada a
Gemini por documento, sobre el texto ya guardado si basta, si no sobre
el archivo (primeras páginas pintadas, nunca OCR del servidor). Cada
dato solo desde los tipos que lo acreditan; nunca sobrescribe (lo
distinto se lista). Del documento más reciente al más antiguo, y se
para en cuanto la máquina no tiene datos vacíos que ese tipo acredite.

DRY-RUN POR DEFECTO (`--apply` escribe). Pantalla y `--log-file` a la
vez, con progreso y ETA.
"""
import collections
import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from document_explorer.document_check_service import (
    MACHINE_FACTS_BY_TYPE,
    MIN_TEXT_CHARS,
    apply_machine_facts,
    check_document,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

# Field of the machine for each fact a type states.
# Campo de la máquina para cada dato que acredita un tipo.
_FIELD_OF_FACT = {
    "plate": "plate", "chassis_number": "chassis_number",
    "brand_model": "brand_model", "insurer": "insurance_info",
}


def _missing(machine):
    return {
        field for field in _FIELD_OF_FACT.values()
        if not (getattr(machine, field) or "").strip()
    }


def _fillable(code, missing):
    return {
        _FIELD_OF_FACT[fact] for fact in MACHINE_FACTS_BY_TYPE.get(code, ())
        if fact in _FIELD_OF_FACT
    } & missing


class Command(BaseCommand):
    help = "S148: rellena los datos vacíos de las máquinas con sus documentos."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)
        parser.add_argument(
            "--only-purchase", action="store_true",
            help="S148: solo la fecha de compra (sin lecturas de Gemini)")

    def handle(self, *args, **options):
        log_file = open(options["log_file"], "a", encoding="utf-8")
        start = datetime.datetime.now()

        def _log(text):
            line = "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), text)
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        def _plain(text):
            print(text, flush=True)
            log_file.write(text + "\n")
            log_file.flush()

        apply = options["apply"]
        _log("Datos de máquinas desde sus documentos (S148) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        # S148: fecha de compra vacía = la más antigua de sus facturas de
        # compra, compraventas y leasing: la fecha ya registrada o, si no
        # la tienen, la que lee Gemini (como mucho 4 por máquina).
        bought = self._purchase_dates(apply, _log, _plain)
        _log("Fecha de compra: %d máquinas" % bought)
        if options["only_purchase"]:
            _plain("Escrito en la BD: %s" % ("sí" if apply else "no"))
            log_file.close()
            return
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        machines = [
            m for m in MachineAsset.objects.filter(
                is_active=True).order_by("code")
            if _missing(m)
        ]
        entries = collections.defaultdict(list)
        for entry in DocumentIndexEntry.objects.filter(
            domain_content_type=machine_ct,
            domain_object_id__in=[m.pk for m in machines],
            deleted_at__isnull=True,
            is_obsolete=False,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code__in=list(MACHINE_FACTS_BY_TYPE),
        ).select_related("document_type").order_by("-pk"):
            entries[entry.domain_object_id].append(entry)
        machines = [m for m in machines if entries[m.pk]]
        _log("%d máquinas activas con datos vacíos y documentos que los "
             "acreditan" % len(machines))
        totals = collections.Counter()
        for number, machine in enumerate(machines, 1):
            _log("%d/%d %s %s" % (
                number, len(machines), machine.code, machine.plate or ""))
            for entry in entries[machine.pk]:
                code = entry.document_type.code
                if not _fillable(code, _missing(machine)):
                    continue
                text = entry.ocr_text or ""
                data = b""
                if len(text.strip()) < MIN_TEXT_CHARS:
                    try:
                        data = download_bytes(entry.bucket, entry.blob_name)
                    except Exception as error:  # noqa: BLE001
                        _plain("    %s: no se pudo descargar (%s)" % (
                            entry.name, error))
                        totals["error"] += 1
                        continue
                totals["leídos"] += 1
                result = check_document(
                    document_type=entry.document_type, is_machine=True,
                    data=data, filename=entry.name, text=text,
                )
                if not result:
                    _plain("    %s: sin lectura" % entry.name)
                    totals["error"] += 1
                    continue
                if result.get("type_mismatch"):
                    # Como en la subida: con el tipo en duda no se toman
                    # datos del documento (S148: folletos del fabricante
                    # archivados como ficha técnica).
                    totals["tipo dudoso"] += 1
                    _plain("    tipo dudoso: %s parece %s (no se toman "
                           "datos)" % (entry.name,
                                       result["type_mismatch"]["label"]))
                    continue
                # Gemini puede tardar más que el tiempo de inactividad de
                # MySQL (S148: "Lost connection to MySQL server").
                close_old_connections()
                outcome = apply_machine_facts(
                    machine, code, result.get("facts") or {}, save=apply,
                )
                for label, value in outcome["filled"].items():
                    totals["rellenar"] += 1
                    _plain("    rellenar  %s: %s  [%s id=%s]" % (
                        label, value, code, entry.pk))
                for label, (current, read) in outcome["different"].items():
                    totals["DISTINTO"] += 1
                    _plain("    DISTINTO  %s: ficha %s, documento %s  "
                           "[%s id=%s]" % (label, current, read, code,
                                           entry.pk))
            elapsed = (datetime.datetime.now() - start).total_seconds()
            eta = elapsed / number * (len(machines) - number)
            end = datetime.datetime.now() + datetime.timedelta(seconds=eta)
            _log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                 "-- rellenados %d" % (
                     number, len(machines), 100 * number // len(machines),
                     eta // 60, eta % 60, end.strftime("%H:%M:%S"),
                     totals["rellenar"]))
        _plain("")
        _plain("RESUMEN")
        for key in ("leídos", "rellenar", "DISTINTO", "tipo dudoso", "error"):
            _plain("%s: %d" % (key, totals[key]))
        _plain("Escrito en la BD: %s" % ("sí" if apply else "no"))
        log_file.close()

    def _purchase_dates(self, apply, _log, _plain):
        """
        S148: empty purchase dates from the purchase documents.
        ---
        Fechas de compra vacías desde facturas de compra, compraventas
        y leasing (la más antigua). Devuelve cuántas máquinas.
        """
        from document_explorer.document_check_service import PURCHASE_TYPES

        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        machines = {
            m.pk: m for m in MachineAsset.objects.filter(
                is_active=True, purchase_date__isnull=True)
        }
        by_machine = collections.defaultdict(list)
        for entry in DocumentIndexEntry.objects.filter(
            domain_content_type=machine_ct,
            domain_object_id__in=list(machines),
            deleted_at__isnull=True,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code__in=PURCHASE_TYPES,
        ).select_related("document_type").order_by("pk"):
            by_machine[entry.domain_object_id].append(entry)
        _log("Fecha de compra: %d máquinas sin fecha con facturas de "
             "compra, compraventas o leasing" % len(by_machine))
        start = datetime.datetime.now()
        bought = 0
        for number, (pk, entries) in enumerate(by_machine.items(), 1):
            machine = machines[pk]
            dates = [(e.issue_date, e) for e in entries if e.issue_date]
            for entry in [e for e in entries if not e.issue_date][:4]:
                text = entry.ocr_text or ""
                data = b""
                if len(text.strip()) < MIN_TEXT_CHARS:
                    try:
                        data = download_bytes(entry.bucket, entry.blob_name)
                    except Exception as error:  # noqa: BLE001
                        _plain("    %s: no se pudo descargar (%s)" % (
                            entry.name, error))
                        continue
                result = check_document(
                    document_type=entry.document_type, is_machine=True,
                    data=data, filename=entry.name, text=text,
                ) or {}
                if result.get("type_mismatch"):
                    continue
                read = (result.get("facts") or {}).get("document_date")
                if read:
                    dates.append((read, entry))
            if dates:
                date, entry = min(dates, key=lambda pair: pair[0])
                bought += 1
                _plain("    %s: fecha de compra %s  [%s id=%s]" % (
                    machine.code, date.strftime("%d/%m/%Y"),
                    entry.document_type.code, entry.pk))
                if apply:
                    close_old_connections()
                    machine.purchase_date = date
                    machine.save(update_fields=["purchase_date"])
            elapsed = (datetime.datetime.now() - start).total_seconds()
            eta = elapsed / number * (len(by_machine) - number)
            end = datetime.datetime.now() + datetime.timedelta(seconds=eta)
            _log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                 "-- con fecha %d" % (
                     number, len(by_machine),
                     100 * number // len(by_machine), eta // 60, eta % 60,
                     end.strftime("%H:%M:%S"), bought))
        return bought
