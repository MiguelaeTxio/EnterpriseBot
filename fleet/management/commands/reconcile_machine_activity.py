# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/reconcile_machine_activity.py
"""
Make the Active/Inactive state of the fleet match reality: GasoGes
refuels against sale or deregistration evidence.

---

H31 (S150). Que el estado Activo/Inactivo de los centros de gasto
refleje la realidad. Miguel Ángel: "el [Excel] estaba desactualizado
[...] hay muchos vehículos que están en activo que no deberían de
estarlo y hay vehículos que están inactivos y no deberían de estarlo
[...] Si un vehículo está activo, tiene que estar repostando
periódicamente [...] en un periodo de 6 meses o 1 año seguro que se ha
movido".

Señales de cada máquina:
- Repostajes de GasoGes de sus vehículos enlazados (hay datos desde
  enero de 2026: "sin repostajes" es ninguno en ese tiempo).
- Pruebas de baja o venta: documentos de EnterpriseBot de baja
  definitiva, baja temporal o factura de venta (fuertes); contrato de
  compraventa o justificante de transferencia (dudosos: pueden ser los
  de la compra); y su carpeta local de OneDrive (la de su última
  descarga o la de sus documentos) en una carpeta de bajas o ventas o
  con "vendid" en el nombre (fuerte).

Decisión, solo en lo seguro:
- DESACTIVAR: activa, sin ningún repostaje y con una prueba fuerte de
  baja o venta. Las que no tienen GasoGes (remolques, góndolas) solo si
  su carpeta local lo dice.
- REACTIVAR: inactiva, con repostajes en los últimos 180 días y sin
  ninguna prueba de baja o venta.
- El resto se informa para revisar: inactivas que repostan con pruebas
  de baja, activas que repostan con pruebas de baja, y activas sin
  repostajes con pruebas dudosas o sin ninguna.

Se hace como desde el panel: guardar, sync_machine_documents y
follow_change (la carpeta local pasa a la de bajas de su familia, o
vuelve). DRY-RUN por defecto; --apply escribe. Informe en JSON
(--output) y log propio (pantalla y archivo, com-standards 0bis).
"""
import json
import re
import unicodedata
from datetime import datetime
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models import Max
from django.db.models import Q
from django.utils import timezone

from document_explorer import machine_local_folder_service
from document_explorer.machine_folder_service import sync_machine_documents
from document_explorer.models import DocumentIndexEntry
from fleet.models import GasoGesSupply
from fleet.models import GasoGesVehicle
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
STRONG_TYPES = ("BAJA_DEFINITIVA", "BAJA_TEMPORAL", "FACTURA_VENTA")
WEAK_TYPES = ("CONTRATO_COMPRAVENTA", "JUSTIFICANTE_TRANSFERENCIA")
EXCLUDED_FAMILIES = ("DEPENDENCIAS", "PERSONAL")
RECENT_DAYS = 180
# Carpeta local de bajas o ventas: "VEHICULOS DE BAJA", "BAJA
# DEFINITIVA", "BAJAS", "VENTA", "(vendido)", "VENDIDA CHATARRA".
_LOCAL_OUT = re.compile(r"\bBAJAS?\b|\bVENTA\b|VENDID")


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(
        c for c in text if not unicodedata.combining(c)).upper()


class Command(BaseCommand):
    """
    Reconcile is_active with refuels and deregistration evidence.

    ---

    Concilia el estado Activo/Inactivo con los repostajes y las
    pruebas de baja o venta.
    """

    help = ("Concilia Activo/Inactivo de los centros de gasto con los "
            "repostajes de GasoGes y las pruebas de baja o venta.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--output", required=True,
                            help="Informe en JSON.")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._log_file.write(line + "\n")
        self._log_file.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as log_file:
            self._log_file = log_file
            self._log("MODO: %s" % (
                "APLICAR (escribe)" if options["apply"]
                else "DRY-RUN (no escribe nada)"))
            report = self._run(options["apply"])
        with open(options["output"], "w", encoding="utf-8") as out:
            json.dump(report, out, ensure_ascii=False, indent=1)
        self._log("Informe: %s" % options["output"])

    def _evidence(self):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        docs = {}
        for pk, code, issue, expiry, name in DocumentIndexEntry.objects.filter(
                bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                domain_content_type=machine_ct,
                deleted_at__isnull=True, purged_at__isnull=True,
                document_type__code__in=STRONG_TYPES + WEAK_TYPES,
        ).values_list("domain_object_id", "document_type__code",
                      "issue_date", "expiry_date", "name"):
            date = issue or expiry
            docs.setdefault(pk, []).append({
                "type": code, "date": date.isoformat() if date else None,
                "strong": code in STRONG_TYPES, "name": name,
            })
        return docs

    def _refuels(self):
        since = timezone.now() - timedelta(days=RECENT_DAYS)
        rows = GasoGesSupply.objects.filter(
            vehicle__machine__isnull=False,
        ).values("vehicle__machine_id").annotate(
            total=Count("id"), last=Max("supplied_at"),
            recent=Count("id", filter=Q(supplied_at__gte=since)),
        )
        linked = set(GasoGesVehicle.objects.filter(
            machine__isnull=False).values_list("machine_id", flat=True))
        return {
            row["vehicle__machine_id"]: row for row in rows
        }, linked

    def _run(self, apply_changes):
        docs = self._evidence()
        refuels, linked = self._refuels()
        machines = list(MachineAsset.objects.exclude(
            family__in=EXCLUDED_FAMILIES).order_by("code"))
        self._log("Centros de gasto: %d (con GasoGes: %d)." % (
            len(machines), len(linked)))
        result = {key: [] for key in (
            "desactivar", "reactivar", "inactivas_que_repostan",
            "activas_que_repostan_con_pruebas_de_baja",
            "activas_sin_repostajes_con_pruebas",
            "activas_sin_repostajes_sin_pruebas")}
        for position, machine in enumerate(machines, start=1):
            item = self._classify(machine, docs.get(machine.pk, []),
                                  refuels.get(machine.pk),
                                  machine.pk in linked)
            if item is None:
                continue
            bucket, row = item
            result[bucket].append(row)
            self._log("%d/%d %s: %s -- %s" % (
                position, len(machines), machine.code, bucket,
                row["motivo"]))
            if apply_changes and bucket in ("desactivar", "reactivar"):
                self._set_active(machine, bucket == "reactivar")
        for key, rows in result.items():
            self._log("%s: %d" % (key, len(rows)))
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "applied": apply_changes, "recent_days": RECENT_DAYS,
            **result,
        }

    def _classify(self, machine, evidence, refuel, has_gasoges):
        local = machine_local_folder_service.current_local_folder(machine)
        local_out = bool(_LOCAL_OUT.search(_plain(local)))
        strong = [e for e in evidence if e["strong"]]
        weak = [e for e in evidence if not e["strong"]]
        total = refuel["total"] if refuel else 0
        recent = refuel["recent"] if refuel else 0
        row = {
            "id": machine.pk, "code": machine.code, "plate": machine.plate,
            "family": machine.family, "is_active": machine.is_active,
            "gasoges": has_gasoges, "repostajes": total,
            "repostajes_180d": recent,
            "ultimo_repostaje": (refuel["last"].date().isoformat()
                                 if refuel and refuel["last"] else None),
            "carpeta_local": local, "carpeta_local_baja": local_out,
            "documentos": evidence,
        }
        proof = local_out or bool(strong)
        if machine.is_active:
            if total:
                if not proof:
                    return None
                row["motivo"] = "repostando (último %s) y %s" % (
                    row["ultimo_repostaje"],
                    "carpeta local de bajas o ventas" if local_out
                    else "documento de " + strong[0]["type"])
                return "activas_que_repostan_con_pruebas_de_baja", row
            if has_gasoges and proof or not has_gasoges and local_out:
                row["motivo"] = "sin repostajes y %s" % (
                    "carpeta local de bajas o ventas" if local_out
                    else "documento de " + strong[0]["type"])
                return "desactivar", row
            if not has_gasoges:
                return None
            if strong or weak:
                row["motivo"] = "sin repostajes; documentos: %s" % ", ".join(
                    e["type"] for e in evidence)
                return "activas_sin_repostajes_con_pruebas", row
            row["motivo"] = "sin repostajes y sin pruebas de baja"
            return "activas_sin_repostajes_sin_pruebas", row
        if not total:
            return None
        if recent and not proof and not weak:
            row["motivo"] = (
                "%d repostajes en %d días, sin pruebas de baja"
                % (recent, RECENT_DAYS))
            return "reactivar", row
        row["motivo"] = "inactiva con %d repostajes (último %s)%s" % (
            total, row["ultimo_repostaje"],
            "; pruebas de baja o venta" if proof or weak else "")
        return "inactivas_que_repostan", row

    def _set_active(self, machine, active):
        previous = machine_local_folder_service.current_local_folder(machine)
        machine.is_active = active
        machine.save(update_fields=["is_active"])
        sync_machine_documents(machine)
        machine_local_folder_service.follow_change(machine, previous)
        self._log("    %s -> %s" % (
            machine.code, "ACTIVA" if active else "INACTIVA"))
