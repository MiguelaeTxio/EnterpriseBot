# ~/EnterpriseBot/h28_migration_agent/test_easyocr_vs_tesseract_vm.py
"""
H30 (sesion tras S85). Version VM del benchmark Tesseract vs EasyOCR
-- descarga el documento real de GCS directamente (no requiere copiar
la imagen de depuracion del PC de Miguel Angel) y mide tiempos reales
en esta VM (e2-standard-8, CPU-only), para decidir si el rendimiento
hace viable EasyOCR como lector oficial del barrido masivo.

USO (documento real ya identificado, BURGOS FERNANDEZ):
    python3 test_easyocr_vs_tesseract_vm.py
"""
import io
import time

import fitz
import pytesseract
from google.cloud import storage
from PIL import Image

from config import get_service_account_key_path

BUCKET = "cgs_grupo_alvarez"
PARENT_PATH = (
    "DOC. PERSONAL/FORMACION TRABAJADORES/CURSO GRUAS ANAGRUAL/"
    "SOLICITUD DE CARNE/BURGOS FERNANDEZ"
)
NAME = "EXAMEN MEDICO GRUAS MOV AUT BURGOS FERNANDEZ 10-1-22.pdf"
BLOB_NAME = PARENT_PATH + "/" + NAME

print("Descargando %s de gs://%s/ ..." % (NAME, BUCKET))
gcs_client = storage.Client.from_service_account_json(
    get_service_account_key_path()
)
bucket = gcs_client.bucket(BUCKET)
data = bucket.blob(BLOB_NAME).download_as_bytes()
print("Descargado (%d bytes)." % len(data))

doc = fitz.open(stream=data, filetype="pdf")
page = doc.load_page(0)
pix = page.get_pixmap(dpi=400)
img = Image.open(io.BytesIO(pix.tobytes("png")))
doc.close()

print()
print("=" * 70)
print("TESSERACT (PSM automatico)")
print("=" * 70)
t0 = time.time()
tesseract_text = pytesseract.image_to_string(img, lang="spa")
print("Tiempo: %.1fs" % (time.time() - t0))
print(tesseract_text)

print()
print("=" * 70)
print("EASYOCR (es)")
print("=" * 70)
import easyocr

t0 = time.time()
reader = easyocr.Reader(["es"])
print("Tiempo de carga del modelo: %.1fs" % (time.time() - t0))

import numpy as np
t0 = time.time()
resultados = reader.readtext(np.array(img), detail=1)
print("Tiempo de lectura: %.1fs" % (time.time() - t0))
print()
for (bbox, texto, confianza) in resultados:
    print("[%.2f] %s" % (confianza, texto))

print()
print("=" * 70)
print("EASYOCR -- texto plano concatenado")
print("=" * 70)
print(" ".join(texto for (_, texto, _) in resultados))
