# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/backfill_lifting_accessories_s121.py
"""
H30 (S121). Alta de los accesorios de elevación que ya tienen su
certificado en el bucket, y tipado correcto de los documentos
relacionados. Datos en document_explorer/data/lifting_accessories_s121
.json, sacados de la revisión del CONTENIDO REAL de cada documento
(relevo gcs_image + OCR, comprobado a ojo donde el OCR dudaba) y
validados por Miguel Ángel en S121:

1. Cambios de tipo (13): cables/componentes de la propia grúa ->
   CERT_COMPONENTE_MAQUINA; adecuación OCA -> C_ADECUACION; revisiones
   de eslingas de la A-22 -> REVISION_ESLINGAS; pedido 2006 por lotes ->
   CERT_ACCESORIO_ELEVACION (histórico, sin accesorios: "ya no se sabe
   ni dónde estarán"); catálogo Bezabala -> MANUAL_USO. Solo cambia el
   tipo (y, donde se indica, el sujeto copiado de otro documento ya
   vinculado); el archivo nunca se toca.
2. Papelera (11): duplicados exactos comprobados píxel a píxel (8 .jpg
   de Huelva, 2 páginas extraídas de 8184, la versión comprimida del
   pedido 2006). Papelera recuperable (trash_dossier_entry, H29).
3. Accesorios (259), en servicio, sin entrega (los certificados no
   dicen a quién ni a qué centro de gasto se entregó cada uno): uno por
   certificado individual. En los PDF que agrupan certificados (8160,
   8184, 8185, 8188) cada página se guarda como PDF propio, tipado y
   enlazado a su accesorio ("un PDF por certificado"); el original se
   conserva. Los demás se enlazan tal cual.
4. Modelos (13) y trazabilidad (S121, entrega por modelo): crea el
   catálogo de modelos y asigna a cada accesorio su modelo y su código
   de trazabilidad tal como viene impreso en su certificado (lo que va
   en la etiqueta según EN 1492-1). Nunca pisa un modelo o una
   trazabilidad que ya tenga el accesorio (corregidos en el panel).

DRY-RUN POR DEFECTO: comprueba que todo existe y cuenta lo que haría.
Con --apply escribe. Idempotente: se puede repetir sin duplicar nada.
"""

import json
import os
from datetime import date

import fitz
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer import lifting_accessory_service as service
from document_explorer.classification_service import (
    _resolve_dossier_trash_user,
    trash_dossier_entry,
)
from document_explorer.models import (
    DocumentIndexEntry,
    DocumentTypeCatalog,
    LiftingAccessory,
    LiftingAccessoryModel,
    LiftingAccessoryType,
)
from spare_parts.gcs_service import download_bytes

DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data",
    "lifting_accessories_s121.json",
)


def _single_page(data, page_number):
    """
    Bytes of a new one-page PDF with page `page_number` (1-based).
    ---
    Bytes de un PDF nuevo de una sola página, la `page_number` (contada
    desde 1) -- mismo método que split_rm_dossier.
    """
    source = fitz.open(stream=data, filetype="pdf")
    try:
        if page_number > source.page_count:
            raise ValueError(
                "página %d de %d" % (page_number, source.page_count),
            )
        target = fitz.open()
        target.insert_pdf(
            source, from_page=page_number - 1, to_page=page_number - 1,
        )
        out = target.tobytes()
        target.close()
        return out
    finally:
        source.close()


class Command(BaseCommand):
    help = (
        "H30 (S121) -- alta de los accesorios de elevación del bucket "
        "con su certificado, y tipado de los documentos relacionados. "
        "Dry-run por defecto; --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad (sin esto, solo comprueba y cuenta).",
        )
        parser.add_argument(
            "--log-file", default=None,
            help="Archivo de log (pantalla y archivo a la vez, flush por "
                 "línea -- com-standards 0bis).",
        )

    def out(self, message):
        """
        Write one line to screen and log file, flushed.
        ---
        Escribe una línea en pantalla y en el log, con flush.
        """
        self.stdout.write(message)
        self.stdout.flush()
        if self.log_handle is not None:
            self.log_handle.write(message + "\n")
            self.log_handle.flush()

    def handle(self, *args, **options):
        self.log_handle = (
            open(options["log_file"], "a", encoding="utf-8")
            if options["log_file"] else None
        )
        try:
            self._run(options["apply"])
        finally:
            if self.log_handle is not None:
                self.log_handle.close()

    def _run(self, apply):
        with open(DATA_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        admin = _resolve_dossier_trash_user()
        if admin is None:
            raise CommandError(
                "No se resuelve el CompanyUser de la papelera; no se hace "
                "nada.",
            )
        company = admin.company
        self.out("# Modo: %s | empresa: %s" % (
            "APPLY" if apply else "DRY-RUN", company,
        ))
        errors = []
        self._retypes(data["retypes"], apply, errors)
        self._trash(data["trash"], apply, errors)
        self._accessories(data["accessories"], company, apply, errors)
        self._models(data["models"], data["accessories"], company, apply,
                     errors)
        self.out("\n# ERRORES: %d" % len(errors))
        for error in errors:
            self.out("  - %s" % error)
        self.out("# FIN (%s)" % ("APPLY" if apply else "DRY-RUN"))

    def _live(self, pk):
        return DocumentIndexEntry.objects.filter(
            pk=pk, deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").first()

    def _retypes(self, retypes, apply, errors):
        self.out("\n## 1. Cambios de tipo (%d)" % len(retypes))
        done = 0
        for item in retypes:
            entry = self._live(item["id"])
            doc_type = DocumentTypeCatalog.objects.filter(
                code=item["type"],
            ).first()
            if entry is None or doc_type is None:
                errors.append("retipo %s: documento o tipo %s inexistente"
                              % (item["id"], item["type"]))
                continue
            source = None
            if item.get("subject_from"):
                source = self._live(item["subject_from"])
                if source is None or source.domain_object_id is None:
                    errors.append("retipo %s: sujeto de %s no resuelto"
                                  % (item["id"], item["subject_from"]))
                    continue
            before = entry.document_type.code if entry.document_type else "-"
            self.out("  %s: %s -> %s%s | %s" % (
                entry.pk, before, doc_type.code,
                " (sujeto de %s)" % source.pk if source else "",
                item["note"],
            ))
            if apply:
                entry.document_type = doc_type
                fields = ["document_type"]
                if source is not None:
                    entry.domain_content_type_id = (
                        source.domain_content_type_id
                    )
                    entry.domain_object_id = source.domain_object_id
                    fields += ["domain_content_type", "domain_object_id"]
                entry.save(update_fields=fields)
            done += 1
        self.out("  -> %d %s" % (
            done, "aplicados" if apply else "a aplicar",
        ))

    def _trash(self, trash, apply, errors):
        self.out("\n## 2. Papelera (%d)" % len(trash))
        done = skipped = 0
        for item in trash:
            entry = self._live(item["id"])
            if entry is None:
                skipped += 1
                self.out("  %s: ya en papelera o inexistente"
                                  % item["id"])
                continue
            self.out("  %s: %s | %s" % (
                entry.pk, entry.name, item["note"],
            ))
            if apply and not trash_dossier_entry(entry):
                errors.append("papelera %s: no aplicada" % entry.pk)
                continue
            done += 1
        self.out("  -> %d %s, %d ya estaban" % (
            done, "enviados" if apply else "a enviar", skipped,
        ))

    def _accessories(self, items, company, apply, errors):
        self.out("\n## 3. Accesorios (%d)" % len(items))
        cert_type = DocumentTypeCatalog.objects.get(
            code=service.CERTIFICATE_TYPE_CODE,
        )
        accessory_ct = ContentType.objects.get_for_model(LiftingAccessory)
        types = {t.code: t for t in LiftingAccessoryType.objects.all()}
        sources = {}
        created = existing = certificates = 0
        for number, item in enumerate(items, start=1):
            if number % 25 == 0:
                self.out("  ... %d/%d" % (number, len(items)))
            label = "%s %s" % (item["type"], item["identifier"])
            accessory_type = types.get(item["type"])
            source = self._live(item["source"])
            if accessory_type is None or source is None:
                errors.append("%s: tipo o documento %s inexistente"
                              % (label, item["source"]))
                continue
            if not apply:
                exists = LiftingAccessory.objects.filter(
                    company=company, accessory_type=accessory_type,
                    identifier=item["identifier"],
                ).exists()
                existing += exists
                created += not exists
                certificates += 1
                continue
            try:
                with transaction.atomic():
                    accessory, was_created = (
                        LiftingAccessory.objects.get_or_create(
                            company=company,
                            accessory_type=accessory_type,
                            identifier=item["identifier"],
                            defaults={
                                "description": item["description"],
                                "dimensions": item["dimensions"],
                                "working_load_kg": item["working_load_kg"],
                                "standard": item["standard"],
                                "manufacturer": item["manufacturer"],
                                "traceability": item.get(
                                    "traceability", "",
                                ),
                                "supply_date": (
                                    date.fromisoformat(item["supply_date"])
                                    if item["supply_date"] else None
                                ),
                                "is_active": True,
                            },
                        )
                    )
                    if item["page"]:
                        if source.pk not in sources:
                            sources[source.pk] = download_bytes(
                                source.bucket, source.blob_name,
                            )
                        page_bytes = _single_page(
                            sources[source.pk], item["page"],
                        )
                        filename = "%s_%s_CERT_ACCESORIO_ELEVACION.pdf" % (
                            accessory_type.code,
                            service._safe_segment(item["identifier"]),
                        )
                        service.store_document(
                            accessory, page_bytes, "pdf",
                            service.CERTIFICATE_TYPE_CODE,
                            service.CERTIFICATES_ROOT, filename,
                            issue_date=accessory.supply_date,
                        )
                    else:
                        fields = []
                        if source.document_type_id != cert_type.pk:
                            source.document_type = cert_type
                            fields.append("document_type")
                        if (source.issue_date is None
                                and accessory.supply_date):
                            source.issue_date = accessory.supply_date
                            fields.append("issue_date")
                        if fields:
                            source.save(update_fields=fields)
                        if not (source.domain_content_type_id
                                == accessory_ct.pk
                                and source.domain_object_id
                                == accessory.pk):
                            service.link_certificate(accessory, source)
            except Exception as exc:  # noqa: BLE001 -- se sigue con el resto
                errors.append("%s: %s" % (label, exc))
                continue
            created += was_created
            existing += not was_created
            certificates += 1
        self.out("  -> fichas %s: %d | ya existían: %d | "
                          "certificados %s: %d" % (
                              "creadas" if apply else "a crear", created,
                              existing,
                              "enlazados" if apply else "a enlazar",
                              certificates,
                          ))

    def _models(self, models_data, items, company, apply, errors):
        self.out("\n## 4. Modelos (%d) y trazabilidad" % len(models_data))
        types = {t.code: t for t in LiftingAccessoryType.objects.all()}
        by_key = {}
        new_models = 0
        for spec in models_data:
            accessory_type = types.get(spec["type"])
            if accessory_type is None:
                errors.append("modelo %s: tipo %s inexistente"
                              % (spec["key"], spec["type"]))
                continue
            model = LiftingAccessoryModel.objects.filter(
                accessory_type=accessory_type, name=spec["name"],
            ).first()
            if model is None:
                new_models += 1
                if apply:
                    model = LiftingAccessoryModel.objects.create(
                        accessory_type=accessory_type,
                        name=spec["name"],
                        dimensions=spec["dimensions"],
                        working_load_kg=spec["working_load_kg"],
                        standard=spec["standard"],
                        display_order=spec["display_order"],
                    )
            by_key[spec["key"]] = model
        set_model = set_trace = 0
        for item in items:
            accessory = LiftingAccessory.objects.filter(
                company=company, accessory_type__code=item["type"],
                identifier=item["identifier"],
            ).first()
            if accessory is None:
                if apply:
                    errors.append("modelo: accesorio %s %s inexistente"
                                  % (item["type"], item["identifier"]))
                continue
            fields = []
            model = by_key.get(item["model"])
            if accessory.model_id is None:
                set_model += 1
                if model is not None:
                    accessory.model = model
                    fields.append("model")
            if item["traceability"] and not accessory.traceability:
                set_trace += 1
                accessory.traceability = item["traceability"]
                fields.append("traceability")
            if apply and fields:
                accessory.save(update_fields=fields + ["updated_at"])
        verb = "" if apply else "a "
        self.out("  -> modelos %screar: %d | accesorios con modelo "
                 "%sasignar: %d | trazabilidades %sguardar: %d" % (
                     "" if apply else "a ", new_models, verb, set_model,
                     verb, set_trace,
                 ))
