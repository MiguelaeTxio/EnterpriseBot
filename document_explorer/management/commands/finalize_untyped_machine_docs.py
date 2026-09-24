# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/finalize_untyped_machine_docs.py
"""
H30 (S118), punto 7 de la hoja de ruta -- PASO D (cierre): reparto
final de los documentos SIN TIPO de máquinas ACTIVAS que quedan tras
los marcadores (paso B) y Gemini (paso C, todos "NINGUNO"), con las
decisiones de Miguel Ángel (S118, "1. Correcto. 2. Correcto. 3.
Correcto."):

1. Documentos de PERSONAS (DNI, NIE, pasaporte...): a su ficha si la
   persona es trabajador activo o dueño (--owner-pks); si no, papelera
   -- misma regla y misma identificación que el paso B
   (`classify_untyped_machine_text.resolve_person`).
2. Certificados de propiedad/titularidad firmados por el administrador
   -> CERT_PROPIEDAD (migración 0142).
3. Todo lo demás (documentos de empresa, folletos, DocuSign, COVID,
   citas de ITV, mandatos, listados, envíos, plantillas, escaneos
   vacíos, "Recibí manejo PEMP"...) -> papelera.

Sin texto legible (paso A), por el nombre: fotos -> IMAGEN, catálogo
de piezas -> MANUAL_DESPIECE, el resto -> papelera.

DRY-RUN por defecto; --apply escribe. Papelera = borrado blando
(deleted_at), nunca se toca GCS (4.12). Log propio (0bis).
---
H30 (S118), roadmap item 7 -- STEP D: final split of the remaining
untyped documents of active machines, per Miguel Ángel's decisions.
"""
import re
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.date_verification_service import (
    extract_dni_front_expiry,
    extract_dni_mrz_expiry,
)
from document_explorer.management.commands.classify_untyped_machine_text \
    import normalize, resolve_person
from document_explorer.models import (
    DocumentIndexEntry,
    DocumentTypeCatalog,
    PersonIdentity,
)
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"

# Documento de persona, por nombre de archivo o cabecera del texto.
PERSON_NAME_RE = re.compile(r"\b(DNI|D\.N\.I|NIE|PASAPORTE)\b")
PERSON_TEXT_CODES = [
    ("NIE", ["REGISTRO DE CIUDADANO DE LA UNION", "NUMERO DE IDENTIDAD DE "
             "EXTRANJERO"]),
    ("DNI", ["DOCUMENTO NACIONAL DE IDENTIDAD", "IDESP"]),
    ("PASAPORTE", ["PASAPORTE", "PASSPORT", "REISEPASS"]),
]
# Certificado de propiedad/titularidad firmado por el administrador.
OWNERSHIP_TEXT_RE = re.compile(
    r"COMO ADMINISTRADOR.{0,200}CERTIFICA QUE.{0,250}"
    r"(ES PROPIEDAD|TITULARIDAD|TITULAR)",
)
OWNERSHIP_NAME_RE = re.compile(r"CERT\.?\s*(PROPIEDAD|TITULARIDAD)")
# S118 -- revisados uno a uno tras el dry-run EnterpriseBot_016: 9 de
# los "NINGUNO" de Gemini son documentación real de la máquina, no
# ruido. Decisión de Miguel Ángel ("Ok"): se rescatan con estos tipos en
# vez de ir a la papelera.
RESCUED_TYPES = {
    6025: "REFORMA_VEHICULO",      # B-35 CERT. NEUMATICOS
    8461: "REV_TACOGRAFO",         # certificado limitador de velocidad
    10287: "ITV",                  # A-58 informe pesada (ITV de pesaje)
    10920: "CERT_REVISION",        # H-06 montaje puente grua
    14675: "CERT_REVISION",        # validez sensor de angulo Bronto
    10915: "CERT_REVISION",        # Cert quality (pruebas polipasto)
    19502: "ORDEN_TRABAJO_MANTENIMIENTO",  # 2018 07 11 MANTENIMIENTO
    17507: "INFORME_INCIDENCIAS",  # declaracion de RC (siniestro)
    3917: "INFORME_INCIDENCIAS",   # 9184.pdf (rechazo de siniestro)
}
PHOTO_NAME_RE = re.compile(r"\bFOTOS?\b|\bIMG|DANOS|WHATSAPP")
PARTS_NAME_RE = re.compile(r"CATALOGO\s+(DE\s+)?PARTES|DESPIECE|PARTS")


class Command(BaseCommand):
    help = (
        "H30 (S118) -- paso D del punto 7: reparto final (personas, "
        "certificados de propiedad, papelera) de los sin tipo de "
        "maquinas activas. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--owner-pks", default="",
            help="PersonIdentity pk de duenos (cuentan como activos).",
        )
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
        self._owner_pks = {
            int(pk) for pk in options["owner_pks"].split(",") if pk.strip()
        }
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        self._person_ct = ContentType.objects.get_for_model(PersonIdentity)
        self._catalog = {
            dt.code: dt for dt in DocumentTypeCatalog.objects.filter(
                is_active=True,
            )
        }
        active_pks = list(MachineAsset.objects.filter(
            is_active=True,
        ).values_list("pk", flat=True))
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=True,
            domain_content_type=machine_ct,
            domain_object_id__in=active_pks,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("id"))
        self._log(
            "PASO D -- MODO: %s -- %d documentos sin tipo de maquinas "
            "activas" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)", len(entries),
            )
        )
        actions = {}
        for entry in entries:
            action, detail = self._decide(entry)
            actions.setdefault(action, []).append((entry, detail))
            if apply_changes:
                self._apply(entry, action, detail)

        self._log_plain("=== RESUMEN PASO D (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for action, items in sorted(actions.items()):
            self._log_plain("  %s: %d" % (action, len(items)))
        for action, items in sorted(actions.items()):
            self._log_plain("--- %s ---" % action)
            for entry, detail in items:
                self._log_plain("    id=%d %s | %s" % (
                    entry.id, entry.name, detail.get("why", ""),
                ))

    def _decide(self, entry):
        """
        Return (action, detail) for one remaining untyped document.
        ---
        Decide la acción: PERSONA_A_FICHA, CERT_PROPIEDAD, IMAGEN,
        MANUAL_DESPIECE o PAPELERA.
        """
        if entry.id in RESCUED_TYPES:
            return RESCUED_TYPES[entry.id], {
                "why": "rescatado tras revision manual (S118)",
            }
        name = normalize(entry.name)
        text = normalize(entry.ocr_text)

        if not text.strip():
            if PHOTO_NAME_RE.search(name):
                return "IMAGEN", {"why": "sin texto; fotos por el nombre"}
            if PARTS_NAME_RE.search(name):
                return "MANUAL_DESPIECE", {
                    "why": "sin texto; catalogo de piezas por el nombre",
                }
            return "PAPELERA", {"why": "sin texto y sin tipo por el nombre"}

        person_code = None
        for code, phrases in PERSON_TEXT_CODES:
            if any(phrase in text[:1500] for phrase in phrases):
                person_code = code
                break
        if person_code is None and PERSON_NAME_RE.search(name):
            person_code = "DNI" if "DNI" in name or "D.N.I" in name else (
                "NIE" if "NIE" in name else "PASAPORTE"
            )
        if person_code:
            person, how = resolve_person(text, entry.name)
            active = bool(person) and (
                person.is_active_employee or person.pk in self._owner_pks
            )
            if active and person_code in self._catalog:
                return "PERSONA_A_FICHA", {
                    "why": "%s de %s (pk=%d) [%s]" % (
                        person_code, person, person.pk, how,
                    ),
                    "code": person_code, "person": person,
                    "text": entry.ocr_text,
                }
            reason = (
                "%s de %s (pk=%d), NO activa [%s]" % (
                    person_code, person, person.pk, how,
                ) if person else "%s sin ficha [%s]" % (person_code, how)
            )
            return "PAPELERA", {"why": "persona: " + reason}

        if OWNERSHIP_TEXT_RE.search(text[:1500]) or \
                OWNERSHIP_NAME_RE.search(name):
            return "CERT_PROPIEDAD", {
                "why": "certificado de propiedad del administrador",
            }
        return "PAPELERA", {"why": "no corresponde a ningun tipo"}

    def _apply(self, entry, action, detail):
        """
        Write the decided action for one document.
        ---
        Escribe la acción decidida para un documento.
        """
        qs = DocumentIndexEntry.objects.filter(pk=entry.pk)
        if action == "PAPELERA":
            qs.update(deleted_at=timezone.now())
        elif action == "PERSONA_A_FICHA":
            fields = {
                "document_type": self._catalog[detail["code"]],
                "domain_content_type": self._person_ct,
                "domain_object_id": detail["person"].pk,
            }
            if detail["code"] == "DNI":
                expiry = extract_dni_mrz_expiry(detail["text"]) or \
                    extract_dni_front_expiry(detail["text"])
                if expiry:
                    fields["expiry_date"] = expiry
            qs.update(**fields)
        elif action in self._catalog:
            qs.update(document_type=self._catalog[action])
