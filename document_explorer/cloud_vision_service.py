# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/cloud_vision_service.py
"""
H31 (S102). Extracción de texto real de un documento, CENTRALIZADA en
un único sitio: texto embebido de PDF (gratis, instantáneo) primero,
Cloud Vision API después -- NUNCA Tesseract local (`pytesseract`).

Origen real: `personal_intake_service.py` ya había migrado esto para
el alta en H31/S100, tras el aviso de Miguel Ángel de que el OCR local
consume CPU compartida real de PythonAnywhere, con cuota diaria por
cuenta -- varias altas de 15-20 documentos el mismo día podían
agotarla y bloquear el resto del trabajo. Repetido en S102 (incidente
real: un Comando S tardó "lo más grande" ejecutando OCR local sobre un
único documento desde la ficha) y ampliado a un barrido: "hay que ver
también dónde tenemos más tesseract en todo el proyecto y cambiarlo" --
Miguel Ángel, verbatim, corrigiendo además el motor exacto: "el texto
lo tenemos que extraer con llamadas a... Cloud Vision, nunca jamás con
OCR de PythonAnywhere."

Centralizado aquí para que ningún llamador duplique la lógica de
Cloud Vision (mismo principio DRY que el resto de la plataforma) --
`personal_intake_service.py` y `date_verification_service.py` ya no
tienen su propia copia, ambos delegan aquí.
"""
from ai_services.gemini_client import ensure_gcp_credentials


def pdf_embedded_text(data: bytes) -> str:
    """
    Texto real ya incrustado en un PDF generado digitalmente (nunca
    un escaneo/foto) -- gratis, instantáneo, más fiable que cualquier
    OCR: es el texto real del documento, no una lectura visual.
    Devuelve cadena vacía (nunca lanza) si el PDF no trae texto real
    -- es un escaneo/foto -- para que el llamador caiga a Cloud
    Vision en ese caso. Acotado a las 2 primeras páginas, mismo
    límite que el resto del motor de fechas.
    """
    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
        parts = [page.get_text() for page in doc[:2]]
        return "\n".join(parts).strip()
    except Exception:
        return ""


def cloud_vision_image_text(image_bytes: bytes) -> str:
    """
    OCR real de una imagen ya rasterizada (PNG/JPEG en memoria) vía
    Cloud Vision `text_detection()` -- primitivo de bajo nivel, para
    cuando el llamador ya tiene los píxeles (una página de PDF
    renderizada a imagen, una foto/escaneo tal cual). Nunca None --
    cadena vacía si no hay texto reconocible.
    """
    from google.cloud import vision

    ensure_gcp_credentials()
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)
    if response.error.message:
        raise RuntimeError(response.error.message)
    return response.full_text_annotation.text or ""


def cloud_vision_text(data: bytes, filename: str) -> str:
    """
    OCR real vía Cloud Vision API -- nunca Tesseract local. Imagen
    (jpg/jpeg/png): `cloud_vision_image_text()` directo. PDF:
    `batch_annotate_files()` con `DOCUMENT_TEXT_DETECTION`, acotado a
    las 2 primeras páginas -- un DNI o la primera página de un
    contrato nunca necesitan más. Cloud Vision corre en la nube de
    Google (mismo proyecto/credenciales ya usadas para Vertex AI),
    responde en menos de un segundo por imagen/página, y no gasta ni
    un ciclo de CPU en el servidor.

    Devuelve cadena vacía (nunca None) si no hay texto reconocible, o
    si la extensión no está soportada -- el llamador decide el
    fallback.
    """
    from google.cloud import vision

    name_lower = (filename or "").lower()

    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return cloud_vision_image_text(data)

    if name_lower.endswith(".pdf"):
        ensure_gcp_credentials()
        client = vision.ImageAnnotatorClient()
        input_config = vision.InputConfig(
            content=data, mime_type="application/pdf",
        )
        feature = vision.Feature(
            type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION,
        )
        # Páginas 1-based en la API -- 1 y 2, mismo límite de 2
        # páginas que el resto del motor de fechas.
        request = vision.AnnotateFileRequest(
            input_config=input_config, features=[feature], pages=[1, 2],
        )
        response = client.batch_annotate_files(requests=[request])
        texts = []
        for file_response in response.responses:
            for page_response in file_response.responses:
                if page_response.error.message:
                    continue
                texts.append(page_response.full_text_annotation.text or "")
        return "\n".join(texts)

    return ""


def extract_text(filename: str, data: bytes) -> str:
    """
    Punto de entrada único: texto embebido de PDF -> Cloud Vision, en
    ese orden -- mismo criterio que ya usaba
    `personal_intake_service.extract_one_document`. Devuelve cadena
    vacía si ninguno de los dos encontró nada legible, o si la
    extensión no está soportada (nunca None -- a diferencia del
    contrato antiguo de `date_verification_service.extract_text()`,
    que devolvía `None` para extensiones sin extractor: aquí toda
    extensión que Cloud Vision no reconoce ya devuelve cadena vacía
    por su cuenta, mismo resultado práctico para el llamador).
    """
    text = ""
    if filename.lower().endswith(".pdf"):
        text = pdf_embedded_text(data)
    if not text:
        text = cloud_vision_text(data, filename)
    return text
