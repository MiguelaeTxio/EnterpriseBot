# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/tirea_extraction.py
"""
H37 (S132). Data extraction from a photo of a TIREA albarán.

---

H37 (S132). Extracción de datos de una foto (o PDF) del albarán de
TIREA con Gemini Vision, para dar de alta la orden de trabajo de
asistencia. Miguel Ángel, S132: "el supervisor sacará una foto del
albarán, la sube y a partir de ahí es cuando empezamos a generar el
albarán". Ya decidido en H17-S002: fuente de entrada única, foto del
albarán de TIREA procesada por Gemini Vision.

Los campos siguen la pantalla real del albarán de TIREA que aportó
Miguel Ángel en S132 (bloques Servicio, Vehículo y conductor,
Recogida, Entrega y el lateral de Fallido/Facturable/Comentarios), con
los mismos nombres que `WorkOrderAssistance`. Lo que TIREA llama
"Chófer" y "Grúa" son el conductor y la máquina de la empresa
asignados en TIREA: se devuelven tal cual, como pista para la unidad.

La extracción nunca guarda nada: devuelve un diccionario que la vista
usa como valores iniciales del formulario de alta, que el supervisor
revisa antes de crear la orden.
"""
import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    Part,
    ThinkingConfig,
)

from ai_services.document_vision_service import _generate_content_with_retry
from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

logger = logging.getLogger(__name__)

TEXT_FIELDS = (
    "insurer_name", "provider_code", "client_name", "client_company",
    "expediente", "policy_number", "location_elapsed", "insured_name",
    "client_phone", "vehicle_plate", "vehicle_model", "vehicle_brand",
    "vehicle_color", "vehicle_type_label", "vehicle_subtype_label",
    "breakdown_description", "breakdown_code", "pickup_type",
    "pickup_province", "vehicle_locality", "pickup_country", "pickup_cp",
    "pickup_location", "delivery_type", "delivery_province",
    "delivery_locality", "delivery_country", "delivery_address",
    "ris_motive", "insurer_comments", "company_observations",
    "tirea_driver", "tirea_machine",
)
DATETIME_FIELDS = (
    "request_time", "service_datetime", "service_start_time",
    "arrival_time", "load_time", "completion_time",
)
DECIMAL_FIELDS = (
    "vehicle_weight", "vehicle_height", "vehicle_length", "vehicle_pma",
    "vehicle_tare", "driver_km", "total_km_tirea",
)
INTEGER_FIELDS = ("vehicle_axes", "num_passengers")
BOOLEAN_FIELDS = ("is_failed", "is_billable")

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "string"} for name in TEXT_FIELDS},
        **{name: {"type": "string"} for name in DATETIME_FIELDS},
        **{name: {"type": "string"} for name in DECIMAL_FIELDS},
        **{name: {"type": "string"} for name in INTEGER_FIELDS},
        **{name: {"type": "string"} for name in BOOLEAN_FIELDS},
    },
    "required": list(
        TEXT_FIELDS + DATETIME_FIELDS + DECIMAL_FIELDS + INTEGER_FIELDS
        + BOOLEAN_FIELDS
    ),
}

_PROMPT = """La imagen es una captura o foto de un albarán de servicio de
asistencia en carretera de la aplicación TIREA (pantalla "Albarán" con los
bloques Servicio, Vehículo y conductor, Recogida, Entrega y un lateral con
Fallido, Facturable, Comentarios, Chófer y Grúa).

Devuelve SOLO lo que se lee en la imagen, sin inventar nada. Si un campo
está vacío o no se ve, devuelve una cadena vacía "".

Correspondencia de campos (etiqueta en TIREA -> clave):
- Compañía -> insurer_name
- Cod. proveedor -> provider_code
- Cliente -> client_name
- Compañía cliente -> client_company
- Expediente -> expediente
- Nº póliza o Póliza, si aparece -> policy_number
- F. solicitud -> request_time
- F. servicio -> service_datetime
- F. inicio -> service_start_time
- F. localizado -> arrival_time
- F. cargado -> load_time
- F. finalizado -> completion_time
- Tiempo localizado -> location_elapsed (tal cual, p. ej. "01h:53m")
- Conductor (del vehículo asistido) -> insured_name
- Teléfono Móvil (del bloque Vehículo y conductor) -> client_phone
- Matrícula -> vehicle_plate
- Modelo -> vehicle_model
- Marca -> vehicle_brand
- Color -> vehicle_color
- Tipo Vehículo -> vehicle_type_label
- Subtipo Veh -> vehicle_subtype_label (vacío si pone "-- Seleccionar --")
- Ocupantes -> num_passengers
- Avería -> breakdown_description
- Avería Europ (o el código de avería de la compañía) -> breakdown_code
- Peso -> vehicle_weight; Altura -> vehicle_height; Longitud ->
  vehicle_length; Ejes -> vehicle_axes; Pma -> vehicle_pma; Tara ->
  vehicle_tare. Un 0 que solo es el valor vacío del campo se devuelve "".
- Recogida: Recoger en -> pickup_type; Provincia -> pickup_province;
  Localidad -> vehicle_locality; País -> pickup_country; Dirección ->
  pickup_location; C.P., si aparece -> pickup_cp
- Entrega: Entregar en -> delivery_type; Provincia -> delivery_province;
  Localidad -> delivery_locality; País -> delivery_country; Dirección ->
  delivery_address
- Motivo RIS -> ris_motive (vacío si pone "-- Seleccionar --")
- Kms. chófer -> driver_km; Kilómetros -> total_km_tirea
- Fallido -> is_failed ("si" o "no"); Facturable -> is_billable ("si" o
  "no")
- Comentarios -> insurer_comments (texto completo)
- Observaciones compañía -> company_observations
- Chófer (del lateral) -> tirea_driver (tal cual, p. ej. "023 - NOMBRE")
- Grúa (del lateral) -> tirea_machine (tal cual, con su matrícula)

Formatos:
- Fechas con hora: "AAAA-MM-DDTHH:MM" (las de la imagen vienen como
  DD/MM/AAAA HH:MM).
- Números: solo cifras, con punto decimal si lo hay, sin unidades.
"""


def extract_tirea_albaran(file_bytes, mime_type):
    """
    Extract the TIREA albarán fields from an image or PDF.

    ---

    Extrae los campos del albarán de TIREA de una imagen o PDF.
    Devuelve un diccionario con los valores ya convertidos (fechas con
    hora como `datetime`, números como `Decimal`/`int`, sí/no como
    booleanos); lo que no se lee queda fuera. Lanza la excepción de
    Gemini si la llamada falla, para que la vista avise al usuario.
    """
    client = get_gemini_client()
    response = _generate_content_with_retry(
        client,
        model=DEFAULT_MODEL,
        contents=[
            Part.from_bytes(data=file_bytes, mime_type=mime_type),
            _PROMPT,
        ],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=90_000),
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            thinking_config=ThinkingConfig(thinking_budget=0),
            temperature=0.0,
        ),
    )
    raw = json.loads(response.text.strip())
    logger.info(
        "# [TIREA] Extracción: %d campos con valor.",
        sum(1 for value in raw.values() if str(value).strip()),
    )
    return _convert(raw)


def _convert(raw):
    """
    Convert the raw strings of the model answer to Python values.

    ---

    Convierte las cadenas de la respuesta a valores de Python. Un valor
    que no se puede convertir se descarta (nunca se adivina).
    """
    data = {}
    for name in TEXT_FIELDS:
        value = str(raw.get(name, "")).strip()
        if value:
            data[name] = value
    for name in DATETIME_FIELDS:
        value = _to_datetime(raw.get(name))
        if value:
            data[name] = value
    for name in DECIMAL_FIELDS:
        value = _to_decimal(raw.get(name))
        if value is not None:
            data[name] = value
    for name in INTEGER_FIELDS:
        value = _to_decimal(raw.get(name))
        if value is not None and value == value.to_integral_value():
            data[name] = int(value)
    for name in BOOLEAN_FIELDS:
        value = str(raw.get(name, "")).strip().lower()
        if value in ("si", "sí", "yes", "true"):
            data[name] = True
        elif value in ("no", "false"):
            data[name] = False
    return data


def _to_datetime(value):
    """
    Parse "YYYY-MM-DDTHH:MM" (or "DD/MM/YYYY HH:MM"), or None.

    ---

    Interpreta la fecha con hora, o None.
    """
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_decimal(value):
    """
    Parse a number written with point or comma, or None.

    ---

    Interpreta un número con punto o coma decimal, o None.
    """
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
