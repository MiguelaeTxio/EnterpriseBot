# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/mark_duplicate_documents.py
"""
H30 (S125). Exact duplicates in ACTIVE workers' records: the same file
indexed twice for the same person and type.

---

H30 (S125). Duplicados exactos en las fichas de los trabajadores
ACTIVOS: el mismo archivo indexado dos veces para la misma persona y el
mismo tipo. Caso real de Miguel Ángel: el 15/09 su documentación
laboral entró por dos caminos (07:55 con fecha, 17:38 sin fecha); las
copias sin fecha salían en "Altas sin fecha" y "Contratos que no
corresponden a ninguna alta". Consulta real: 31 grupos, 32 copias
sobrantes, 19 activos.

- Duplicado = misma persona, mismo tipo, mismo tamaño y MISMA huella MD5
  del objeto en GCS (el tamaño solo nunca basta).
- Se conserva la copia con fecha; a igualdad, la indexada antes.
- Las demás quedan obsoletas con registro de sustitución. No se borra
  ningún objeto ni ninguna fila (4.12).
- Solo trabajadores activos (Miguel Ángel, S125).

Con --dry-run no guarda nada. Salida en pantalla y archivo (--log-file).
"""
from collections import defaultdict
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_management.models import DocumentSubstitutionLog
from spare_parts.gcs_service import get_storage_client


class Command(BaseCommand):
    """
    Mark exact duplicate documents of active workers as obsolete.

    ---

    Marca como obsoletos los duplicados exactos de los activos.
    """

    help = (
        "Duplicados exactos (misma persona, tipo y MD5) de trabajadores "
        "ACTIVOS: conserva uno y deja los demás obsoletos."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--log-file", default="")

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        self.stdout.write(line)
        if self._log_handle:
            self._log_handle.write(line + "\n")
            self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = (
            open(options["log_file"], "w", encoding="utf-8")
            if options["log_file"] else None
        )
        try:
            self._run(options["dry_run"])
        finally:
            if self._log_handle:
                self._log_handle.close()

    def _md5(self, bucket, entry):
        """
        MD5 of the real GCS object (the index may not have it).

        ---

        Huella MD5 del objeto real de GCS (el índice puede no tenerla).
        """
        if entry.md5_hash:
            return entry.md5_hash
        blob = bucket.get_blob(entry.blob_name)
        return blob.md5_hash if blob is not None else None

    def _run(self, dry_run):
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        entry_ct = ContentType.objects.get_for_model(DocumentIndexEntry)
        people = {
            person.pk: person
            for person in PersonIdentity.objects.filter(
                is_active_employee=True,
            )
        }
        groups = defaultdict(list)
        for entry in DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            domain_content_type=person_ct,
            domain_object_id__in=list(people),
            document_type__isnull=False,
            is_obsolete=False,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            size_bytes__gt=0,
        ).select_related("document_type"):
            groups[(
                entry.domain_object_id, entry.document_type_id,
                entry.size_bytes,
            )].append(entry)
        candidates = [group for group in groups.values() if len(group) > 1]
        self._log("Inicio%s: %d grupo(s) con el mismo tamaño en %d "
                  "activo(s)." % (
                      " (SIMULACIÓN, no se guarda nada)" if dry_run else "",
                      len(candidates),
                      len({group[0].domain_object_id for group in candidates}),
                  ))
        bucket = get_storage_client().bucket("cgs_grupo_alvarez")
        marked = 0
        for position, group in enumerate(candidates, start=1):
            by_md5 = defaultdict(list)
            for entry in group:
                by_md5[self._md5(bucket, entry)].append(entry)
            person = people[group[0].domain_object_id]
            name = "%s %s, %s" % (
                person.first_surname, person.second_surname,
                person.given_name,
            )
            for md5, copies in by_md5.items():
                if md5 is None or len(copies) < 2:
                    continue
                copies.sort(key=lambda e: (
                    e.issue_date is None and e.expiry_date is None,
                    e.indexed_at, e.pk,
                ))
                keep, extra = copies[0], copies[1:]
                self._log("%d. %s -- %s: se conserva %s (%s); obsoletas: %s"
                          % (
                              position, name, keep.document_type.code,
                              keep.pk, keep.issue_date or keep.expiry_date
                              or "sin fecha",
                              ", ".join(
                                  "%s (%s)" % (e.pk, e.name) for e in extra
                              ),
                          ))
                marked += len(extra)
                if dry_run:
                    continue
                with transaction.atomic():
                    for entry in extra:
                        DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                            is_obsolete=True,
                        )
                        DocumentSubstitutionLog.objects.create(
                            company=person.company,
                            superseding_content_type=entry_ct,
                            superseding_object_id=keep.pk,
                            superseding_label=keep.name,
                            superseded_content_type=entry_ct,
                            superseded_object_id=entry.pk,
                            superseded_label=entry.name,
                            subject_label=name,
                            document_type=keep.document_type.code,
                            reasoning=(
                                "Mismo archivo indexado dos veces (MD5 "
                                "idéntico) -- S125."
                            ),
                        )
        self._log("Fin. Copias que quedan obsoletas: %d." % marked)
