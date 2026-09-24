# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/merge_machine_duplicate.py
"""
S117 (H30) -- fusiona una ficha de máquina DUPLICADA en la ficha buena.

Origen real: "3848BZW es la A50, la unificamos en su ficha" (Miguel
Ángel). 3848-BZW es la matrícula de la A-50; alguna ingesta antigua le
creó una segunda ficha con la matrícula como código.

Mueve a la ficha destino TODO lo que apunta a la duplicada, sin lista
escrita a mano (así no se escapa ninguna relación futura):
- toda relación directa (ForeignKey/OneToOne) de cualquier app hacia
  fleet.MachineAsset -- recorriendo MachineAsset._meta.related_objects
  (mantenimientos, partes, piezas, almacén, documentos de máquina,
  chat, destino de movimientos...);
- las relaciones genéricas a una máquina: DocumentIndexEntry
  (domain_content_type/domain_object_id) y SubjectDocumentReference
  (subject_content_type/subject_object_id).
Si una fila movida chocaría con una restricción de unicidad del destino
(la misma referencia ya existe en la ficha buena), esa fila duplicada se
borra en vez de moverse, y se informa.
Después completa en la ficha destino los campos VACÍOS con los de la
duplicada (nunca pisa un dato ya relleno) y borra la ficha duplicada.

DRY-RUN por defecto (solo cuenta y lista); --apply escribe, todo en una
transacción. Log propio (com-standards 0bis/0ter).
"""
import re
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from document_explorer.models import DocumentIndexEntry, SubjectDocumentReference
from fleet.models import MachineAsset

FILLABLE_FIELDS = ("plate", "brand_model", "family", "company_code", "company_name")


def _norm(code):
    return re.sub(r"[\s\-.]", "", str(code or "")).upper()


class Command(BaseCommand):
    help = "S117 -- fusiona una ficha de maquina duplicada en la buena. Dry-run por defecto."

    def add_arguments(self, parser):
        parser.add_argument("--duplicate", required=True, help="Codigo de la ficha duplicada (se borra).")
        parser.add_argument("--target", required=True, help="Codigo de la ficha buena (se conserva).")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def _one(self, code):
        # S117: primero el código EXACTO -- "X01" y "X-01" son justo las
        # dos fichas duplicadas que se quieren fusionar, y sin guion
        # serían indistinguibles. La comparación normalizada queda de
        # respaldo (p. ej. "Z010" escrito como "z010").
        matches = list(MachineAsset.objects.filter(code__iexact=code.strip()))
        if not matches:
            matches = [a for a in MachineAsset.objects.all() if _norm(a.code) == _norm(code)]
        if len(matches) != 1:
            raise CommandError("'%s' no identifica una sola ficha (%d)." % (code, len(matches)))
        return matches[0]

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["duplicate"], options["target"], options["apply"])
        finally:
            self._log_handle.close()

    def _move(self, queryset, field_values, apply_changes, label):
        moved = dropped = 0
        for row in list(queryset):
            if apply_changes:
                try:
                    with transaction.atomic():
                        for field, value in field_values.items():
                            setattr(row, field, value)
                        row.save(update_fields=list(field_values))
                    moved += 1
                except IntegrityError:
                    row.delete()
                    dropped += 1
            else:
                moved += 1
        if moved or dropped:
            self._log("    %-55s movidas=%d%s" % (label, moved, (" borradas por duplicadas=%d" % dropped) if dropped else ""))
        return moved + dropped

    def _run(self, duplicate_code, target_code, apply_changes):
        duplicate = self._one(duplicate_code)
        target = self._one(target_code)
        if duplicate.pk == target.pk:
            raise CommandError("Duplicada y destino son la misma ficha.")
        self._log("MODO: %s -- duplicada %s (pk=%d) -> destino %s (pk=%d)" % (
            "APLICAR (escribe)" if apply_changes else "DRY-RUN (no escribe nada)",
            duplicate.code, duplicate.pk, target.code, target.pk,
        ))
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        total = 0
        with transaction.atomic():
            for relation in MachineAsset._meta.related_objects:
                if not (relation.one_to_many or relation.one_to_one):
                    continue
                model = relation.related_model
                field = relation.field.name
                total += self._move(
                    model.objects.filter(**{field: duplicate}), {field: target},
                    apply_changes, "%s.%s" % (model._meta.label, field),
                )
            total += self._move(
                DocumentIndexEntry.objects.filter(domain_content_type=machine_ct, domain_object_id=duplicate.pk),
                {"domain_object_id": target.pk}, apply_changes, "document_explorer.DocumentIndexEntry (documentos)",
            )
            total += self._move(
                SubjectDocumentReference.objects.filter(subject_content_type=machine_ct, subject_object_id=duplicate.pk),
                {"subject_object_id": target.pk}, apply_changes, "document_explorer.SubjectDocumentReference",
            )
            filled = []
            for field in FILLABLE_FIELDS:
                if not getattr(target, field) and getattr(duplicate, field):
                    filled.append("%s=%s" % (field, getattr(duplicate, field)))
                    if apply_changes:
                        setattr(target, field, getattr(duplicate, field))
            self._log("    campos vacios del destino completados: %s" % (", ".join(filled) or "ninguno"))
            if apply_changes:
                target.save()
                duplicate.delete()
        self._log("=== RESUMEN (%s) ===" % ("APLICADO" if apply_changes else "DRY-RUN, nada escrito"))
        self._log("    filas que apuntaban a la duplicada: %d -- ficha duplicada %s" % (
            total, "BORRADA" if apply_changes else "se borraria",
        ))
