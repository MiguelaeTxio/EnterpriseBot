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


def pdf_embedded_text(data: bytes, page_range: tuple[int, int] = (0, 2)) -> str:
    """
    Texto real ya incrustado en un PDF generado digitalmente (nunca
    un escaneo/foto) -- gratis, instantáneo, más fiable que cualquier
    OCR: es el texto real del documento, no una lectura visual.
    Devuelve cadena vacía (nunca lanza) si el PDF no trae texto real
    -- es un escaneo/foto -- para que el llamador caiga a Cloud
    Vision en ese caso.

    `page_range` es (inicio, fin) 0-based, fin exclusivo -- por
    defecto las 2 primeras páginas (mismo límite de siempre). H31
    (S111): cuando ninguna fecha se resuelve en ese rango, el
    llamador reintenta con `(2, 4)` -- caso real confirmado (Arrabalí
    Guzmán y otros 14 de 16): la cláusula CUARTA con la fecha de
    alta cae en la página 3 en el impreso de "fijo discontinuo" del
    SEPE, que el límite de 2 páginas nunca llegaba a leer.
    """
    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
        start, end = page_range
        parts = [page.get_text() for page in doc[start:end]]
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


def cloud_vision_text(
    data: bytes, filename: str, page_range: tuple[int, int] = (1, 2),
) -> str:
    """
    OCR real vía Cloud Vision API -- nunca Tesseract local. Imagen
    (jpg/jpeg/png): `cloud_vision_image_text()` directo (ignora
    `page_range`, no aplica a una imagen suelta). PDF:
    `batch_annotate_files()` con `DOCUMENT_TEXT_DETECTION`, acotado
    por defecto a las 2 primeras páginas -- un DNI o la primera
    página de un contrato nunca necesitan más. Cloud Vision corre en
    la nube de Google (mismo proyecto/credenciales ya usadas para
    Vertex AI), responde en menos de un segundo por imagen/página, y
    no gasta ni un ciclo de CPU en el servidor.

    `page_range` es (inicio, fin) 1-based inclusive, tal cual los
    numera la API de Cloud Vision -- por defecto (1, 2). H31 (S111):
    el llamador reintenta con (3, 4) cuando ninguna fecha se resuelve
    en las 2 primeras -- ver `pdf_embedded_text()` para el caso real
    que motivó esto.

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
        start, end = page_range
        request = vision.AnnotateFileRequest(
            input_config=input_config, features=[feature],
            pages=list(range(start, end + 1)),
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
    Acotado a las 2 primeras páginas -- para leer más, usar
    `extract_text_for_dates()`.
    """
    text = ""
    if filename.lower().endswith(".pdf"):
        text = pdf_embedded_text(data)
    if not text:
        text = cloud_vision_text(data, filename)
    return text


def extract_text_for_dates(filename: str, data: bytes):
    """
    H31 (S111). Igual que `extract_text()` seguido de
    `date_verification_service.classify_dates_in_text()`, pero si
    ninguna fecha se resuelve (ni `expiry` ni `issue`) en las 2
    primeras páginas, reintenta automáticamente con las páginas 3-4
    antes de rendirse -- Miguel Ángel, verbatim: "cuando no se lea
    ninguna fecha se leen dos páginas más".

    Origen real: al revisar a mano 16 personas sin ninguna fecha
    resoluble, 15 de 16 SÍ tenían una fecha real, legible y sin
    ambigüedad -- pero en la página 3 (impreso de "fijo discontinuo"
    del SEPE: la cláusula CUARTA con la fecha de alta cae ahí, no en
    las 2 primeras). El límite de 2 páginas nunca llegaba a leerla.

    Devuelve (text, expiry, issue, other, paginas_leidas) --
    `paginas_leidas` es 2 o 4, para que el llamador sepa si tuvo que
    ampliar y pueda registrarlo si quiere. `text` es el texto
    combinado de todas las páginas realmente leídas (para cachear en
    `ocr_text` tal cual, sin perder lo ya obtenido en el primer
    intento).
    """
    from document_explorer.date_verification_service import (
        classify_dates_in_text,
    )

    text = extract_text(filename, data)
    expiry, issue, other = classify_dates_in_text(text) if text else (
        None, None, [],
    )
    if expiry or issue:
        return text, expiry, issue, other, 2

    if filename.lower().endswith(".pdf"):
        extra = pdf_embedded_text(data, page_range=(2, 4))
        if not extra:
            extra = cloud_vision_text(data, filename, page_range=(3, 4))
        if extra:
            text_ampliado = (text + "\n" + extra).strip() if text else extra
            expiry2, issue2, other2 = classify_dates_in_text(text_ampliado)
            if expiry2 or issue2 or other2:
                return text_ampliado, expiry2, issue2, other2, 4

    return text, expiry, issue, other, 2
