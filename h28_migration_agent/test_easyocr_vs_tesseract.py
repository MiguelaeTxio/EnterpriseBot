# C:\EnterpriseBot\h28_migration_agent\test_easyocr_vs_tesseract.py
"""
H30 (sesion tras S85). Prueba puntual, NO parte del pipeline oficial
todavia -- compara Tesseract (lector actual) contra EasyOCR (candidato
a sustituto) sobre la imagen real ya guardada por
extract_personal_dates_bulk.py (debug_entry_<id>_p0.png), el
documento real que confirmo el fallo (certificado CENTRO MEDICO
ALAMEDA, linea "expido el presente CERTIFICADO en... a 10 Enero 2022"
que Tesseract nunca lee, ni con PSM automatico ni con PSM 6).

USO:
    python test_easyocr_vs_tesseract.py debug_entry_24871_p0.png
"""
import os
import shutil
import sys
import time

import pytesseract
from PIL import Image

# Mismo patron que extract_personal_dates_bulk.py: el paquete de
# idioma espanol vive en tessdata\ junto al script, no en la ruta de
# instalacion real (Tesseract no puede escribir ahi sin permisos de
# administrador).
if os.name == "nt":
    _TESSDATA_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tessdata",
    )
    os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR

# Misma deteccion que extract_personal_dates_bulk.py -- Tesseract no
# esta en el PATH de esta maquina (instalado sin permisos de
# administrador).
if not shutil.which("tesseract"):
    _WINDOWS_TESSERACT_DEFAULT = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    if os.path.isfile(_WINDOWS_TESSERACT_DEFAULT):
        pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT_DEFAULT

if len(sys.argv) != 2:
    print("Uso: python test_easyocr_vs_tesseract.py <ruta_imagen.png>")
    sys.exit(1)

image_path = sys.argv[1]
img = Image.open(image_path)

print("=" * 70)
print("TESSERACT (PSM automatico, igual que el pipeline actual)")
print("=" * 70)
t0 = time.time()
tesseract_text = pytesseract.image_to_string(img, lang="spa")
print("Tiempo: %.1fs" % (time.time() - t0))
print(tesseract_text)

print()
print("=" * 70)
print("EASYOCR (es)")
print("=" * 70)
import easyocr  # import tardio: carga los modelos, mejor no pagar el coste si algo falla arriba

t0 = time.time()
reader = easyocr.Reader(["es"])
print("Tiempo de carga del modelo: %.1fs" % (time.time() - t0))

t0 = time.time()
resultados = reader.readtext(image_path, detail=1)
print("Tiempo de lectura: %.1fs" % (time.time() - t0))
print()
for (bbox, texto, confianza) in resultados:
    print("[%.2f] %s" % (confianza, texto))

print()
print("=" * 70)
print("EASYOCR -- texto plano concatenado (para comparar con classify_dates_in_text)")
print("=" * 70)
print(" ".join(texto for (_, texto, _) in resultados))
