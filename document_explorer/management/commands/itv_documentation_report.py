# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/itv_documentation_report.py
"""
Read-only report of the vehicles whose ITV expires within N days (or
has already expired), with their ITV documents, bucket MD5 and the
path each one must have in the local OneDrive tree.

---

H31 (S150). Informe de solo lectura de los vehículos con la ITV a N
días o menos (o ya vencida), con sus documentos de ITV, el MD5 de cada
uno en el cubo y la ruta que debe tener en el árbol local de OneDrive.
Lo consume la tarea programada de ITV (Hoja de Ruta S150, punto 1),
que comprueba en el PC de Miguel Ángel que ese mismo archivo está en
local con el mismo MD5. Miguel Ángel, al cerrar S148: "detectar los
vehículos con las ITV que caducan en un mes o menos y asegurarte de que
la documentación la tienen actualizada en local (microsoft 365) y en
EnterpriseBot".

Fecha de ITV de cada vehículo (decisión S150): la más reciente entre
`MachineAsset.itv_date` (columna del Excel de maquinaria, solo rellena
en ~35 máquinas y a menudo desfasada) y la caducidad del último
documento de ITV vigente (no obsoleto, no en papelera). Así entran
también los turismos, cabezas tractoras y remolques sin `itv_date`.

En EnterpriseBot está "al día" si la fecha de ITV no ha pasado y hay un
documento de ITV vigente con esa misma caducidad.

No escribe nada en BD ni en el cubo.
"""
import base64
import json
from datetime import date
from datetime import datetime
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.machine_local_folder_service import BUCKET
from document_explorer.machine_local_folder_service import PANEL_PREFIXES
from document_explorer.machine_local_folder_service import (
    current_local_folder)
from document_explorer.machine_local_folder_service import has_local_folder
from document_explorer.machine_local_folder_service import (
    target_local_folder)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import get_storage_client

ITV_TYPE_CODE = "ITV"
# Lo que entra por el agente H28 sin clasificar del todo vive en el cubo
# bajo esta cuarentena; en local está en la misma ruta sin el prefijo.
QUARANTINE_PREFIX = "_CUARENTENA/"


class Command(BaseCommand):
    """
    Build the ITV report as JSON (read-only).

    ---

    Genera el informe de ITV en JSON (solo lectura).
    """

    help = ("Informe de solo lectura de los vehículos con la ITV a N días "
            "o menos: documentos de ITV, MD5 en el cubo y ruta local.")

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--output", required=True,
                            help="Ruta del JSON de salida.")
        parser.add_argument("--log", default="",
                            help="Fichero de log (por defecto, el JSON "
                                 "con .log).")

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._log_file.write(line + "\n")
        self._log_file.flush()

    def handle(self, *args, **options):
        log_path = options["log"] or options["output"] + ".log"
        with open(log_path, "a", encoding="utf-8") as log_file:
            self._log_file = log_file
            report = self._build(options["days"])
        with open(options["output"], "w", encoding="utf-8") as out:
            json.dump(report, out, ensure_ascii=False, indent=1)
        print("Informe escrito: %s (%d vehículos)" % (
            options["output"], len(report["vehicles"])), flush=True)

    def _build(self, days):
        today = date.today()
        limit = today + timedelta(days=days)
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=machine_ct,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code=ITV_TYPE_CODE,
            deleted_at__isnull=True, purged_at__isnull=True,
            is_obsolete=False,
        ).order_by("pk")
        by_machine = {}
        for entry in entries:
            by_machine.setdefault(entry.domain_object_id, []).append(entry)
        self._log("Documentos de ITV vigentes: %d, de %d máquinas." % (
            entries.count(), len(by_machine)))

        selected = []
        for machine in MachineAsset.objects.filter(
                is_active=True).order_by("code"):
            if not has_local_folder(machine):
                continue
            docs = by_machine.get(machine.pk, [])
            dates = [d.expiry_date for d in docs if d.expiry_date]
            if machine.itv_date:
                dates.append(machine.itv_date)
            if not dates:
                continue
            itv_due = max(dates)
            if itv_due <= limit:
                selected.append((machine, docs, itv_due))
        self._log("Vehículos con ITV hasta el %s: %d." % (
            limit.isoformat(), len(selected)))

        bucket = get_storage_client().bucket(BUCKET)
        vehicles = []
        for position, (machine, docs, itv_due) in enumerate(
                selected, start=1):
            vehicles.append(
                self._vehicle(bucket, machine, docs, itv_due, today))
            self._log("%d/%d %s: ITV %s, %d documento(s), %s" % (
                position, len(selected), machine.code, itv_due.isoformat(),
                len(docs), vehicles[-1]["enterprisebot"]))
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "today": today.isoformat(),
            "days": days,
            "limit": limit.isoformat(),
            "vehicles": vehicles,
        }

    def _vehicle(self, bucket, machine, docs, itv_due, today):
        folder = target_local_folder(machine, current_local_folder(machine))
        items = []
        for entry in docs:
            if entry.blob_name.startswith(PANEL_PREFIXES):
                local_path = "%s/%s" % (folder, entry.name)
            elif entry.blob_name.startswith(QUARANTINE_PREFIX):
                local_path = entry.blob_name[len(QUARANTINE_PREFIX):]
            else:
                local_path = entry.blob_name
            blob = bucket.get_blob(entry.blob_name)
            md5 = ""
            if blob is not None and blob.md5_hash:
                md5 = base64.b64decode(blob.md5_hash).hex()
            items.append({
                "id": entry.pk,
                "name": entry.name,
                "blob": entry.blob_name,
                "expiry_date": (entry.expiry_date.isoformat()
                                if entry.expiry_date else None),
                "matches_itv": entry.expiry_date == itv_due,
                "in_bucket": blob is not None,
                "md5": md5,
                "size": blob.size if blob is not None else None,
                "local_path": local_path,
            })
        problems = []
        if itv_due < today:
            problems.append(
                "ITV vencida el %s: falta el documento de la ITV nueva"
                % itv_due.isoformat())
        elif not any(item["matches_itv"] for item in items):
            problems.append(
                "falta un documento de ITV con caducidad %s"
                % itv_due.isoformat())
        if machine.itv_date and machine.itv_date != itv_due:
            problems.append(
                "la fecha de ITV de la ficha (%s) no coincide con el "
                "documento (%s)" % (machine.itv_date.isoformat(),
                                    itv_due.isoformat()))
        if any(not item["in_bucket"] for item in items):
            problems.append("hay documentos de ITV que no están en el cubo")
        return {
            "id": machine.pk,
            "code": machine.code,
            "plate": machine.plate,
            "family": machine.family,
            "itv_due": itv_due.isoformat(),
            "days_left": (itv_due - today).days,
            "itv_date_sheet": (machine.itv_date.isoformat()
                               if machine.itv_date else None),
            "local_folder": folder,
            "enterprisebot": "; ".join(problems) or "al día",
            "documents": items,
        }
