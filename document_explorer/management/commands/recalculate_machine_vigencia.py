# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/recalculate_machine_vigencia.py
"""
H30 (S119), roadmap item 2 -- recompute currency (is_obsolete) and
expiry alerts for ACTIVE machines.
---
H30 (S119), punto 2 de la hoja de ruta -- recalcula la vigencia
(`is_obsolete`) y activa los avisos de caducidad de las máquinas
ACTIVAS, tras el fechado del punto 1.

Por grupo (mismo tipo no acumulable + misma máquina activa):

1. Criterio: `vigencia_selector.current_fn_for()` -- en tipos que
   caducan Y están en el requisito de documentación de ESA máquina en
   concreto (`MachineAsset.document_requirement`), `is_current_expiring`;
   en el resto, `is_current` de siempre. Corregido tras el incidente
   real de Alberto Javier Álvarez Díaz (S119): el criterio nunca fue
   por dominio, es por si el tipo es obligatorio para el sujeto -- ver
   docstring completo de `vigencia_selector.current_fn_for`. El mismo
   selector usa la ficha, así que lo que se guarda aquí es lo mismo que
   se ve en pantalla.
2. Compiten los no obsoletos Y los marcados obsoletos por un algoritmo
   anterior; NUNCA vuelve a vigente un documento que está dentro de una
   carpeta OBSOLETO/OBSOLETOS (organización manual, S50).
3. Un vigente por grupo; el resto queda `is_obsolete=True`. Un
   documento obsoleto que gana vuelve a `is_obsolete=False` (incluidos
   los duplicados de ficha técnica de la división de combinados).
4. Avisos: al vigente de un tipo que caduca con caducidad futura se le
   crean las alertas por defecto (30/15/7 días, idempotentes) con los
   DOCS_SUPERVISOR como contacto; las alertas PENDIENTES de los que
   pasan a obsoletos se marcan RESUELTAS, para que no avisen de un
   documento ya sustituido.

DRY-RUN por defecto; --apply escribe. Log propio (pantalla y archivo a
la vez, com-standards 0bis) con heartbeat y ETA.
"""
import time
from collections import Counter
from datetime import date, datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.models import DocumentIndexEntry
from document_explorer.required_documentation_service import (
    get_required_type_ids,
)
from document_explorer.vigencia_selector import current_fn_for
from document_management.alert_service import (
    create_default_expiry_alerts,
    get_docs_supervisor_contacts,
)
from document_management.models import DocumentAlert
from document_management.vigencia_service import DocumentSnapshot
from fleet.models import MachineAsset
from ivr_config.models import Company

BUCKET = "cgs_grupo_alvarez"
MANUAL_OBSOLETE_MARKERS = ("/OBSOLETO/", "/OBSOLETOS/")


class Command(BaseCommand):
    help = (
        "H30 (S119) -- punto 2: vigencia y avisos de caducidad de "
        "máquinas activas. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._log_plain(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message),
        )

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    @staticmethod
    def _is_manual_obsolete(entry):
        path = "/%s/" % entry.blob_name.upper().strip("/")
        return any(marker in path for marker in MANUAL_OBSOLETE_MARKERS)

    @staticmethod
    def _get_required_type_ids(machine, cache):
        """
        Cached per document_requirement_id -- avoids one query per
        machine when many share (or lack) the same requirement.
        ---
        Cacheado por document_requirement_id -- evita una consulta por
        máquina cuando muchas comparten (o carecen de) el mismo
        requisito.
        """
        requirement_id = machine.document_requirement_id
        if requirement_id not in cache:
            cache[requirement_id] = get_required_type_ids(machine)
        return cache[requirement_id]

    def _run(self, apply_changes):
        today = date.today()
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        entry_ct = ContentType.objects.get_for_model(DocumentIndexEntry)
        machines = {
            machine.pk: machine
            for machine in MachineAsset.objects.filter(is_active=True)
        }
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            domain_content_type=machine_ct,
            domain_object_id__in=list(machines),
            document_type__isnull=False,
            document_type__is_cumulative=False,
        ).select_related("document_type").order_by("id")
        groups = {}
        for entry in entries:
            key = (entry.document_type_id, entry.domain_object_id)
            groups.setdefault(key, []).append(entry)
        total = len(groups)
        self._log(
            "PUNTO 2 -- MODO: %s -- %d grupos (tipo no acumulable + "
            "maquina activa)" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)", total,
            )
        )
        company = Company.objects.first()
        contacts = get_docs_supervisor_contacts()
        stats = Counter()
        by_type = Counter()
        examples = {}
        required_ids_cache = {}
        start_time = datetime.now()
        last_beat = time.monotonic()
        for index, ((_type_id, machine_pk), group) in enumerate(
                sorted(groups.items()), start=1):
            machine = machines[machine_pk]
            self._process_group(
                group, machine,
                self._get_required_type_ids(machine, required_ids_cache),
                entry_ct, company, contacts, today, apply_changes,
                stats, by_type, examples,
            )
            if index % 100 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. "
                    "%s) -- a_obsoleto=%d, a_vigente=%d, alertas=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60),
                        (datetime.now() + timedelta(seconds=eta_seg)
                         ).strftime("%H:%M:%S"),
                        stats["a_obsoleto"], stats["a_vigente"],
                        stats["alertas_creadas"],
                    )
                )
        self._summary(apply_changes, total, stats, by_type, examples)

    def _process_group(self, group, machine, required_type_ids, entry_ct,
                       company, contacts, today, apply_changes, stats,
                       by_type, examples):
        """
        Recompute one (type, machine) group.
        ---
        Recalcula un grupo (tipo, máquina): quién es el vigente, qué
        cambia de estado y qué alertas se crean o se resuelven.
        """
        document_type = group[0].document_type
        competitors = [
            entry for entry in group
            if not (entry.is_obsolete and self._is_manual_obsolete(entry))
        ]
        current_fn = current_fn_for(document_type, required_type_ids)
        snapshots = {
            entry.pk: DocumentSnapshot(
                identifier=entry.pk, expiry_date=entry.expiry_date,
                issue_date=entry.issue_date, indexed_at=entry.indexed_at,
            )
            for entry in competitors
        }
        winners = {
            pk for pk, snapshot in snapshots.items()
            if current_fn(snapshot, [
                other for other_pk, other in snapshots.items()
                if other_pk != pk
            ], today)
        }
        stats["grupos"] += 1
        if len(winners) != 1 and competitors:
            stats["grupos_sin_vigente_unico"] += 1
        subject_label = "%s -- %s" % (machine.code, machine.brand_model)
        for entry in competitors:
            should_be_obsolete = entry.pk not in winners
            if should_be_obsolete == entry.is_obsolete:
                continue
            key = "a_obsoleto" if should_be_obsolete else "a_vigente"
            stats[key] += 1
            by_type[(document_type.code, key)] += 1
            examples.setdefault((document_type.code, key), []).append(
                "id=%d %s | %s | cad=%s emi=%s" % (
                    entry.id, machine.code, entry.name,
                    entry.expiry_date, entry.issue_date,
                )
            )
            if apply_changes:
                entry.is_obsolete = should_be_obsolete
                entry.save(update_fields=["is_obsolete"])
            if should_be_obsolete:
                pending = DocumentAlert.objects.filter(
                    content_type=entry_ct, object_id=entry.pk,
                    status=DocumentAlert.Status.PENDING,
                )
                stats["alertas_resueltas"] += pending.count()
                if apply_changes:
                    pending.update(
                        status=DocumentAlert.Status.RESOLVED,
                        resolved_at=timezone.now(),
                        resolution_notes=(
                            "Documento sustituido (recálculo de "
                            "vigencia H30 S119)."
                        ),
                    )
        if not document_type.tracks_expiry:
            return
        for entry in competitors:
            if entry.pk not in winners or entry.expiry_date is None \
                    or entry.expiry_date < today:
                continue
            existing = DocumentAlert.objects.filter(
                content_type=entry_ct, object_id=entry.pk,
            ).count()
            if existing >= 3:
                continue
            stats["documentos_con_alertas_nuevas"] += 1
            if not apply_changes:
                stats["alertas_creadas"] += 3 - existing
                continue
            alerts = create_default_expiry_alerts(
                document=entry, expiry_date=entry.expiry_date,
                document_label=document_type.label,
                subject_label=subject_label, company=company,
            )
            for alert in alerts:
                alert.contacts.add(*contacts)
            stats["alertas_creadas"] += len(alerts)

    def _summary(self, apply_changes, total, stats, by_type, examples):
        self._log_plain("=== RESUMEN PUNTO 2 (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    grupos revisados: %d" % total)
        for key in ("a_obsoleto", "a_vigente", "alertas_creadas",
                    "documentos_con_alertas_nuevas", "alertas_resueltas",
                    "grupos_sin_vigente_unico"):
            self._log_plain("    %s: %d" % (key, stats[key]))
        self._log_plain("--- CAMBIOS POR TIPO ---")
        for (code, key), count in sorted(by_type.items()):
            self._log_plain("    %s %s: %d" % (code, key, count))
        self._log_plain("--- EJEMPLOS (hasta 5 por grupo) ---")
        for (code, key), items in sorted(examples.items()):
            self._log_plain("  %s %s" % (code, key))
            for line in items[:5]:
                self._log_plain("      %s" % line)
