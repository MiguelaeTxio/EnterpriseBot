# C:\EnterpriseBot\h28_migration_agent\extract_local_real_samples.py
"""
H30 (S55). Extraccion via OCR de documentos REALES que ya viven en
carpetas locales del PC de Miguel Angel (OneDrive de GRUALDI SL),
nunca pasados por el pipeline de GCS/DocumentIndexEntry -- se leen
directamente del disco, sin tunel SSH, sin MySQL, sin GCS.

Mismo metodo de extraccion que el resto del proyecto (rasterizar cada
pagina + Tesseract, nunca texto embebido directo, por consistencia con
el resto de datasetN.jsonl), pero SIN reutilizar local_ocr_classify.py
completo -- ese modulo importa config.py, que a su vez exige la clave
de servicio de GCS y las credenciales de MySQL, innecesarias aqui.
Las tres funciones de extraccion se replican localmente, identicas.

Como localizar las carpetas: se le pasa un mapeo TIPO -> lista de
carpetas reales (ver TIPOS_A_CARPETAS abajo, ya rellenado en S55 con
las rutas reales encontradas en el listado de
C:\\Users\\Usuario\\OneDrive - GRUALDI SL). Recorre cada carpeta de
forma recursiva, extrae texto de cada .pdf/.jpg/.jpeg/.png/.docx
encontrado.

NUNCA escribe en ningun sitio del proyecto EnterpriseBot -- solo lee
del disco local y escribe un JSONL local.

USO:
    python extract_local_real_samples.py --output real_local_samples.jsonl
    python extract_local_real_samples.py --output real_local_samples.jsonl --max-per-type 30
"""
import argparse
import io
import json
import os
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# Mismo mecanismo ya resuelto en local_ocr_classify.py (S50): escribir
# en C:\Program Files\Tesseract-OCR\tessdata\ requiere administrador,
# asi que el paquete de idioma "spa" vive en la carpeta tessdata\ ya
# existente junto a los scripts de este directorio (compartida con
# local_ocr_classify.py, no se duplica). Este script es solo-Windows,
# sin necesidad del condicional os.name == "nt" que sí hace falta en
# local_ocr_classify.py (que tambien corre en las VMs Linux de OCR).
_TESSDATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tessdata",
)
os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR

# Este script es inherentemente solo-Windows (BASE ya asume rutas
# C:\Users\Usuario\OneDrive..., nunca corre en una VM Linux como
# local_ocr_classify.py) -- se fija la ruta de Tesseract directamente,
# sin la comedia de la linea comentada que sí hace falta en scripts
# multiplataforma. Confirmada instalacion real en esta ruta desde S50
# (ver SESSION_VARIABLES.md).
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

EXTENSIONES_VALIDAS = {".pdf", ".jpg", ".jpeg", ".png", ".docx"}

# Rutas reales encontradas en el listado de carpetas de S55 -- editar/
# ampliar esta tabla si aparecen mas carpetas reales de estos tipos.
# Cada ruta se recorre de forma RECURSIVA (incluye subcarpetas).
BASE = r"C:\Users\Usuario\OneDrive - GRUALDI SL"
TIPOS_A_CARPETAS = {
    "CERT_ACCESORIO_ELEVACION": [
        BASE + r"\PLANING COMPARTIDO\MATERIAL IZADO GRUAS Y CAMIONES\A-45\CERTIFICADOS ESLINGAS",
    ],
    "CERT_REVISION": [
        BASE + r"\DOCUMENTOS GRUPO ALVAREZ\DOC. MAQUINAS\REVISION DE EQUIPOS",
    ],
    "GASTOS_TARJETA_COMBUSTIBLE": [
        BASE + r"\Documentos compartidos\Combustible\solred",
        BASE + r"\Documentos compartidos\Combustible\Gasoil Huelva",
        BASE + r"\Documentos compartidos\Combustible\Gasoil Malaga",
        BASE + r"\Documentos compartidos\Combustible\Gasoil Profesional",
    ],
    "JUSTIFICANTE_TRANSFERENCIA": [
        BASE + r"\Documentos compartidos\CONTABILIDAD\Transferencias",
        BASE + r"\Documentos compartidos\TRANSFERENCIAS NOMINAS",
    ],
}


def ocr_pdf_to_text(data, max_pages=2, dpi=300):
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text_parts.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(text_parts)


def ocr_image_to_text(data):
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="spa")


def docx_to_text(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text(filename, data):
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return ocr_pdf_to_text(data)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return ocr_image_to_text(data)
    if name_lower.endswith(".docx"):
        return docx_to_text(data)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="real_local_samples.jsonl")
    parser.add_argument("--max-per-type", type=int, default=50)
    args = parser.parse_args()

    stats = {"ok": 0, "sin_texto": 0, "error": 0, "no_encontrado": 0}

    with open(args.output, "w", encoding="utf-8") as out:
        for tipo, carpetas in TIPOS_A_CARPETAS.items():
            escritos_tipo = 0
            for carpeta in carpetas:
                base_path = Path(carpeta)
                if not base_path.exists():
                    print("AVISO: carpeta no encontrada -- %s" % carpeta)
                    stats["no_encontrado"] += 1
                    continue

                for archivo in base_path.rglob("*"):
                    if escritos_tipo >= args.max_per_type:
                        break
                    if not archivo.is_file():
                        continue
                    if archivo.suffix.lower() not in EXTENSIONES_VALIDAS:
                        continue

                    try:
                        data = archivo.read_bytes()
                        texto = extract_text(archivo.name, data)
                    except Exception as error:
                        stats["error"] += 1
                        print("ERROR [%s] -- %s" % (archivo, error))
                        continue

                    if not texto or not texto.strip():
                        stats["sin_texto"] += 1
                        print("SIN TEXTO (OCR vacio) [%s]" % archivo)
                        continue

                    out.write(json.dumps({
                        "tipo": tipo,
                        "parent_path": str(archivo.parent),
                        "name": archivo.name,
                        "texto": texto[:4000],
                    }, ensure_ascii=False) + "\n")
                    out.flush()
                    stats["ok"] += 1
                    escritos_tipo += 1
                    print("OK [%s] %s -- %d caracteres" % (tipo, archivo.name, len(texto)))

            print("%s: %d ejemplos extraidos" % (tipo, escritos_tipo))

    print(
        "\nTERMINADO -- ok=%d sin_texto=%d error=%d carpetas_no_encontradas=%d "
        "-- guardado en %s"
        % (stats["ok"], stats["sin_texto"], stats["error"],
           stats["no_encontrado"], args.output)
    )


if __name__ == "__main__":
    main()
