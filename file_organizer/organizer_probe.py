# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/file_organizer/organizer_probe.py
"""
Probe script for Hito 15 — folder classification using Gemini Vision.
Reads a .zip file containing a folder structure, analyzes each PDF
with Gemini Vision and generates a plain-text organization report.

---

Script de prueba para el Hito 15 -- clasificacion de carpeta con Gemini Vision.
Lee un archivo .zip con una estructura de carpetas, analiza cada PDF
con Gemini Vision y genera un informe de organizacion en texto plano.
"""

import os
import io
import json
import zipfile
import datetime
import pathlib
import traceback

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Authentication / Autenticacion
# ---------------------------------------------------------------------------
# Uses Vertex AI credentials from environment variables.
# Usa credenciales Vertex AI desde variables de entorno.

GCP_CREDENTIALS_PATH = os.environ.get("GCP_CREDENTIALS_PATH")
GOOGLE_CLOUD_PROJECT  = os.environ.get("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL                 = "gemini-2.5-flash"
ZIP_PATH              = os.environ.get("ORGANIZER_ZIP_PATH", "")
OUTPUT_PATH           = os.environ.get("ORGANIZER_OUTPUT_PATH", "/home/MiguelAeTxio/SWAP/informe_organizacion.txt")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCP_CREDENTIALS_PATH

client = genai.Client(
    vertexai=True,
    project=GOOGLE_CLOUD_PROJECT,
    location=GOOGLE_CLOUD_LOCATION,
)

# ---------------------------------------------------------------------------
# Classification prompt / Prompt de clasificacion
# ---------------------------------------------------------------------------
CLASSIFICATION_PROMPT = """
Eres un asistente de clasificacion documental para una empresa del sector
de gruas y maquinaria pesada llamada Grupo Alvarez.
Analiza el documento adjunto y determina:

1. CARPETA: La categoria documental mas adecuada donde deberia archivarse.
   Elige UNA de las siguientes categorias (o propone una nueva si ninguna encaja):
   - POLIZAS_SEGUROS
   - CONTRATOS_CLIENTES
   - DOCUMENTACION_PERSONAL
   - CERTIFICADOS
   - DOCUMENTACION_FISCAL
   - DOCUMENTACION_LABORAL
   - DOCUMENTACION_MAQUINARIA
   - PREVENCION_RIESGOS
   - CORRESPONDENCIA
   - OTROS

2. DESCRIPCION: Una descripcion breve del contenido (maximo 15 palabras).

Responde UNICAMENTE con un objeto JSON valido, sin texto adicional:
{"carpeta": "NOMBRE_CATEGORIA", "descripcion": "descripcion breve del documento"}
"""

# ---------------------------------------------------------------------------
# Core logic / Logica principal
# ---------------------------------------------------------------------------

def classify_pdf(pdf_bytes: bytes, filename: str) -> dict:
    """
    Sends a PDF to Gemini Vision and returns classification result.
    Returns dict with keys: carpeta, descripcion.

    ---

    Envia un PDF a Gemini Vision y devuelve el resultado de clasificacion.
    Retorna dict con claves: carpeta, descripcion.
    """
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(
                data=pdf_bytes,
                mime_type="application/pdf",
            ),
            CLASSIFICATION_PROMPT,
        ],
    )
    raw = response.text.strip()
    # Strip markdown fences if present / Eliminar fences markdown si existen
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def process_zip(zip_path: str) -> dict:
    """
    Iterates all PDF files inside the zip and classifies each one.
    Returns a results dict: {carpeta: [(filename, origin_path), ...]}
    Also tracks errors and unclassified files.

    ---

    Itera todos los PDFs dentro del zip y clasifica cada uno.
    Retorna un dict de resultados: {carpeta: [(filename, ruta_origen), ...]}
    Tambien registra errores y archivos sin clasificar.
    """
    results     = {}   # {carpeta: [(display_name, origin_path, descripcion)]}
    errors      = []   # [(origin_path, reason)]
    total       = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        entries = [e for e in zf.infolist() if not e.is_dir()]
        pdf_entries = [e for e in entries if e.filename.lower().endswith(".pdf")]
        total = len(pdf_entries)

        print(f"# [PROBE] Total PDFs encontrados: {total}")

        for idx, entry in enumerate(pdf_entries, 1):
            origin_path  = entry.filename
            display_name = pathlib.PurePosixPath(origin_path).name
            print(f"# [PROBE] ({idx}/{total}) Procesando: {origin_path}")

            try:
                pdf_bytes = zf.read(entry.filename)

                # Skip empty or suspiciously small files
                # Ignorar archivos vacios o sospechosamente pequenos
                if len(pdf_bytes) < 512:
                    errors.append((origin_path, "Archivo demasiado pequeno o vacio"))
                    continue

                classification = classify_pdf(pdf_bytes, display_name)
                carpeta    = classification.get("carpeta", "SIN_CLASIFICAR").strip().upper()
                descripcion = classification.get("descripcion", "").strip()

                if carpeta not in results:
                    results[carpeta] = []
                results[carpeta].append((display_name, origin_path, descripcion))

            except json.JSONDecodeError as exc:
                errors.append((origin_path, f"Respuesta JSON invalida: {exc}"))
            except Exception as exc:
                errors.append((origin_path, f"Error: {exc}"))
                traceback.print_exc()

    return results, errors, total


def generate_report(results: dict, errors: list, total: int, zip_path: str) -> str:
    """
    Builds the plain-text organization report.

    ---

    Construye el informe de organizacion en texto plano.
    """
    now          = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    folder_name  = pathlib.Path(zip_path).stem
    classified   = sum(len(v) for v in results.values())
    unclassified = total - classified - len(errors)

    lines = []
    sep   = "=" * 70

    lines.append(sep)
    lines.append(f"INFORME DE ORGANIZACION -- {folder_name.upper()}")
    lines.append(f"Fecha                  : {now}")
    lines.append(f"Total PDFs analizados  : {total}")
    lines.append(f"Clasificados           : {classified}")
    lines.append(f"No procesados (error)  : {len(errors)}")
    lines.append(sep)
    lines.append("")
    lines.append("ARBOL DE ORGANIZACION PROPUESTO")
    lines.append("-" * 40)
    lines.append("")

    for carpeta in sorted(results.keys()):
        lines.append(f"[{carpeta}]")
        for display_name, origin_path, descripcion in sorted(results[carpeta]):
            lines.append(f"  {display_name:<50}  ({descripcion})")
            lines.append(f"    origen: {origin_path}")
        lines.append("")

    if errors:
        lines.append(sep)
        lines.append("ARCHIVOS NO PROCESADOS")
        lines.append("-" * 40)
        for origin_path, reason in errors:
            lines.append(f"  {pathlib.PurePosixPath(origin_path).name:<50}")
            lines.append(f"    origen: {origin_path}")
            lines.append(f"    motivo: {reason}")
        lines.append("")

    lines.append(sep)
    lines.append("FIN DEL INFORME")
    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point / Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not ZIP_PATH or not pathlib.Path(ZIP_PATH).exists():
        print(f"# [ERROR] ZIP no encontrado: {ZIP_PATH!r}")
        print("# Uso: ORGANIZER_ZIP_PATH=/ruta/al/archivo.zip python3 organizer_probe.py")
        raise SystemExit(1)

    print(f"# [PROBE] Iniciando analisis de: {ZIP_PATH}")
    results, errors, total = process_zip(ZIP_PATH)

    report = generate_report(results, errors, total, ZIP_PATH)

    output_path = pathlib.Path(OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"# [PROBE] Informe generado en: {OUTPUT_PATH}")
    print(report)
