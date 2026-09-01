# C:\EnterpriseBot\h28_migration_agent\extract_epis_deliveries_vm.py
"""
H30, sesion de continuidad tras S79. Extractor real de entregas de
EPIs para los 767 documentos vivos tipados `EPIS` que se quedaron sin
procesar por `extract_epis_deliveries.py` (aquel comando exigia
`.doc`/`.docx` ya archivados dentro de `ENTREGA EPIS` -- ver hallazgo
real de sesion: la Fase A excluye EPIS de su recorrido normal por
diseno de S48, asi que nada saca estos documentos de `_CUARENTENA`, y
el 90% real (verificado con muestra de 40) son `.pdf` sin capa de
texto -- escaneo puro, nunca los veia ese comando).

Volumen real (752 PDF + 14 docx + 1 doc = 767) obliga a VM segun la
tabla de volumen de OCR de `com-standards` -- nunca en la consola de
PythonAnywhere. Decision explicita de Miguel Angel: UNA sola VM con
hilos (`--threads`), no varias VMs shardeadas como con la maquinaria
-- el volumen no lo justifica.

Mismo patron standalone que `extract_personal_dates_bulk.py`: tunel
SSH por CLAVE ya registrada (nunca contrasena, arreglado en sesion
hoy mismo) + pymysql directo + GCS via service account, sin Django
(la VM no lo tiene). Cada hilo abre su propia conexion MySQL sobre el
mismo puerto local del tunel -- sin bloqueo compartido.

Tres vias de lectura, en este orden segun lo que traiga el documento:
1. PDF con capa de texto real (verificado con `page.get_text()` no
   vacio) -- lee tabla nativa con `pymupdf` (`find_tables()`), misma
   fiabilidad que un .docx.
2. PDF sin texto (escaneo puro, ~90% real de la muestra) -- OCR con
   Tesseract sobre la imagen renderizada de cada pagina, y deteccion
   de items marcados sobre TEXTO PLANO (sin estructura de celda,
   `_parse_marked_labels_flat`) -- menos fiable que la version con
   tabla, se marca `extraction_method=OCR` explicitamente para poder
   auditar despues cuales entradas vienen de aqui.
3. `.doc`/`.docx` -- mismo camino que el comando Django original
   (conversion via `soffice` para `.doc`, lectura de tabla nativa).

Persona: SIEMPRE por DNI real extraido del contenido, NUNCA por
`domain_object_id` ya resuelto ni por carpeta de origen -- mismo
criterio de `extract_epis_deliveries.py`, sin relajarlo aunque el
documento ya este archivado en la carpeta correcta de la persona.
Documentos cuyo DNI no resuelve se reportan, nunca se inventan.

Deteccion de "esto no es una entrega real" (hallazgo real de sesion,
9 muestras reales de Miguel Angel): certificados de FORMACION ("USO
DE EPIS" de Fundacion Tripartita), entregas de informacion PRL, y
facturas/albaranes de proveedor (EpiCenter) comparten por error el
tipo `EPIS` de origen. Nunca se procesan como `EpiDelivery` -- se
reportan aparte con el codigo sugerido de reclasificacion, la
reclasificacion real se hace a mano despues de revisar el listado.

DRY-RUN POR DEFECTO. --apply escribe de verdad. --limit acota una
pasada de muestreo (obligatorio antes de un --apply sin limite,
mismo principio de verificacion previa de todo el proyecto).
"""
import argparse
import datetime
import getpass
import io
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from queue import Queue

import pymysql

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import paramiko
if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

import pytesseract
import sshtunnel
from google.cloud import storage
from PIL import Image

from config import get_service_account_key_path

PYTHONANYWHERE_USERNAME = "MiguelAeTxio"
SSH_HOSTNAME = "ssh.pythonanywhere.com"
MYSQL_HOSTNAME = "MiguelAeTxio.mysql.pythonanywhere-services.com"
MYSQL_DB_NAME = "MiguelAeTxio$enterprisebot"
MYSQL_USERNAME = "MiguelAeTxio"
BUCKET = "cgs_grupo_alvarez"

_SOFFICE_TIMEOUT_SECONDS = 60

_DNI_LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
# S82: acepta tambien NIE (letra X/Y/Z inicial) -- bug real
# confirmado con un caso vivo (Petru Iordachi, NIE X6854905P) que
# nunca se resolvia porque el regex solo aceptaba digitos.
_DNI_DIGITS_RE = re.compile(
    r"D\.?\s*N\.?\s*I\.?\s*[:.]?\s*([XYZxyz]?[0-9]{1,2}[.\s]?[0-9]{3}[.\s]?[0-9]{3})"
)
_NAME_ENTREGA_RE = re.compile(
    r"[Ee]ntrega\s+a\s+D\.?[ºa]?\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s.]+?)"
    r"\s+con\s+D\.?\s*N\.?\s*I"
)
_NAME_TABLE_RE = re.compile(
    r"D\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)\s+D\.?\s*N\.?\s*I\.?\s*[:.]?"
)
_DATE_LIKE_RE = re.compile(r"^[0-9./\-]+$")
_MARK_RE = re.compile(r"^[Xx✓]{1,2}$")
_FILENAME_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2,4})")
_CONTENT_DATE_RE = re.compile(
    r"(?:A\s+fecha|FECHA)\s*[:.]?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
    re.IGNORECASE,
)

# Identica a extract_epis_deliveries.py -- nunca se reescribe sin
# motivo, mismo catalogo confirmado por Miguel Angel en S72/S73.
ITEM_LABEL_MAP = [
    ("MASCARILLA FILTRO ANTIPARTICULAS", "MASCARILLA_FILTRO_ANTIPARTICULAS"),
    ("MASCARILLA CON FILTRO ANTI PARTICULAS", "MASCARILLA_FILTRO_ANTIPARTICULAS"),
    ("MASCARILLA BUCONASAL", "MASCARILLA_BUCONASAL"),
    ("MASCARA MEDIA", "MASCARA_MEDIA_RESPIRADOR"),
    ("MASCARA SOLDAR", "MASCARA_SOLDAR"),
    ("MASCARA DE SOLDAR", "MASCARA_SOLDAR"),
    ("CARETA DE PROTECCION", "CARETA_PROTECCION"),
    ("FILTROS VAPORES", "FILTRO_VAPORES_GASES_ACIDOS"),
    ("RETENEDOR DE FILTROS", "RETENEDOR_FILTROS"),
    ("BOLSA PORTARESPIRADOR", "BOLSA_PORTARRESPIRADOR"),
    ("BOLSA PORTARRESPIRADOR", "BOLSA_PORTARRESPIRADOR"),
    ("PREFILTRO P3", "PREFILTRO_P3"),
    ("FILTRO PARTICULAS", "PREFILTRO_P3"),
    ("GUANTES DE ACCION MECANICA Y QUIMICA", "GUANTES_MECANICA_QUIMICA"),
    ("GUANTES DE ACCION QUIMICA", "GUANTES_QUIMICA"),
    ("GUANTES ACCION QUIMICA", "GUANTES_QUIMICA"),
    ("GUANTES DE ACCION MECANICA", "GUANTES_MECANICA"),
    ("GUANTES ACCION MECANICA", "GUANTES_MECANICA"),
    ("GUANTES DE PROTECCION", "GUANTES_PROTECCION"),
    ("TRAJE DE AGUA", "TRAJE_AGUA"),
    ("POLAR", "POLAR"),
    ("BUZO DE TRABAJO", "BUZO_ALTA_VISIBILIDAD"),
    ("PANTALON DE TRABAJO", "PANTALON_ALTA_VISIBILIDAD"),
    ("PANTALON", "PANTALON_ALTA_VISIBILIDAD"),
    ("POLO MANGA CORTA", "POLO_ALTA_VISIBILIDAD"),
    ("POLO", "POLO_ALTA_VISIBILIDAD"),
    ("MONO DE TRABAJO", "MONO_ALTA_VISIBILIDAD"),
    ("CHAQUETA", "CHAQUETA_ALTA_VISIBILIDAD"),
    ("CINTURON DE SEG", "CINTURON_DOS_AMARRES"),
    ("ELEMENTO DE AMARRE", "ELEMENTO_AMARRE"),
    ("ARNE", "ARNES_SEGURIDAD"),
    ("ROPA IGNIFUGA", "ROPA_IGNIFUGA_ARCO"),
    ("ROPA INGNIFUGA", "ROPA_IGNIFUGA_ARCO"),
    ("ROPA DE TRABAJO", "ROPA_TRABAJO"),
    ("CASCO", "CASCO_SEGURIDAD"),
    ("CHALECO REFLECTANTE", "CHALECO_REFLECTANTE"),
    ("ZAPATOS DE SEGURIDAD", "ZAPATOS_SEGURIDAD"),
    ("PROTECCION AUDITIVA", "PROTECCION_AUDITIVA"),
    ("ROPA DE SENALIZACION", "BUZO_ALTA_VISIBILIDAD"),
    ("GAFAS", "GAFAS_ANTIPARTICULAS"),
]
ITEM_LABEL_MAP.append(("GUANTES", "GUANTES_PROTECCION"))

# Hallazgo real de sesion (9 muestras reales de Miguel Angel, 31/08):
# estos documentos comparten por error el tipo EPIS pero NO son una
# entrega de equipos -- nunca se procesan como EpiDelivery.
_NON_DELIVERY_SIGNALS = [
    ("CERTIFICADO DE PARTICIPACION", "FORMACION"),
    ("ACCION FORMATIVA", "FORMACION"),
    ("ENTREGA DE INFORMACION EN PREVENCION", "ENTREGA_INFORMACION"),
    ("AUTORIZACION DE MANEJO DE MAQUINARIA", "AUTORIZACION_USO_MAQUINARIA"),
    ("NUMERO DE ALBARAN", "OTROS_DOCUMENTOS"),
    ("ABONO IMPARTICION", "OTROS_DOCUMENTOS"),
    ("BASE IMPONIBLE", "OTROS_DOCUMENTOS"),
]


def _normalize(label):
    label = unicodedata.normalize("NFKD", (label or "").upper())
    label = "".join(c for c in label if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", label).strip()


def _map_label(label):
    norm = _normalize(label)
    for phrase, code in ITEM_LABEL_MAP:
        if phrase in norm:
            return code
    return None


def _parse_plain_list_items(text):
    """Fallback (S82): plantilla real sin ninguna marca de casilla --
    confirmado con dos casos reales (Zafra Balbuena, Ruiz Leiva) --
    bajo el titulo del apartado EPIS lista los items entregados con
    guiones, sin X ni checkbox alguno; el propio texto del documento
    ("La Empresa ha hecho entrega... de los Equipos de Proteccion
    Individual especificados a continuacion") confirma que TODO lo
    listado ahi se considera entregado, sin necesidad de marca
    individual. Solo se usa cuando el camino de marcas (tabla nativa u
    OCR espacial) no encontro ningun item, para no interferir nunca
    con el formato de tabla ya funcionando."""
    match = re.search(
        r"EQUIPO.{0,80}PROTECCI[OÓ]N INDIVIDUAL.{0,400}?ENTREGAD[OA]S?"
        r".{0,60}TRABAJADOR",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return set()
    start = match.end()
    next_section = re.search(r"\n\s*\d+[oº°]?[-.]", text[start:])
    end = start + next_section.start() if next_section else len(text)
    block = text[start:end]
    codes = set()
    # El guion real a veces lo lee Tesseract como comilla tipografica
    # (confirmado real: "\u201cCASCOS" en vez de "-CASCOS") -- se
    # acepta como separador de item igual que el guion.
    for fragment in re.split(r"[-\u2010-\u2015\u2018-\u201F]", block):
        fragment = fragment.strip()
        if not fragment:
            continue
        code = _map_label(fragment)
        if code:
            codes.add(code)
    return codes


def _detect_non_delivery(text):
    norm = _normalize(text)
    for signal, suggested_code in _NON_DELIVERY_SIGNALS:
        if signal in norm:
            return suggested_code
    return None


def _convert_doc_to_docx(content_bytes):
    with tempfile.TemporaryDirectory() as workdir:
        input_path = Path(workdir) / "input.doc"
        profile_dir = Path(workdir) / "profile"
        input_path.write_bytes(content_bytes)
        try:
            subprocess.run(
                [
                    "soffice", "--headless", "--norestore",
                    "-env:UserInstallation=file://%s" % profile_dir,
                    "--convert-to", "docx", "--outdir", workdir,
                    str(input_path),
                ],
                check=True, timeout=_SOFFICE_TIMEOUT_SECONDS,
                capture_output=True,
            )
        except Exception as exc:
            return None, str(exc)
        output_path = Path(workdir) / "input.docx"
        if not output_path.exists():
            return None, "soffice no genero input.docx"
        return output_path.read_bytes(), None


def _extract_docx(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    para_text = "\n".join(p.text for p in doc.paragraphs)
    rows, table_texts = [], []
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            rows.append(cells)
            table_texts.append(" ".join(cells))
    full_text = para_text + "\n" + "\n".join(table_texts)
    return full_text, rows


def _extract_pdf_native(data):
    """Lee un PDF con capa de texto real -- tabla via find_tables()
    (pymupdf), mismo formato de retorno que _extract_docx. Devuelve
    ademas has_text para que quien llama decida si hace falta OCR de
    respaldo."""
    doc = fitz.open(stream=data, filetype="pdf")
    text_parts = []
    rows = []
    has_text = False
    for page in doc:
        t = page.get_text()
        if t.strip():
            has_text = True
        text_parts.append(t)
        for tabla in page.find_tables():
            for row in tabla.extract():
                rows.append([(c or "").strip() for c in row])
    doc.close()
    return "\n".join(text_parts), rows, has_text


def _extract_pdf_ocr(data):
    """OCR de respaldo para PDF sin capa de texto (escaneo puro,
    ~90% real de la muestra). Devuelve texto plano (para
    DNI/fecha/deteccion de no-entrega) Y filas reconstruidas por
    POSICION real (para deteccion de items) -- ver
    _group_words_into_rows(). Sesion de continuidad: la primera
    version usaba solo texto plano con ventana de caracteres para
    encontrar items marcados, y perdia la mayoria de ellos en tablas
    de 2 columnas (verificado real: 3/10, 1/8, 0/5 items en 3
    muestras reales) porque el orden de lectura de Tesseract no
    coincide con el layout visual de la tabla. Con coordenadas reales
    de cada palabra (`image_to_data`) se reconstruye la fila visual
    de verdad, igual que hace pymupdf con una tabla nativa."""
    doc = fitz.open(stream=data, filetype="pdf")
    text_parts = []
    row_lines = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        # Timeout real (S82, causa confirmada de hilos colgados
        # indefinidamente: un documento concreto sin limite de tiempo
        # bloqueaba el hilo entero para siempre, sin avisar, sin pasar
        # al siguiente documento). pytesseract.image_to_string()/
        # image_to_data() aceptan timeout=segundos -- lanzan
        # RuntimeError si se excede, que el except generico de
        # _worker ya captura, registra con traza completa, y cuenta
        # como fallo real -- el hilo sigue vivo para el siguiente.
        # ---
        # Real timeout (S82, confirmed cause of threads hanging
        # forever on a single problematic document, with no warning).
        try:
            text_parts.append(
                pytesseract.image_to_string(img, lang="spa", timeout=60)
            )
            data_dict = pytesseract.image_to_data(
                img, lang="spa", output_type=pytesseract.Output.DICT,
                timeout=60,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                "Timeout OCR (60s) en una pagina: %s" % exc
            ) from exc
        row_lines.extend(_group_words_into_rows(data_dict))
    doc.close()
    return "\n".join(text_parts), row_lines


def _group_words_into_rows(data_dict):
    """Agrupa las palabras de pytesseract.image_to_data() por banda
    horizontal real (mismo centro Y, con tolerancia de altura de
    palabra) y las ordena de izquierda a derecha -- reconstruye la
    fila visual de la tabla sin depender del orden de lectura interno
    de Tesseract, que en tablas de 2 columnas intercala mal."""
    words = []
    n = len(data_dict["text"])
    for i in range(n):
        txt = (data_dict["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data_dict["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf != -1 and conf < 25:
            continue
        words.append({
            "text": txt,
            "left": data_dict["left"][i],
            "top": data_dict["top"][i],
            "height": max(data_dict["height"][i], 1),
        })
    words.sort(key=lambda w: w["top"])
    bands = []
    for w in words:
        cy = w["top"] + w["height"] / 2
        placed = False
        for band in bands:
            band_cy = sum(b["top"] + b["height"] / 2 for b in band) / len(band)
            if abs(cy - band_cy) <= max(w["height"], 10) * 0.6:
                band.append(w)
                placed = True
                break
        if not placed:
            bands.append([w])
    for band in bands:
        band.sort(key=lambda w: w["left"])
    return bands


def _parse_person(text):
    dni_match = _DNI_DIGITS_RE.search(text)
    dni = _compute_full_dni(dni_match.group(1)) if dni_match else None
    name_match = _NAME_ENTREGA_RE.search(text) or _NAME_TABLE_RE.search(text)
    name = name_match.group(1).strip() if name_match else None
    return name, dni


_NIE_PREFIX_MAP = {"X": "0", "Y": "1", "Z": "2"}


def _compute_full_dni(digits):
    """Calcula DNI/NIE completo con letra de control real. Para NIE
    (S82: bug real, Petru Iordachi X6854905P nunca se resolvia), la
    letra inicial X/Y/Z se sustituye por 0/1/2 SOLO para el calculo
    modulo-23 -- el valor devuelto conserva la letra real (X6854905),
    nunca el digito sustituto, para que coincida con como esta
    guardado en PersonIdentity.dni."""
    clean = re.sub(r"[.\s]", "", digits).upper()
    if not clean:
        return None
    prefix = clean[0] if clean[0] in _NIE_PREFIX_MAP else ""
    numeric_str = (
        _NIE_PREFIX_MAP[prefix] + clean[1:] if prefix else clean
    )
    if not numeric_str.isdigit():
        return None
    control = _DNI_LETTER_TABLE[int(numeric_str) % 23]
    return clean + control


def _parse_marked_labels(table_rows):
    marked = []
    for row in table_rows:
        for i, cell in enumerate(row):
            if not _MARK_RE.match(cell):
                continue
            label = None
            if (
                i - 1 >= 0 and row[i - 1]
                and not _MARK_RE.match(row[i - 1])
                and not _DATE_LIKE_RE.match(row[i - 1])
            ):
                label = row[i - 1]
            elif (
                i + 1 < len(row) and row[i + 1]
                and not _DATE_LIKE_RE.match(row[i + 1])
            ):
                label = row[i + 1]
            if label:
                marked.append(label)
    return marked


def _parse_marked_labels_spatial(row_bands):
    """Misma logica que _parse_marked_labels (celda a la izquierda o
    derecha de la marca), aplicada sobre filas reconstruidas por
    posicion real en vez de celdas de tabla nativa -- ver
    _group_words_into_rows()."""
    marked = []
    for band in row_bands:
        texts = [w["text"] for w in band]
        for i, txt in enumerate(texts):
            if not _MARK_RE.match(txt):
                continue
            label = None
            if (
                i - 1 >= 0 and texts[i - 1]
                and not _MARK_RE.match(texts[i - 1])
                and not _DATE_LIKE_RE.match(texts[i - 1])
            ):
                # Etiqueta a la izquierda: acumula palabras hacia
                # atras hasta la marca/fecha anterior (una etiqueta
                # real casi siempre son 2-4 palabras, no una sola).
                j = i - 1
                words = []
                while j >= 0 and not _MARK_RE.match(texts[j]) and not _DATE_LIKE_RE.match(texts[j]):
                    words.insert(0, texts[j])
                    j -= 1
                label = " ".join(words)
            elif (
                i + 1 < len(texts) and texts[i + 1]
                and not _DATE_LIKE_RE.match(texts[i + 1])
            ):
                j = i + 1
                words = []
                while j < len(texts) and not _MARK_RE.match(texts[j]) and not _DATE_LIKE_RE.match(texts[j]):
                    words.append(texts[j])
                    j += 1
                label = " ".join(words)
            if label:
                marked.append(label)
    return marked


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _parse_date_from_filename(name):
    match = _FILENAME_DATE_RE.search(name)
    if not match:
        return None
    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, int(month), int(day))
    except ValueError:
        return None


def _parse_date_from_content(text):
    match = _CONTENT_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, int(month), int(day))
    except ValueError:
        return None


# Log persistido a fichero, ademas de stdout -- S81: la consola SSH
# movil se desconecto dos veces durante un --apply real, y al no
# quedar nada en disco, la sesion se cerro sin poder saber si el
# barrido habia terminado, se habia interrumpido a medias, o habia
# fallado. Ver ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md, incidente S81.
_LOG_FH = None


def _log(lock, msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    with lock:
        print(line, flush=True)
        if _LOG_FH is not None:
            _LOG_FH.write(line + "\n")
            _LOG_FH.flush()


def _worker(
    tunnel_port, mysql_password, gcs_client, task_queue, results_lock,
    totals, unmapped_labels, log_lock, apply_changes,
    discard_unresolved, discard_unresolved_items, total_tasks,
    heartbeat_state,
):
    def _connect():
        return pymysql.connect(
            host="127.0.0.1", port=tunnel_port,
            user=MYSQL_USERNAME, passwd=mysql_password,
            db=MYSQL_DB_NAME, charset="utf8mb4", autocommit=False,
        )

    conn = _connect()
    bucket_obj = gcs_client.bucket(BUCKET)

    def bump(key, n=1):
        with results_lock:
            totals[key] = totals.get(key, 0) + n

    # Una sola linea por documento, todo junto -- formato exacto pedido
    # por Miguel Angel (S82) tras dos intentos previos que no le
    # sirvieron (heartbeat separado de la traza, cadencia demasiado
    # espaciada): "procesando archivo x de y transcurrido hh:mm:ss
    # estimado hh:mm:ss". El contador de posicion (x) se incrementa al
    # COGER la tarea, bajo el mismo results_lock que ya protege totals
    # -- nunca una condicion de carrera entre hilos.
    # ---
    # One single line per document, everything together -- exact
    # format requested by Miguel Angel after two previous attempts
    # that didn't work for him.
    def _next_position():
        with results_lock:
            heartbeat_state["iniciados"] += 1
            posicion = heartbeat_state["iniciados"]
            completados = totals.get("procesados", 0)
        elapsed = time.time() - heartbeat_state["start"]
        elapsed_txt = str(datetime.timedelta(seconds=int(elapsed)))
        if completados > 0:
            ritmo = elapsed / completados  # segundos por documento
            restantes = max(total_tasks - completados, 0)
            eta_txt = str(datetime.timedelta(seconds=int(ritmo * restantes)))
        else:
            eta_txt = "calculando..."
        return posicion, elapsed_txt, eta_txt

    while True:
        task = task_queue.get()
        if task is None:
            task_queue.task_done()
            break
        entry_id, blob_name, name, parent_path = task
        posicion, elapsed_txt, eta_txt = _next_position()
        _log(
            log_lock,
            "Procesando archivo %d de %d: %s/%s -- transcurrido %s -- "
            "estimado %s"
            % (
                posicion, total_tasks, parent_path, name,
                elapsed_txt, eta_txt,
            ),
        )
        try:
            _process_one(
                conn, bucket_obj, entry_id, blob_name, name, parent_path,
                bump, unmapped_labels, results_lock, log_lock,
                apply_changes, discard_unresolved, discard_unresolved_items,
            )
        except (pymysql.err.Error, OSError) as exc:
            # Conexion MySQL/tunel muerta (S82: causa real confirmada
            # de "FALLO INESPERADO -- (0, '')" en cascada silenciosa,
            # un solo hilo zombie procesando cientos de documentos sin
            # avisar). Reconectar en vez de dejar el hilo muerto para
            # el resto del barrido -- este documento concreto se
            # cuenta como fallo real, pero los siguientes de este
            # mismo hilo vuelven a tener conexion valida.
            # ---
            # Dead MySQL/tunnel connection (S82: confirmed real cause
            # of cascading silent "FALLO INESPERADO -- (0, '')", a
            # single zombie thread processing hundreds of documents
            # without warning). Reconnect instead of leaving the
            # thread dead for the rest of the sweep.
            _log(
                log_lock,
                "CONEXION MYSQL PERDIDA, RECONECTANDO: %s/%s -- %s"
                % (parent_path, name, exc),
            )
            try:
                conn.close()
            except Exception:
                pass
            conn = _connect()
            bump("fallos_lectura")
            bump("reconexiones_mysql")
        except Exception:
            import traceback
            _log(
                log_lock,
                "FALLO INESPERADO: %s/%s -- %s"
                % (parent_path, name, traceback.format_exc()),
            )
            bump("fallos_lectura")
        finally:
            task_queue.task_done()

    conn.close()


def _process_one(
    conn, bucket_obj, entry_id, blob_name, name, parent_path,
    bump, unmapped_labels, results_lock, log_lock,
    apply_changes, discard_unresolved, discard_unresolved_items,
):
    blob = bucket_obj.blob(blob_name)
    data = blob.download_as_bytes()

    name_lower = name.lower()
    text, rows = "", []

    is_ocr = False
    if name_lower.endswith(".doc"):
        docx_bytes, err = _convert_doc_to_docx(data)
        if docx_bytes is None:
            _log(log_lock, "FALLO CONVERSION: %s/%s -- %s" % (parent_path, name, err))
            bump("fallos_lectura")
            return
        text, rows = _extract_docx(docx_bytes)
    elif name_lower.endswith(".docx"):
        text, rows = _extract_docx(data)
    elif name_lower.endswith(".pdf"):
        text, rows, has_text = _extract_pdf_native(data)
        if not has_text:
            text, rows = _extract_pdf_ocr(data)
            is_ocr = True
    else:
        _log(log_lock, "EXTENSION NO SOPORTADA: %s/%s" % (parent_path, name))
        bump("fallos_lectura")
        return

    bump("procesados")

    if apply_changes:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE document_explorer_documentindexentry "
                "SET ocr_text=%s WHERE id=%s",
                (text, entry_id),
            )
        conn.commit()

    no_delivery = _detect_non_delivery(text)
    if no_delivery:
        _log(log_lock, "NO ES ENTREGA (%s): %s/%s" % (no_delivery, parent_path, name))
        bump("no_es_entrega")
        bump("no_es_entrega_%s" % no_delivery)
        return

    _, dni = _parse_person(text)
    date_ = _parse_date_from_filename(name) or _parse_date_from_content(text)

    with conn.cursor() as cur:
        if not dni:
            _log(log_lock, "SIN DNI: %s/%s" % (parent_path, name))
            bump("sin_persona")
            if apply_changes and discard_unresolved:
                _trash_entry(cur, entry_id)
                conn.commit()
                bump("sin_persona_a_papelera")
            return

        cur.execute(
            "SELECT id FROM document_explorer_personidentity WHERE dni = %s",
            (_normalize_dni(dni),),
        )
        row = cur.fetchone()
        if row is None:
            _log(log_lock, "DNI SIN PersonIdentity: %s -- %s/%s" % (dni, parent_path, name))
            bump("sin_persona")
            if apply_changes and discard_unresolved:
                _trash_entry(cur, entry_id)
                conn.commit()
                bump("sin_persona_a_papelera")
            return
        person_id = row[0]

        if not date_:
            _log(log_lock, "SIN FECHA reconocible: %s/%s" % (parent_path, name))
            bump("sin_items")
            if apply_changes and discard_unresolved_items:
                _trash_entry(cur, entry_id)
                conn.commit()
                bump("sin_items_a_papelera")
            return

        if rows and not is_ocr:
            labels = _parse_marked_labels(rows)
            codes = set()
            for label in labels:
                code = _map_label(label)
                if code:
                    codes.add(code)
                else:
                    bump("items_sin_mapear")
                    with results_lock:
                        unmapped_labels[label] = unmapped_labels.get(label, 0) + 1
            extraction_method = "HEURISTIC"
        else:
            labels = _parse_marked_labels_spatial(rows) if rows else []
            codes = set()
            for label in labels:
                code = _map_label(label)
                if code:
                    codes.add(code)
                else:
                    bump("items_sin_mapear")
                    with results_lock:
                        unmapped_labels[label] = unmapped_labels.get(label, 0) + 1
            extraction_method = "OCR"

        if not codes:
            # Fallback (S82): plantilla sin marcas de casilla -- solo
            # se intenta cuando el camino normal (tabla/OCR espacial)
            # no encontro nada, nunca sustituye a las marcas cuando
            # si las hay.
            fallback_codes = _parse_plain_list_items(text)
            if fallback_codes:
                codes = fallback_codes
                extraction_method = "HEURISTIC" if not is_ocr else "OCR"
                _log(
                    log_lock,
                    "Items via lista plana (sin marcas): %s/%s -- %s"
                    % (parent_path, name, sorted(codes)),
                )

        if not codes:
            _log(log_lock, "SIN ITEMS reconocidos: %s/%s" % (parent_path, name))
            bump("sin_items")
            if apply_changes and discard_unresolved_items:
                _trash_entry(cur, entry_id)
                conn.commit()
                bump("sin_items_a_papelera")
            return

        if not apply_changes:
            _log(
                log_lock,
                "OK (dry-run, %s): %s -> persona_id=%d fecha=%s items=%s"
                % (extraction_method, name, person_id, date_.isoformat(), sorted(codes)),
            )
            bump("documentos_completos")
            bump("deliveries_creadas", len(codes))
            return

        cur.execute(
            "SELECT id, code FROM document_explorer_epiitemcatalog "
            "WHERE code IN (%s)" % ",".join(["%s"] * len(codes)),
            list(codes),
        )
        catalog_by_code = {code: pk for pk, code in cur.fetchall()}

        created_this_doc = 0
        new_rows_this_doc = 0
        for code in codes:
            epi_pk = catalog_by_code.get(code)
            if epi_pk is None:
                _log(log_lock, "AVISO: codigo %s no existe en catalogo -- omitido (%s/%s)" % (code, parent_path, name))
                continue
            cur.execute(
                "SELECT id FROM document_explorer_epidelivery "
                "WHERE person_id=%s AND epi_id=%s AND delivery_date=%s",
                (person_id, epi_pk, date_),
            )
            existing = cur.fetchone()
            created_this_doc += 1
            if existing is None:
                cur.execute(
                    "INSERT INTO document_explorer_epidelivery "
                    "(person_id, epi_id, delivery_date, source_entry_id, "
                    "extraction_method, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())",
                    (person_id, epi_pk, date_, entry_id, extraction_method),
                )
                new_rows_this_doc += 1

        bump("deliveries_creadas", new_rows_this_doc)
        if created_this_doc == len(codes):
            cur.execute(
                "SELECT id FROM django_content_type "
                "WHERE app_label='document_explorer' AND model='personidentity'"
            )
            person_ct_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE document_explorer_documentindexentry "
                "SET domain_content_type_id=%s, domain_object_id=%s "
                "WHERE id=%s",
                (person_ct_id, person_id, entry_id),
            )
            trashed = _trash_entry(cur, entry_id)
            conn.commit()
            if trashed:
                _log(log_lock, "COMPLETO (%s): %s -> persona_id=%d, %d entregas, original a papelera" % (extraction_method, name, person_id, created_this_doc))
            else:
                _log(log_lock, "COMPLETO (aviso: no se pudo enviar a papelera): %s" % name)
            bump("documentos_completos")
        else:
            conn.rollback()
            _log(log_lock, "PARCIAL: %s -- %d de %d items creados, original SIN tocar" % (name, created_this_doc, len(codes)))


def _trash_entry(cur, entry_id):
    """Papelera logica -- misma semantica que trash_dossier_entry()
    del lado Django (deleted_at/deleted_by), resuelta aqui por SQL
    directo porque la VM no tiene Django. deleted_by fijo al mismo
    CompanyUser que ya usa _resolve_dossier_trash_user() en
    produccion (alvarez_admin) -- confirmar que sigue siendo la
    cuenta real antes de un --apply grande."""
    cur.execute(
        "SELECT cu.id FROM ivr_config_companyuser cu "
        "JOIN auth_user u ON u.id = cu.user_id WHERE u.username = %s",
        ("alvarez_admin",),
    )
    row = cur.fetchone()
    if row is None:
        return False
    admin_id = row[0]
    cur.execute(
        "UPDATE document_explorer_documentindexentry "
        "SET deleted_at=NOW(), deleted_by_id=%s WHERE id=%s",
        (admin_id, entry_id),
    )
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument(
        "--discard-unresolved-persona", action="store_true",
        dest="discard_unresolved",
    )
    parser.add_argument(
        "--discard-unresolved-items", action="store_true",
        dest="discard_unresolved_items",
    )
    parser.add_argument(
        "--pdf-only", action="store_true",
        help=(
            "Acota a solo .pdf -- util para probar especificamente el "
            "camino OCR (los .doc/.docx nativos, minoria real de 15 "
            "sobre 767, ya se sabe que funcionan bien)."
        ),
    )
    parser.add_argument(
        "--shard-count", type=int, default=1,
        help=(
            "Numero total de procesos en paralelo (S82, mismo patron "
            "que split_rm_dossier_vm.py) -- una ventana de PowerShell/"
            "gcloud compute ssh por shard, cada una con su propio "
            "--shard-index."
        ),
    )
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()

    if not (0 <= args.shard_index < max(args.shard_count, 1)):
        parser.error("--shard-index debe estar entre 0 y --shard-count - 1")

    global _LOG_FH
    log_path = "extract_epis_deliveries_vm_%s_shard%d.log" % (
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), args.shard_index,
    )
    _LOG_FH = open(log_path, "a", encoding="utf-8")
    print("Log persistido en: %s (sobrevive a una desconexion de la consola)" % log_path)

    pa_password = getpass.getpass(
        "Contrasena de PythonAnywhere (la de la web, para el tunel SSH): "
    )
    mysql_password = getpass.getpass(
        "Contrasena de MySQL (panel PythonAnywhere, pestana 'Databases'): "
    )

    print("Abriendo tunel SSH a %s ..." % SSH_HOSTNAME)
    tunnel = sshtunnel.SSHTunnelForwarder(
        SSH_HOSTNAME,
        ssh_username=PYTHONANYWHERE_USERNAME,
        ssh_password=pa_password,
        remote_bind_address=(MYSQL_HOSTNAME, 3306),
        host_pkey_directories=[],
        allow_agent=False,
    )
    tunnel.start()
    print("Tunel abierto, puerto local %d." % tunnel.local_bind_port)

    conn = pymysql.connect(
        host="127.0.0.1", port=tunnel.local_bind_port,
        user=MYSQL_USERNAME, passwd=mysql_password,
        db=MYSQL_DB_NAME, charset="utf8mb4",
    )
    with conn.cursor() as cur:
        ext_pattern = r"\.pdf$" if args.pdf_only else r"\.(pdf|docx?)$"
        shard_clause = ""
        params = (BUCKET, ext_pattern)
        if args.shard_count > 1:
            shard_clause = " AND e.id %% %s = %s"
            params = params + (args.shard_count, args.shard_index)
        cur.execute(
            "SELECT e.id, e.blob_name, e.name, e.parent_path "
            "FROM document_explorer_documentindexentry e "
            "JOIN document_explorer_documenttypecatalog t "
            "  ON e.document_type_id = t.id "
            "WHERE e.bucket = %s AND t.code = 'EPIS' "
            "AND e.entry_kind = 'FILE' "
            "AND e.deleted_at IS NULL AND e.purged_at IS NULL "
            "AND e.name REGEXP %s "
            "AND (e.ocr_text IS NULL OR e.ocr_text = '') "
            + shard_clause +
            " ORDER BY e.id",
            params,
        )
        tasks = cur.fetchall()
    conn.close()

    if args.limit:
        tasks = tasks[:args.limit]

    print("Autenticando con GCS (clave del agente H28) ...")
    gcs_client = storage.Client.from_service_account_json(
        get_service_account_key_path()
    )

    shard_info = (
        " shard %d/%d" % (args.shard_index, args.shard_count)
        if args.shard_count > 1 else ""
    )
    print(
        "=== %d documento(s) en alcance (%s, %d hilo(s)%s) ==="
        % (len(tasks), "APLICANDO" if args.apply else "DRY-RUN", args.threads, shard_info)
    )

    task_queue = Queue()
    for t in tasks:
        task_queue.put(t)
    for _ in range(args.threads):
        task_queue.put(None)

    results_lock = threading.Lock()
    log_lock = threading.Lock()
    totals = {}
    unmapped_labels = {}

    threads = []
    heartbeat_state = {"iniciados": 0, "start": time.time()}
    total_tasks = len(tasks)
    for _ in range(args.threads):
        th = threading.Thread(
            target=_worker,
            args=(
                tunnel.local_bind_port, mysql_password, gcs_client,
                task_queue, results_lock, totals, unmapped_labels,
                log_lock, args.apply, args.discard_unresolved,
                args.discard_unresolved_items, total_tasks, heartbeat_state,
            ),
        )
        th.start()
        threads.append(th)

    task_queue.join()
    for th in threads:
        th.join()


    tunnel.stop()

    summary_lines = ["", "=== RESUMEN ==="]
    for key, value in sorted(totals.items()):
        summary_lines.append("    %s: %d" % (key, value))
    if unmapped_labels:
        summary_lines.append("    Etiquetas sin mapear (frecuencia):")
        for label, n in sorted(unmapped_labels.items(), key=lambda x: -x[1]):
            summary_lines.append("      %4d  %r" % (n, label))
    for line in summary_lines:
        print(line)
        _LOG_FH.write(line + "\n")
    _LOG_FH.flush()
    _LOG_FH.close()


if __name__ == "__main__":
    main()
