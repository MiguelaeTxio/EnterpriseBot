# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/payslip_cost.py
"""
H37 (S143). Cost per hour of an operator, read from a payslip.

---

Coste por hora de un operario a partir de una nómina (S143). Miguel
Ángel: "que tengamos la posibilidad de subir la nómina para calcular el
coste tal y como hemos hecho con la mía". Mismo cálculo que en S142
(`DEFAULT_OPERATOR_COST_HOUR`):

    coste empresa al mes = total devengado
                           + prorrata de pagas extra (si no va ya en
                             el devengado)
                           + Seguridad Social a cargo de la empresa
    coste por hora = coste empresa al mes × 12 / horas trabajadas al año

Las horas trabajadas al año (1.800 por defecto) ya descuentan
vacaciones y festivos, que se pagan sin trabajar.

La nómina se lee con Gemini (primero su texto, como TIREA) y no se
guarda: ni el archivo ni sus importes. Solo queda el coste por hora si
quien la sube lo guarda en Medias de coste. Nada de la nómina va a los
registros (logs).
"""
import json
import logging
from decimal import ROUND_HALF_UP, Decimal

from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    Part,
    ThinkingConfig,
)

from ai_services.document_vision_service import _generate_content_with_retry
from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from budgets.tirea_extraction import (
    MIN_TEXT_CHARS,
    TEXT_TIMEOUT_MS,
    _document_text,
    _to_decimal,
)

logger = logging.getLogger(__name__)

ACCEPTED_TYPES = (
    "application/pdf", "image/jpeg", "image/png", "image/webp",
)
MAX_BYTES = 15 * 1024 * 1024
FILE_TIMEOUT_MS = 90_000
MONTHS_PER_YEAR = 12
AMOUNT_FIELDS = ("gross_pay", "extra_prorata", "employer_ss")

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_payslip": {"type": "string"},
        "period": {"type": "string"},
        "gross_pay": {"type": "string"},
        "prorata_in_gross": {"type": "string"},
        "extra_prorata": {"type": "string"},
        "employer_ss": {"type": "string"},
    },
    "required": [
        "is_payslip", "period", "gross_pay", "prorata_in_gross",
        "extra_prorata", "employer_ss",
    ],
}

_TEXT_INTRO = (
    "El documento llega ya leído como TEXTO (texto del PDF o OCR de la "
    "imagen), no como imagen. Las tablas pueden salir desordenadas; "
    "cada etiqueta suele ir seguida de su importe.\n\n---\n"
)

_PROMPT = """El documento debería ser una nómina española (recibo de
salarios) de un trabajador. Devuelve SOLO lo que se lee, sin inventar ni
calcular nada; lo que no aparezca, cadena vacía "". No devuelvas nombres,
DNI, NAF, IBAN ni ningún otro dato personal.

- is_payslip: "si" si es una nómina; "no" si es otra cosa (y deja el
  resto vacío).
- period: periodo de liquidación tal cual (p. ej. "01/10/2026 a
  31/10/2026").
- gross_pay: TOTAL DEVENGADO del mes (la suma de los devengos, antes de
  las deducciones del trabajador).
- prorata_in_gross: "si" si entre los devengos hay una línea de prorrata
  de pagas extra (p. ej. "Prorrata pagas extras", "P.P. extras"); "no"
  si no la hay.
- extra_prorata: importe mensual de la prorrata de pagas extra que
  aparece en la determinación de las bases de cotización (p. ej.
  "Prorrata pagas extras", "P.P.P.E."), o el de la línea de devengos si
  solo está ahí.
- employer_ss: total de la aportación de la EMPRESA a la Seguridad
  Social (p. ej. "Total aportación empresa", "Aportación empresarial",
  "Coste Seguridad Social empresa"): la suma de contingencias comunes,
  desempleo, formación profesional, FOGASA, accidentes de trabajo y MEI
  a cargo de la empresa. Nunca la del trabajador.

Importes: solo cifras, con punto decimal, sin euros ni separador de
miles.
"""


class PayslipError(Exception):
    """
    The payslip could not be read.

    ---

    No se pudo leer la nómina; el mensaje es para el usuario.
    """


def _money(value):
    """
    Decimal rounded to cents.

    ---

    Decimal redondeado a céntimos.
    """
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def read_payslip(file_bytes, mime_type):
    """
    Read the amounts of a payslip that make up its company cost.

    ---

    Lee de la nómina los importes del coste empresa: total devengado,
    si la prorrata de pagas extra va en él, la prorrata y la Seguridad
    Social a cargo de la empresa. Primero el texto (PDF u OCR) y, si no
    basta o falla, el archivo. Lanza PayslipError con el motivo.
    """
    client = get_gemini_client()

    def ask(document, timeout):
        return _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[document, _PROMPT],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=timeout),
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                thinking_config=ThinkingConfig(thinking_level="low"),
                temperature=0.0,
            ),
        )

    text = _document_text(file_bytes, mime_type)
    response = None
    if len(text.strip()) >= MIN_TEXT_CHARS:
        try:
            response = ask(_TEXT_INTRO + text, TEXT_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001 -- se lee el archivo
            logger.warning(
                "# [NOMINA] Lectura del texto fallida (%s); se lee el "
                "archivo.", type(exc).__name__,
            )
    if response is None:
        try:
            response = ask(
                Part.from_bytes(data=file_bytes, mime_type=mime_type),
                FILE_TIMEOUT_MS,
            )
        except Exception as exc:  # noqa: BLE001 -- se avisa al usuario
            logger.warning(
                "# [NOMINA] Lectura fallida: %s", type(exc).__name__,
            )
            raise PayslipError(
                "No se pudo leer la nómina; vuelve a intentarlo.",
            ) from exc
    try:
        raw = json.loads(response.text.strip())
    except (ValueError, AttributeError) as exc:
        raise PayslipError(
            "La lectura de la nómina no se entendió; vuelve a intentarlo.",
        ) from exc
    if str(raw.get("is_payslip", "")).strip().lower() == "no":
        raise PayslipError("El documento no parece una nómina.")
    data = {
        "period": str(raw.get("period") or "").strip(),
        "prorata_in_gross": str(
            raw.get("prorata_in_gross", ""),
        ).strip().lower() in ("si", "sí", "yes", "true"),
    }
    for name in AMOUNT_FIELDS:
        data[name] = _to_decimal(raw.get(name))
    if data["gross_pay"] is None or data["employer_ss"] is None:
        raise PayslipError(
            "En la nómina no se lee el total devengado o la aportación de "
            "la empresa a la Seguridad Social.",
        )
    logger.info("# [NOMINA] Nómina leída (sin guardar nada).")
    return data


def hourly_cost(data, annual_hours):
    """
    Company cost of the payslip per month, per year and per hour.

    ---

    Coste empresa de la nómina al mes, al año y por hora trabajada, con
    el desglose para enseñarlo (plantillas tontas). La prorrata de
    pagas extra solo se suma si no va ya en el devengado.
    """
    prorata = data.get("extra_prorata") or Decimal("0")
    added_prorata = Decimal("0") if data["prorata_in_gross"] else prorata
    monthly = data["gross_pay"] + added_prorata + data["employer_ss"]
    annual = monthly * MONTHS_PER_YEAR
    return {
        "period": data["period"],
        "gross_pay": _money(data["gross_pay"]),
        "prorata_in_gross": data["prorata_in_gross"],
        "extra_prorata": _money(prorata),
        "added_prorata": _money(added_prorata),
        "employer_ss": _money(data["employer_ss"]),
        "monthly_cost": _money(monthly),
        "annual_cost": _money(annual),
        "annual_hours": annual_hours,
        "cost_per_hour": _money(annual / Decimal(annual_hours)),
    }
