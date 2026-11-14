# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/albaran_full.py
"""
Full digital copy of a work delivery note (every field, not only times).

---

S153 (Miguel Ángel: "es necesario extraer los datos", "una copia
digital exacta en base de datos"). La lectura de S149
(albaran_check.read_batch) solo saca lo que hace falta para cotejar los
fichajes (número, fecha, operario, máquina, horas). Aquí se saca TODO
lo que trae cada albarán, sin perder nada:

- full_text: la transcripción literal, campo a campo y en el orden del
  papel.
- full_data: los datos ordenados -- campos fijos que suelen traer
  (cliente, obra, expediente, vehículo, km, horas, servicio...), todos
  los demás pares etiqueta/valor que haya, las tablas (conceptos,
  materiales, horas...) fila a fila, las firmas y lo que no se lee bien.

Un archivo puede traer varios albaranes: Gemini los devuelve en el
mismo orden que la lectura de S149 (position 1, 2, 3...).
"""
import json
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

_PROMPT = """
Eres un transcriptor de albaranes de trabajo (partes de producción) de
una empresa de grúas, plataformas y asistencia en carretera. El
documento es una foto o un escaneo y puede traer uno o varios albaranes
(uno por página o varios en una página). Devuélvelos en el orden en que
aparecen.

De cada albarán quiero una COPIA DIGITAL EXACTA, sin resumir ni
interpretar:
- "transcripcion": todo el texto del albarán, literal, en el orden del
  papel, una línea por campo o renglón ("Etiqueta: valor"). Incluye los
  textos impresos, lo escrito a mano y los sellos. Lo que no se lea,
  escríbelo como [ilegible].
- Los campos fijos si aparecen (vacío si no): número, fecha, empresa
  emisora, cliente, CIF/NIF del cliente, dirección u obra, población,
  expediente o referencia, operario, ayudantes, vehículo o máquina,
  matrícula, km de salida y de llegada, horas (salida de base, llegada
  a obra, inicio y fin de trabajo, salida de obra, llegada a base),
  servicio o trabajo realizado, observaciones.
- "otros_campos": TODOS los demás pares etiqueta/valor del albarán que
  no estén en los campos fijos (casillas marcadas, tarifas, toneladas,
  metros, peajes, dietas, lo que haya).
- "tablas": cada tabla (conceptos, materiales, horas, etc.) con su
  título, sus columnas y sus filas tal cual.
- "firmas": quién firma (cliente, operario, encargado...), con nombre y
  DNI si constan y si la firma está.
- "ilegible": lo que no se ha podido leer bien.
Copia los valores tal como están escritos (fechas, horas, importes y
números sin cambiar su formato).
"""

_TEXT = {"type": "string"}
_SCHEMA = {
    "type": "object",
    "properties": {
        "albaranes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "transcripcion": _TEXT,
                    "numero": _TEXT,
                    "fecha": _TEXT,
                    "empresa_emisora": _TEXT,
                    "cliente": _TEXT,
                    "cif_cliente": _TEXT,
                    "direccion_obra": _TEXT,
                    "poblacion": _TEXT,
                    "expediente": _TEXT,
                    "operario": _TEXT,
                    "ayudantes": _TEXT,
                    "vehiculo_maquina": _TEXT,
                    "matricula": _TEXT,
                    "km_salida": _TEXT,
                    "km_llegada": _TEXT,
                    "hora_salida_base": _TEXT,
                    "hora_llegada_obra": _TEXT,
                    "hora_inicio_trabajo": _TEXT,
                    "hora_fin_trabajo": _TEXT,
                    "hora_salida_obra": _TEXT,
                    "hora_llegada_base": _TEXT,
                    "servicio": _TEXT,
                    "observaciones": _TEXT,
                    "otros_campos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"etiqueta": _TEXT, "valor": _TEXT},
                            "required": ["etiqueta", "valor"],
                        },
                    },
                    "tablas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "titulo": _TEXT,
                                "columnas": {"type": "array", "items": _TEXT},
                                "filas": {
                                    "type": "array",
                                    "items": {"type": "array",
                                              "items": _TEXT},
                                },
                            },
                            "required": ["columnas", "filas"],
                        },
                    },
                    "firmas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quien": _TEXT, "nombre": _TEXT,
                                "dni": _TEXT, "firmado": {"type": "boolean"},
                            },
                            "required": ["quien", "firmado"],
                        },
                    },
                    "ilegible": _TEXT,
                },
                "required": ["transcripcion", "numero", "fecha"],
            },
        },
    },
    "required": ["albaranes"],
}


def transcribe(data, mime):
    """
    Every field of every albarán in a file, in paper order.
    ---
    La copia completa de cada albarán del archivo (lista, en el orden
    del papel).
    """
    from google.genai.types import GenerateContentConfig, HttpOptions, Part

    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
    from document_explorer.classification_service import (
        _generate_content_with_retry,
    )

    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=mime), _PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=300_000),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip()).get("albaranes") or []


def _match(sheets, items):
    """
    Pair each sheet with its full copy: same number first, then order.
    ---
    Empareja cada albarán leído con su copia completa: por número si
    coincide y, si no, por el orden en el archivo.
    """
    pairs, free = [], list(items)
    for sheet in sheets:
        same = next((item for item in free if sheet.number and (
            (item.get("numero") or "").strip() == sheet.number)), None)
        if same is None and free:
            same = free[0]
        if same is not None:
            free.remove(same)
        pairs.append((sheet, same))
    return pairs


def store_full(sheets, data, mime):
    """
    Transcribe a file and keep the full copy in its sheets.
    ---
    Transcribe el archivo y guarda la copia completa en cada albarán
    que salió de él (`sheets`, ordenados por position). Devuelve
    cuántos se han guardado.
    """
    items = transcribe(data, mime)
    stamp = timezone.now()
    saved = 0
    for sheet, item in _match(sheets, items):
        if item is None:
            continue
        sheet.full_text = item.get("transcripcion") or ""
        sheet.full_data = {k: v for k, v in item.items()
                           if k != "transcripcion"}
        sheet.full_read_at = stamp
        sheet.save(update_fields=["full_text", "full_data",
                                  "full_read_at"])
        saved += 1
    return saved
