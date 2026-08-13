# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/expiry_resolution_service.py
"""
H30 (S50). Resolucion de fecha de caducidad/emision EN TIEMPO REAL,
para enganchar directamente en el pipeline de clasificacion
(`apply_quarantine_classification`), no solo en barridos historicos
por lote.

Origen real, Miguel Angel, verbatim (S50): "cuando un archivo llegue,
conforme llegue y se clasifique, hay que sacar la fecha de caducidad
si la tiene [...] si no conseguimos sacarla de forma automatica, hay
que decirle al usuario [...] antes tenemos que agotar todos los
pasos. Heuristica primero, OCR despues, y llamada a Gemini despues."

Encadena, en este orden exacto, parando en el primer paso que
encuentre una fecha real:
1. `filename_date_service.extract_date_by_filename()` -- gratis, sin
   abrir el archivo.
2. `date_verification_service.extract_text()` +
   `classify_dates_in_text()` -- OCR local con Tesseract, gratis.
   Se SALTA por completo cuando `document_type.ocr_unreliable=True`
   (verificado con datos reales -- hoy solo ITV, tarjetas manuscritas
   con fondo de seguridad que domina la lectura de Tesseract, mismo
   criterio ya usado en `verify_typed_date`) -- no tiene sentido
   gastar tiempo en un OCR que ya sabemos que va a fallar.
3. `date_verification_service.extract_expiry_via_gemini()` -- ultimo
   recurso, con coste real, solo si los dos anteriores no encontraron
   nada.

Si NINGUNO de los tres pasos encuentra fecha, devuelve
`(None, None)` -- nunca inventa una fecha, nunca bloquea la
clasificacion/reubicacion del archivo. El documento queda con
`expiry_date`/`issue_date` en blanco, marcado implicitamente como
"necesita atencion humana" por la propia ausencia del dato (ver
`document_explorer.views_documentation_h30`, columna de alerta) --
no hace falta ningun campo booleano nuevo, la ausencia de fecha en un
tipo `tracks_expiry=True` ya es la señal completa.
"""
from document_explorer.date_verification_service import (
    classify_dates_in_text, extract_expiry_via_gemini, extract_text,
)
from document_explorer.filename_date_service import extract_date_by_filename


def resolve_expiry_date(document_type, filename, data):
    """
    Devuelve (field, date) donde field es "expiry" o "issue", o
    (None, None) si ninguno de los tres pasos encontro nada legible.
    Nunca se llama si `document_type.tracks_expiry` es False -- eso
    lo decide quien llama, este servicio asume que ya hace falta
    fecha.
    """
    by_name = extract_date_by_filename(document_type.code, filename)
    if by_name:
        return by_name

    if not document_type.ocr_unreliable:
        text = extract_text(filename, data)
        if text is not None:
            expiry, issue, other = classify_dates_in_text(text)
            if expiry:
                return "expiry", expiry
            if issue:
                return "issue", issue
            if len(other) == 1:
                # Fecha encontrada, sin contexto claro de caducidad ni
                # emision -- mismo criterio ya usado en
                # verify_typed_date(): una unica fecha ambigua se
                # trata como la relevante, mejor que ninguna.
                return "issue", other[0]

    gemini_expiry = extract_expiry_via_gemini(data, filename)
    if gemini_expiry:
        return "expiry", gemini_expiry

    return None, None
