# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_driving_licence_cards.py
"""
H30 (S120) -- after the class harvest: retype the CARNET_CONDUCIR
entries that are not driving licences, and realign canonical names.
---
H30 (S120) -- tras la recolección de clases (harvest_driving_licence_
classes), dos arreglos sobre los carnés de las personas activas:

A. RETIPADO. La lectura de Gemini ya guardada en la caché del harvest
   (sin llamadas nuevas) marcó 34 documentos tipados `CARNET_CONDUCIR`
   que NO son un permiso de conducción -- origen: la etiqueta ambigua
   del tipo, "Carnet / tarjeta de conductor". Según la nota de Gemini:
   - solo tarjeta de tacógrafo -> `TACOGRAFO` (tipo ya existente,
     dominio Personal);
   - solo tarjeta CAP -> `CAP` (ídem);
   - mixtos (CAP + tacógrafo, tacógrafo + otra tarjeta) o ajenos
     (circulares, hojas informativas, solicitudes, justificantes):
     NO se tocan -- se listan para que Miguel Ángel decida uno a uno.
     Nunca se inventa un tipo.
B. REALINEADO de nombres canónicos con
   `apply_personal_canonical_rename()` (solo `name` en BD, nunca GCS,
   sin Gemini): los retipados (el tipo va en el nombre) y los carnés
   con matriz, cuya `expiry_date` cambió a la caducidad más lejana de
   sus clases (decisión 2 de Miguel Ángel, S120).

DRY-RUN por defecto; --apply escribe. Log propio (com-standards
0bis/0ter).
"""
import json
import re
import unicodedata
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from document_explorer.classification_service import (
    apply_personal_canonical_rename,
)
from document_explorer.models import (
    DocumentIndexEntry,
    DocumentTypeCatalog,
    DrivingLicenceGrant,
    PersonIdentity,
)

BUCKET = "cgs_grupo_alvarez"
CARD_CODE = "CARNET_CONDUCIR"
TACHO_CODE = "TACOGRAFO"
CAP_CODE = "CAP"
TACHO_RE = re.compile(r"tacograf")
CAP_RE = re.compile(r"\bcap\b|cualificacion del conductor")


def _plain(text):
    """
    Lowercase, accent-free text for keyword matching.
    ---
    Texto en minúsculas y sin tildes para buscar palabras clave.
    """
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).lower()


def _target_code(notes):
    """
    Return TACOGRAFO, CAP or None (manual review) from Gemini's note.
    ---
    Tipo destino según la nota de Gemini: TACOGRAFO si solo habla de
    tacógrafo, CAP si solo habla de CAP; None (revisión manual) si
    habla de ambos, de otra tarjeta más, o de ninguno.
    """
    plain = _plain(notes)
    is_tacho = bool(TACHO_RE.search(plain))
    is_cap = bool(CAP_RE.search(plain))
    mentions_other = "seguridad social" in plain
    if is_tacho and not is_cap and not mentions_other:
        return TACHO_CODE
    if is_cap and not is_tacho and not mentions_other:
        return CAP_CODE
    return None


class Command(BaseCommand):
    help = (
        "H30 (S120) -- retipa los CARNET_CONDUCIR que no son carnes y "
        "realinea nombres canonicos. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--cache-file", required=True,
            help="Cache JSON de harvest_driving_licence_classes.",
        )
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"], options["cache_file"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes, cache_path):
        with open(cache_path, encoding="utf-8") as handle:
            cache = json.load(handle)
        types = {
            catalog.code: catalog
            for catalog in DocumentTypeCatalog.objects.filter(
                code__in=[TACHO_CODE, CAP_CODE],
            )
        }
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        active_ids = list(PersonIdentity.objects.filter(
            is_active_employee=True,
        ).values_list("pk", flat=True))
        cards = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code=CARD_CODE,
            domain_content_type=person_ct,
            domain_object_id__in=active_ids,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").order_by("id"))
        self._log(
            "RETIPADO + REALINEADO (%s) -- %d carnes de activos, %d "
            "respuestas en cache" % (
                "APLICAR" if apply_changes else "DRY-RUN, nada se escribe",
                len(cards), len(cache),
            )
        )

        # --- A. Retipado ---------------------------------------------
        retyped, manual = [], []
        for entry in cards:
            answer = cache.get(str(entry.id))
            if not answer or answer.get("is_driving_licence", True):
                continue
            notes = answer.get("notes", "")
            code = _target_code(notes)
            if code is None:
                manual.append((entry, notes))
                continue
            retyped.append((entry, code))
            self._log("RETIPO id=%d %s -> %s" % (entry.id, entry.name, code))
            if apply_changes:
                with transaction.atomic():
                    DrivingLicenceGrant.objects.filter(entry=entry).delete()
                    DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                        document_type=types[code],
                    )
            # En memoria también en dry-run: el nombre canónico del
            # bloque B se calcula ya con el tipo nuevo (nunca se guarda
            # en dry-run: apply_changes=False no escribe).
            entry.document_type = types[code]
        self._log("--- REVISION MANUAL (no se tocan) ---")
        for entry, notes in manual:
            self._log("    id=%d %s -- %s" % (entry.id, entry.name, notes))

        # --- B. Realineado de nombres canónicos ----------------------
        cards_with_grants = set(DrivingLicenceGrant.objects.filter(
            entry__in=cards,
        ).values_list("entry_id", flat=True))
        to_rename = [entry for entry, _code in retyped] + [
            entry for entry in cards if entry.id in cards_with_grants
        ]
        reserved = set()
        stats = {"renamed": 0, "unchanged": 0, "not_built": 0}
        for index, entry in enumerate(to_rename, start=1):
            old_name = entry.name
            if apply_changes:
                entry.refresh_from_db()
            result = apply_personal_canonical_rename(
                entry, apply_changes=apply_changes, reserved_names=reserved,
            )
            new_name = result.get("new_name")
            if new_name is None:
                stats["not_built"] += 1
                self._log("SIN NOMBRE id=%d %s -- %s" % (
                    entry.id, old_name, result.get("reason"),
                ))
            elif new_name != old_name:
                stats["renamed"] += 1
                self._log("RENOMBRE id=%d %s -> %s" % (
                    entry.id, old_name, new_name,
                ))
            else:
                stats["unchanged"] += 1
            if index % 25 == 0 or index == len(to_rename):
                self._log("Progreso renombrado: %d/%d" % (
                    index, len(to_rename),
                ))

        self._log("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log("    retipados a TACOGRAFO: %d" % sum(
            1 for _entry, code in retyped if code == TACHO_CODE
        ))
        self._log("    retipados a CAP: %d" % sum(
            1 for _entry, code in retyped if code == CAP_CODE
        ))
        self._log("    para revision manual: %d" % len(manual))
        self._log("    nombres cambiados: %d" % stats["renamed"])
        self._log("    nombres ya correctos: %d" % stats["unchanged"])
        self._log("    sin nombre construible: %d" % stats["not_built"])
