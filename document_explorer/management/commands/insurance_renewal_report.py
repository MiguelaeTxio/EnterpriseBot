# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/insurance_renewal_report.py
"""
Read-only report of the insurance documents of the active cost centres
and of the company, with the policy data read by Gemini from each
document (insurer, broker, policy number, cover, premium, dates).

---

H31 (S152). Informe de solo lectura de los documentos de seguro de los
centros de gasto activos y de la empresa, con los datos de la póliza
leídos por Gemini de cada documento (aseguradora, mediador, número de
póliza, cobertura, prima, fechas). Encargo de Alejandro Álvarez
(11/11/2026): "sacarme un listado de todos los seguros con la
información necesaria para su renovación de precio y demas con los
mediadores de seguros" (Hoja de Ruta S152, punto 1).

Documentos que entran:
- De cada centro de gasto activo, el último documento vigente (no
  obsoleto, no en papelera) de cada tipo de seguro: recibo (SEGURO),
  póliza (POLIZA_SEGURO) y certificado (CERTIFICADO_SEGURO), por
  caducidad y, a igualdad, por emisión.
- Además, cualquier otro documento vigente de seguro de un centro de
  gasto activo que caduque desde hoy hasta --until (por defecto el
  31/12/2026), para que estén todos los recibos de diciembre.
- Los documentos de seguro de la empresa: los que no cuelgan de una
  máquina ni de una persona, fuera de carpetas de obsoletos y
  siniestros.

Los centros de gasto activos sin ningún documento de seguro salen
aparte, con el texto de seguro de la ficha (Excel de maquinaria).

El texto OCR del panel falta en 434 de los 628 documentos de seguro
(consulta del 12/11/2026), así que se lee el propio documento (PDF o
imagen) con Gemini en vez del OCR. No escribe nada en BD ni en el cubo.
"""
import json
from datetime import date
from datetime import datetime
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
import fitz  # PyMuPDF, ya en requirements
from google.genai.types import GenerateContentConfig
from google.genai.types import HttpOptions
from google.genai.types import Part
from google.genai.types import ThinkingConfig

from ai_services.document_vision_service import (
    _generate_content_with_retry)
from ai_services.document_vision_service import extract_pages
from ai_services.gemini_client import DEFAULT_MODEL
from ai_services.gemini_client import get_gemini_client
from document_explorer.models import DocumentIndexEntry
from document_explorer.models import PersonIdentity
from fleet.models import MachineAsset
from spare_parts.gcs_service import get_storage_client

MACHINE_TYPES = ("SEGURO", "POLIZA_SEGURO", "CERTIFICADO_SEGURO")
COMPANY_TYPES = MACHINE_TYPES + (
    "POLIZA_SEGURO_EMPRESA", "CONDICIONES_GENERALES_SEGURO",
    "CARTA_VERDE")
# Carpetas de la empresa que no son seguros en vigor.
COMPANY_EXCLUDED_WORDS = ("OBSOLET", "SINIESTRO")
MAX_PAGES = 8
MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}

_NULLABLE_STRING = {"type": "string", "nullable": True}
_NULLABLE_NUMBER = {"type": "number", "nullable": True}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_kind": {
            "type": "string",
            "enum": ["recibo", "poliza", "certificado", "carta_verde",
                     "condiciones_generales", "listado", "otro"],
        },
        "insurer": _NULLABLE_STRING,
        "broker": _NULLABLE_STRING,
        "policy_number": _NULLABLE_STRING,
        "policyholder": _NULLABLE_STRING,
        "insured_plates": {"type": "array", "items": {"type": "string"}},
        "insured_object": _NULLABLE_STRING,
        "cover": _NULLABLE_STRING,
        "total_premium": _NULLABLE_NUMBER,
        "net_premium": _NULLABLE_NUMBER,
        "payment_frequency": _NULLABLE_STRING,
        "period_start": _NULLABLE_STRING,
        "period_end": _NULLABLE_STRING,
        "renewal_date": _NULLABLE_STRING,
        "notes": _NULLABLE_STRING,
    },
    "required": [
        "document_kind", "insurer", "broker", "policy_number",
        "policyholder", "insured_plates", "insured_object", "cover",
        "total_premium", "net_premium", "payment_frequency",
        "period_start", "period_end", "renewal_date", "notes",
    ],
}

PROMPT = """Este documento es un seguro de vehículo, maquinaria o de una
empresa del Grupo Álvarez (grúas). Lee el documento completo y devuelve
solo lo que conste en él, sin inventar nada. Si un dato no consta, null.

- document_kind: recibo (cobro de la prima de un periodo), poliza
  (condiciones particulares o póliza completa), certificado (certificado
  de seguro o de cobertura), carta_verde, condiciones_generales,
  listado (lista de varios vehículos o pólizas) u otro.
- insurer: compañía aseguradora (Allianz, AXA, Mapfre, Generali...).
- broker: mediador, corredor o agente (correduría, agencia o agente con
  su nombre; también su clave o código si aparece). No la aseguradora.
- policy_number: número de póliza tal cual figura.
- policyholder: tomador del seguro.
- insured_plates: matrículas o números de bastidor de los vehículos o
  máquinas asegurados que aparezcan.
- insured_object: qué se asegura (vehículo con marca y modelo, flota,
  responsabilidad civil de la empresa, maquinaria...).
- cover: modalidad y coberturas principales, en una frase corta
  (p. ej. "terceros ampliado con lunas y asistencia", "todo riesgo con
  franquicia de 600 EUR", "RC general hasta 1.200.000 EUR").
- total_premium: importe total a pagar del recibo o prima total anual de
  la póliza, en euros, como número (1234.56).
- net_premium: prima neta, si consta.
- payment_frequency: anual, semestral, trimestral, mensual...
- period_start / period_end: periodo de cobertura del documento, en
  formato AAAA-MM-DD.
- renewal_date: fecha de vencimiento o renovación de la póliza, en
  formato AAAA-MM-DD.
- notes: cualquier dato útil para renegociar el precio con el mediador
  (bonificaciones, franquicias, número de siniestros, capital
  asegurado), en una frase. null si no hay nada.

Responde únicamente con el JSON solicitado."""


class Command(BaseCommand):
    """
    Build the insurance renewal report as JSON (read-only).

    ---

    Genera el informe de seguros para la renovación en JSON (solo
    lectura).
    """

    help = ("Informe de solo lectura de los seguros de los centros de "
            "gasto activos y de la empresa, con los datos de cada "
            "documento leídos por Gemini.")

    def add_arguments(self, parser):
        parser.add_argument("--until", default="2026-12-31",
                            help="Incluye también todos los documentos de "
                                 "seguro de centros de gasto activos que "
                                 "caducan hasta esta fecha (AAAA-MM-DD).")
        parser.add_argument("--output", required=True,
                            help="Ruta del JSON de salida.")
        parser.add_argument("--log", default="",
                            help="Fichero de log (por defecto, el JSON "
                                 "con .log).")
        parser.add_argument("--limit", type=int, default=0,
                            help="Solo los N primeros documentos (prueba).")

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._log_file.write(line + "\n")
        self._log_file.flush()

    def handle(self, *args, **options):
        log_path = options["log"] or options["output"] + ".log"
        until = datetime.strptime(options["until"], "%Y-%m-%d").date()
        with open(log_path, "a", encoding="utf-8") as log_file:
            self._log_file = log_file
            report = self._build(until, options["limit"])
        with open(options["output"], "w", encoding="utf-8") as out:
            json.dump(report, out, ensure_ascii=False, indent=1)
        print("Informe escrito: %s (%d documentos)" % (
            options["output"], len(report["documents"])), flush=True)

    def _build(self, until, limit):
        today = date.today()
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        alive = DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            is_obsolete=False,
        ).select_related("document_type")
        machines = {
            machine.pk: machine
            for machine in MachineAsset.objects.filter(is_active=True)
        }

        by_machine = {}
        for entry in alive.filter(domain_content_type=machine_ct,
                                  domain_object_id__in=list(machines),
                                  document_type__code__in=MACHINE_TYPES):
            by_machine.setdefault(entry.domain_object_id, []).append(entry)

        selected = []
        for machine_id, docs in by_machine.items():
            chosen = set()
            for type_code in MACHINE_TYPES:
                same_type = [d for d in docs
                             if d.document_type.code == type_code]
                if same_type:
                    chosen.add(max(same_type, key=_recency).pk)
            for doc in docs:
                if doc.expiry_date and today <= doc.expiry_date <= until:
                    chosen.add(doc.pk)
            for doc in docs:
                if doc.pk in chosen:
                    selected.append((doc, machines[machine_id]))

        company_docs = alive.filter(
            document_type__code__in=COMPANY_TYPES,
        ).exclude(domain_content_type__in=[machine_ct, person_ct])
        for doc in company_docs:
            path = (doc.parent_path + "/" + doc.name).upper()
            if any(word in path for word in COMPANY_EXCLUDED_WORDS):
                continue
            if _mime_type(doc) is None:
                continue
            selected.append((doc, None))

        selected.sort(key=lambda pair: (
            pair[1] is None, pair[1].code if pair[1] else "", pair[0].pk))
        if limit:
            selected = selected[:limit]
        without = sorted(
            (m for m in machines.values() if m.pk not in by_machine),
            key=lambda m: m.code)
        self._log("Centros de gasto activos: %d; con seguro en el panel: "
                  "%d; sin seguro: %d. Documentos a leer: %d." % (
                      len(machines), len(by_machine), len(without),
                      len(selected)))

        storage = get_storage_client()
        client = get_gemini_client()
        documents = []
        start = datetime.now()
        counters = {"leidos": 0, "errores": 0}
        for position, (doc, machine) in enumerate(selected, start=1):
            item = self._read(storage, client, doc, machine)
            documents.append(item)
            counters["errores" if item["error"] else "leidos"] += 1
            self._log("%d/%d %s %s (%s): %s" % (
                position, len(selected), machine.code if machine else
                "EMPRESA", doc.name, doc.document_type.code,
                item["error"] or "%s, póliza %s, prima %s" % (
                    (item["data"] or {}).get("insurer"),
                    (item["data"] or {}).get("policy_number"),
                    (item["data"] or {}).get("total_premium"))))
            self._progress(position, len(selected), start, counters)
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "today": today.isoformat(),
            "until": until.isoformat(),
            "documents": documents,
            "machines_without_insurance": [
                _machine_dict(m) for m in without],
        }

    def _progress(self, done, total, start, counters):
        if done % 10 and done != total:
            return
        elapsed = (datetime.now() - start).total_seconds()
        eta_seconds = elapsed / done * (total - done)
        end = datetime.now() + timedelta(seconds=eta_seconds)
        self._log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. "
                  "%s) -- leidos=%d, errores=%d" % (
                      done, total, done * 100 // total,
                      eta_seconds // 60, eta_seconds % 60,
                      end.strftime("%H:%M:%S"), counters["leidos"],
                      counters["errores"]))

    def _read(self, storage, client, doc, machine):
        item = {
            "id": doc.pk,
            "type": doc.document_type.code,
            "name": doc.name,
            "path": doc.parent_path,
            "bucket": doc.bucket,
            "blob": doc.blob_name,
            "expiry_date": (doc.expiry_date.isoformat()
                            if doc.expiry_date else None),
            "issue_date": (doc.issue_date.isoformat()
                           if doc.issue_date else None),
            "domain": (doc.domain_content_type.model
                       if doc.domain_content_type_id else None),
            "machine": _machine_dict(machine) if machine else None,
            "data": None,
            "error": "",
        }
        mime_type = _mime_type(doc)
        if mime_type is None:
            item["error"] = "formato no legible: %s" % doc.name
            return item
        try:
            blob = storage.bucket(doc.bucket).get_blob(doc.blob_name)
            if blob is None:
                item["error"] = "no está en el cubo"
                return item
            content = blob.download_as_bytes()
            if mime_type == "application/pdf":
                content = _first_pages(content)
            response = _generate_content_with_retry(
                client,
                model=DEFAULT_MODEL,
                contents=[Part.from_bytes(data=content,
                                          mime_type=mime_type), PROMPT],
                config=GenerateContentConfig(
                    http_options=HttpOptions(timeout=120_000),
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    thinking_config=ThinkingConfig(thinking_level="low"),
                    temperature=0.0,
                ),
            )
            item["data"] = json.loads(response.text.strip())
        except Exception as exc:  # noqa: BLE001 -- se informa y se sigue
            item["error"] = "error al leer: %s" % str(exc)[:300]
        return item


def _recency(doc):
    """
    Sort key: expiry date, then issue date (missing dates first).

    ---

    Clave de orden: caducidad y, a igualdad, emisión (sin fecha, antes).
    """
    return (doc.expiry_date or date.min, doc.issue_date or date.min, doc.pk)


def _mime_type(doc):
    """
    MIME type Gemini can read for this document, or None.

    ---

    Tipo MIME legible por Gemini para este documento, o None.
    """
    if "." not in doc.name:
        return None
    extension = doc.name.rsplit(".", 1)[-1].lower()
    return MIME_BY_EXTENSION.get(extension)


def _first_pages(pdf_bytes):
    """
    The first MAX_PAGES pages of a PDF (the whole PDF if shorter or
    unreadable).

    ---

    Las MAX_PAGES primeras páginas de un PDF (el PDF entero si es más
    corto o no se puede abrir).
    """
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            pages = pdf.page_count
    except Exception:  # noqa: BLE001 -- se manda tal cual
        return pdf_bytes
    if pages <= MAX_PAGES:
        return pdf_bytes
    return extract_pages(pdf_bytes, list(range(1, MAX_PAGES + 1)))


def _machine_dict(machine):
    """
    The cost-centre fields the report needs.

    ---

    Los campos del centro de gasto que necesita el informe.
    """
    return {
        "id": machine.pk,
        "code": machine.code,
        "plate": machine.plate,
        "company_code": machine.company_code,
        "company_name": machine.company_name,
        "family": machine.family,
        "type_name": machine.type_name,
        "brand_model": machine.brand_model,
        "insurance_info": machine.insurance_info,
    }
