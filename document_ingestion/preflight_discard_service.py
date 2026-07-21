# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/preflight_discard_service.py
"""
Servicio de descarte PREVIO a la subida, exclusivamente por nombre de
archivo -- nunca llama a Gemini, nunca toca bytes de ningún PDF (S026,
decision explicita de Miguel Angel a raiz del incidente real de S025:
13 documentos maestros de la A-45 perdidos por un fallo de
assess_master_coverage() que, analizados uno a uno, resultaron ser
TODOS redundantes -- nunca deberian haberse llegado a subir).

Flujo tal cual lo describio Miguel Angel: "Leer nombre de archivo ->
heuristica -> lista de descarte -> conformidad -> subir unicamente los
que pasen el primer filtro". Este modulo implementa la heuristica; la
vista (panel/views_documentation.py, DocumentationPreflightView) la
invoca ANTES de que el JS del navegador (hub.html) empiece el troceo
de subida real -- ver esa vista para el punto exacto de enganche.

Dos reglas independientes, en este orden:

REGLA A -- descarte ESTRUCTURAL (siempre, sin comparar fechas):
    un nombre que combina dos tipos de documento ("+") o lleva un
    sufijo de compresion COMPRIMIDO/COMPRESSED es, por construccion,
    un documento maestro/dossier -- ya cubierto por los individuales
    que se suben en el mismo lote (mismo principio que
    _MASTER_HEURISTIC_KEYWORDS de
    machine_documents.document_classification_service, pero aplicado
    ANTES de la subida, no despues, y sin exigir un tamano minimo:
    aqui no hay bytes que pesar todavia).

    NO incluye "UNLOCKED" (retirado en S026, mismo dia, tras
    contraejemplo real de Miguel Angel): a diferencia de
    COMPRIMIDO/COMPRESSED, que Miguel Angel reconoce sin ambiguedad
    como "todo junto, dossier", UNLOCKED no tiene para el ningun
    significado reconocible por si solo -- palabras suyas: "no le
    encuentro relacion con el dossier... para mi unlocked es algo que
    se ha abierto, que ya no tiene llave". El caso real que lo prueba:
    "A-45 E-6998-BDY REC SEG ALLIANZ 01-01-2026_unlocked.pdf" (uno de
    los 13 perdidos en S025) es, por su propio nombre, un recibo de
    seguro Allianz vigente de 2026 -- el mas reciente de su grupo, no
    un dossier -- y bajo el criterio correcto NUNCA deberia haberse
    descartado solo por llevar "_unlocked". Confirmado ademas que no
    queda copia en ningun sitio del sistema para poder abrir el
    archivo y comprobarlo con certeza (ver
    machine_documents.tasks.process_machine_document_batch: un
    maestro descartado se borra local, "nunca llego a subirse a
    GCS") -- sin ese archivo, cualquier regla sobre UNLOCKED seria
    hipotesis sin datos, prohibido por principio de sesion.

REGLA B -- descarte por OBSOLESCENCIA DE GRUPO, criterio de TRES
    FACTORES (Miguel Angel, S026, palabras textuales): "si
    determinamos la maquina, el tipo de documento y la fecha a la que
    hace referencia el documento, podemos discriminar perfectamente
    los archivos a subir o no". Los TRES deben identificarse con
    confianza para poder descartar -- si falta cualquiera de los tres,
    se sube sin comparar, sin excepcion:

    1. MAQUINA -- "principal, encontrar el codigo de la maquina" (en
       BD, via match_machine_asset_by_filename, que tambien reconoce
       la matricula "si viene" -- Miguel Angel: "si no viene, no,
       pero si viene, hay que encontrarla", ya cubierto por esa
       funcion, que busca codigo O matricula). Sin maquina
       identificada, la REGLA B nunca se aplica -- ni siquiera la
       comparacion dentro del propio lote.
    2. TIPO DE DOCUMENTO -- por palabra clave del nombre (ver
       _OBSOLESCENCE_GROUP_KEYWORDS), excluyendo SIEMPRE el codigo de
       maquina y la matricula del propio nombre antes de buscar la
       palabra clave (se repiten en todos los archivos del lote, no
       diferencian nada -- Miguel Angel: "el cuello de la maquina...
       esa parte no la vas a poner... tu tienes que meter en lo que
       es ya el nombre que diferencia el documento").
    3. FECHA -- "es importantisimo determinar la fecha del documento
       en el nombre, porque se puede haber generado mas tarde el
       documento y realmente ser de un año mucho anterior" -- SIEMPRE
       formato español dia-mes-año, pero de ANCHO Y SEPARADOR
       DESCONOCIDOS de antemano (Miguel Angel: "no sabemos el formato
       que va a tener, si va a venir el dia con dos digitos, con
       uno... separados por un guion, por un guion bajo... no lo
       vamos a saber") -- ver parse_date_from_filename(), agnostica
       de separador y de ancho de digitos. Documentos de un tipo que
       NUNCA caduca (se hacen una vez para toda la vida util de la
       maquina) no llevan fecha en el nombre -- esos se suben siempre,
       sin comparar (Miguel Angel: "esos habra que subirlos
       inequivocamente").

    Con los tres factores identificados: se queda solo el mas
    moderno POR FECHA DE NOMBRE dentro del propio lote (Miguel Angel,
    S026: "el candidato sera el mas moderno del lote, evidentemente.
    Es una perdida de tiempo comparar los mas antiguos del lote entre
    si"), y ese candidato se compara despues contra lo YA PERSISTIDO
    en BD para esa maquina (issue_date/period_end/expiry_date reales,
    extraidos por Gemini -- mas fiables que volver a adivinar la
    fecha de un nombre de archivo ya persistido).

    Documentos cuyo TIPO no se reconoce por nombre -- incluido
    cualquier caso "raro" como UNLOCKED sin mas contexto -- se suben
    siempre, para que los lea Gemini (Miguel Angel: "documentos que no
    sepamos bien lo que son... habra que subirlo para que Gemini lo
    lea y vea que es").

Este modulo es agnostico de vista/HTTP -- solo recibe datos ya
resueltos por el llamador (nombres de archivo, maquina opcional,
documentos ya persistidos ya consultados). Vive en document_ingestion
(no en machine_documents) porque el principio DRY del propio hito
(H23/H26) es que la logica de deteccion no se duplique entre dominios
-- personal_documents (H25) podra reutilizar REGLA A/parseo de fecha
tal cual cuando se aborde, aunque hoy (S026) no se ha conectado ahi.
"""
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# REGLA A -- descarte estructural (maestro/dossier por nombre)
# ---------------------------------------------------------------------------
#
# Lista independiente de _MASTER_HEURISTIC_KEYWORDS
# (machine_documents.document_classification_service) a proposito: esa
# constante sigue exigiendo tamano minimo porque decide si un archivo YA
# SUBIDO se manda o no a Gemini; esta decide si un archivo NUNCA llega a
# subirse, sin bytes que pesar. Evolucionan por separado.
#
# NO incluye "UNLOCKED" -- ver docstring del modulo, retirado en S026
# tras contraejemplo real de Miguel Angel (recibo de seguro vigente
# descartado por error solo por llevar ese sufijo).
_STRUCTURAL_DISCARD_KEYWORDS = ["COMPRIMIDO", "COMPRESSED"]


def is_structural_discard_candidate(filename: str) -> bool:
    """
    True si el nombre de archivo, por si solo, delata un documento
    maestro/dossier que combina contenido ya cubierto por los
    individuales del mismo lote -- nunca se sube. Dos senales, ambas
    suficientes por si solas (Miguel Angel, S026, confirmadas sobre
    los 13 casos reales de S025 -- pero ver docstring del modulo:
    "UNLOCKED" quedo fuera de esta lista, no es una senal fiable):

    - Un "+" en el nombre, uniendo dos tipos de documento
      ("FICHA TECNICA+ITV", "POLIZA ALLIANZ+REC").
    - Sufijo de compresion: COMPRIMIDO, COMPRESSED.

    Excluye SIEMPRE los manuales de uso (is_manual_by_filename) antes
    de mirar cualquiera de las dos senales -- falso positivo real
    detectado en pruebas contra datos reales (S026): un manual real
    del lote de la A-45 se llama literalmente
    "A-45 E-6998-BDY MANUAL DE USO-comprimido-2.pdf" y contiene
    "comprimido" en su propio nombre sin ser ningun dossier. Los
    manuales tienen su propia heuristica de nombre, independiente y ya
    probada (machine_documents.document_classification_service), y
    nunca deben pasar por este filtro nuevo.
    """
    # Import perezoso para evitar dependencia circular entre apps a
    # nivel de import de modulo (machine_documents no importa este
    # modulo, pero document_ingestion.entity_matching_service si
    # importa document_classification_service en varios puntos ya).
    from machine_documents.document_classification_service import (
        is_manual_by_filename,
    )

    if is_manual_by_filename(filename):
        return False

    upper_name = filename.upper()
    if "+" in upper_name:
        return True
    return any(keyword in upper_name for keyword in _STRUCTURAL_DISCARD_KEYWORDS)


# ---------------------------------------------------------------------------
# REGLA B -- descarte por obsolescencia de grupo
# ---------------------------------------------------------------------------
#
# Diccionario ESTÁTICO palabra clave -> grupo canonico (Miguel Angel,
# S026: "yo crearia un diccionario... con una palabra que se repite y
# anades todo... forma grupos, conjuntos"). ALLIANZ/POLIZA/SEGURO se
# lumpean en un unico grupo SEGURO -- son la misma categoria de
# negocio (recibo/poliza de seguro), visto en los 13 casos reales
# (S025) y en el individual vigente del mismo lote
# ("..._04_Recibo_Seguro_Allianz_2025.pdf", lleva las dos palabras a
# la vez). Este diccionario estatico es solo el ARRANQUE -- en tiempo
# real se combina con las aseguradoras reales de BD
# (budgets.models.Insurer) y con lo aprendido automaticamente
# (document_ingestion.models.LearnedDocumentTypeKeyword) -- ver
# _dynamic_keyword_group_pairs().
_OBSOLESCENCE_GROUP_KEYWORDS: list[tuple[str, str]] = [
    ("FICHA TECNICA", "FICHA TECNICA"),
    ("ITV", "ITV"),
    ("OCA", "OCA"),
    ("PERMISO DE CIRCULACION", "SEGURO"),
    ("ALLIANZ", "SEGURO"),
    ("MAPFRE", "SEGURO"),
    ("AXA", "SEGURO"),
    ("LINEA DIRECTA", "SEGURO"),
    ("MUTUA MADRILEÑA", "SEGURO"),
    ("MUTUA MADRILENA", "SEGURO"),
    ("ZURICH", "SEGURO"),
    ("GENERALI", "SEGURO"),
    ("PELAYO", "SEGURO"),
    ("REALE", "SEGURO"),
    ("CATALANA OCCIDENTE", "SEGURO"),
    ("PLUS ULTRA", "SEGURO"),
    ("LIBERTY", "SEGURO"),
    ("SEGUROS BILBAO", "SEGURO"),
    ("POLIZA", "SEGURO"),
    ("SEGURO", "SEGURO"),
    ("LIBRO HISTORIAL", "LIBRO HISTORIAL"),
    ("CERTIFICADO DE MANTENIMIENTO", "MANTENIMIENTO"),
    ("CERT MANTENIMIENTO", "MANTENIMIENTO"),
    ("CERT.MANTENIMIENTO", "MANTENIMIENTO"),
]

# Etiqueta legible por grupo CANÓNICO ESTÁTICO -- usada por
# machine_documents.tasks (S026, fase 3) para sustituir el
# document_type que devolvería Gemini cuando la heurística YA tenía
# el tipo claro por máquina+tipo+fecha (Miguel Ángel: "directamente lo
# tenemos ya clasificado por el nombre"). Solo cubre los grupos
# estáticos de arriba -- los grupos dinámicos (aseguradora real de BD,
# o aprendidos) no tienen aquí una etiqueta manual, se dejan tal cual
# los devuelva Gemini (su propio document_type/display_name), ya que
# no hay un texto mejor que inventar sin datos.
CANONICAL_GROUP_DISPLAY_NAMES: dict[str, str] = {
    "FICHA TECNICA": "Ficha técnica",
    "ITV": "Tarjeta ITV",
    "OCA": "Certificado OCA",
    "SEGURO": "Recibo de seguro",
    "LIBRO HISTORIAL": "Libro historial",
    "MANTENIMIENTO": "Certificado de mantenimiento",
}

# Fecha en el nombre: SIEMPRE día-mes-año en español (Miguel Ángel,
# S026: "siempre va a ser día, mes y año"), pero de FORMATO
# desconocido de antemano -- ancho de dígitos y separador variables,
# palabras textuales: "no sabemos el formato que va a tener, si va a
# venir el día con dos dígitos, con uno, si el año va a tener dos
# dígitos, cuatro, si van a estar separados por un guion, por un
# guion bajo... no lo vamos a saber". Separador: cualquier secuencia
# de guion/guion bajo/punto/barra/espacio (independiente entre cada
# par de campos -- "24_4-19" es tan válido como "24-4-19"). Se toma
# la ÚLTIMA coincidencia del nombre (las fechas van al final, antes
# de ".pdf", en todos los casos reales) -- evita que un número suelto
# de expediente confunda el parseo si alguna vez coincidiera por
# casualidad con D-M-Y.
_DATE_PATTERN = re.compile(
    r"(\d{1,2})[-_./ ]+(\d{1,2})[-_./ ]+(\d{2,4})(?!\d)",
)


def _strip_accents_upper(value: str) -> str:
    """Mayusculas y sin acentos, para que 'técnica'/'TECNICA' comparen igual."""
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    return without_accents.upper()


def _strip_machine_reference(filename: str, machine) -> str:
    """
    Quita del nombre (ya en mayusculas/sin acentos) el codigo y la
    matricula de la maquina, si se conoce -- Miguel Angel, S026: "el
    cuello de la maquina... eso no lo vas a poner. La matricula tambien
    se va a repetir, esa parte tampoco la vas a poner". Sin esto, un
    codigo de maquina que por casualidad contuviera una de las palabras
    clave de grupo podria falsear el agrupamiento.
    """
    upper_name = _strip_accents_upper(filename)
    if machine is None:
        return upper_name
    for reference in (getattr(machine, "code", "") or "", getattr(machine, "plate", "") or ""):
        reference_upper = _strip_accents_upper(reference)
        if reference_upper:
            upper_name = upper_name.replace(reference_upper, "")
    return upper_name


def _dynamic_keyword_group_pairs(company) -> list[tuple[str, str]]:
    """
    Diccionario COMPLETO en tiempo real: estático (arriba) + nombres
    de aseguradoras reales de la empresa (budgets.models.Insurer,
    Miguel Ángel S026: "tenemos también una lista de aseguradoras...
    que esa también nos sirve para añadirla al diccionario") + lo
    aprendido automáticamente y activo
    (document_ingestion.models.LearnedDocumentTypeKeyword). Sin
    `company` (nunca debería pasar en producción, solo pruebas
    aisladas) se queda solo con el estático.
    """
    pairs = list(_OBSOLESCENCE_GROUP_KEYWORDS)
    if company is None:
        return pairs

    # Imports perezosos -- mismo motivo que is_manual_by_filename más
    # abajo: evitar acoplar el import de módulo de este archivo
    # ligero a apps con dependencias más pesadas.
    from budgets.models import Insurer
    from document_ingestion.models import LearnedDocumentTypeKeyword

    insurer_names = (
        Insurer.objects.filter(company=company)
        .exclude(insurer_company_name="")
        .values_list("insurer_company_name", flat=True)
        .distinct()
    )
    for name in insurer_names:
        normalized = _strip_accents_upper(name)
        if normalized:
            pairs.append((normalized, "SEGURO"))

    learned = LearnedDocumentTypeKeyword.objects.filter(
        company=company, is_active=True,
    ).values_list("keyword", "canonical_group")
    for keyword, group in learned:
        normalized_keyword = _strip_accents_upper(keyword)
        if normalized_keyword:
            pairs.append((normalized_keyword, group))

    return pairs


def _group_for_text(text: str, pairs: list[tuple[str, str]]) -> str | None:
    """
    Busca en `text` (se normaliza aquí mismo) todas las keywords de
    `pairs` que aparezcan como subcadena, y devuelve el grupo de la
    MÁS LARGA que coincida -- evita que una palabra genérica (p. ej.
    "SEGURO") tape a una más específica (p. ej. el nombre real de una
    aseguradora) cuando ambas aparecen en el mismo nombre. None si
    ninguna coincide.
    """
    upper_text = _strip_accents_upper(text)
    matches = [
        (keyword, group) for keyword, group in pairs
        if keyword and keyword in upper_text
    ]
    if not matches:
        return None
    _best_keyword, best_group = max(matches, key=lambda pair: len(pair[0]))
    return best_group


def find_obsolescence_group(
    filename: str, machine=None, company=None,
    keyword_pairs: list[tuple[str, str]] | None = None,
) -> str | None:
    """
    Devuelve el grupo canonico al que pertenece `filename`, o None si
    no coincide con ninguna palabra clave conocida (estática, de
    aseguradora real, o aprendida) -- en cuyo caso el llamador nunca
    debe aplicar la REGLA B sobre este archivo (se sube sin comparar,
    para que lo clasifique Gemini). `keyword_pairs` permite reutilizar
    un diccionario ya calculado (evaluate_batch lo calcula UNA vez por
    lote en vez de una consulta a BD por archivo) -- si no se pasa, se
    calcula aquí mismo a partir de `company`.
    """
    stripped = _strip_machine_reference(filename, machine)
    pairs = (
        keyword_pairs if keyword_pairs is not None
        else _dynamic_keyword_group_pairs(company)
    )
    return _group_for_text(stripped, pairs)


# Palabras GENÉRICAS de nombre de archivo -- nunca deben aprenderse
# como palabra clave de tipo de documento, por muy "limpias" que
# queden tras quitar máquina/matrícula/fecha/extensión. Son nombres
# que pone el propio software del escáner o la cámara, no dicen nada
# sobre el CONTENIDO del documento -- y como se repiten en TODOS los
# archivos generados por el mismo aparato, aprender una de estas
# palabras contamina cualquier archivo futuro de ese escáner con la
# clasificación del primer error, sin volver a consultar a Gemini
# nunca más. Hallazgo real (S026, cierre de sesión): "SCAN" se
# aprendió -> grupo ITV a partir de UN documento mal clasificado por
# Gemini ("Scan2025-10-27_094743.pdf", en realidad un libro de
# revisiones técnicas, no una tarjeta ITV) -- desde entonces, CUALQUIER
# archivo nombrado "Scan..." (así nombra este escáner concreto todos
# sus archivos, sin excepción) heredó ciegamente esa clasificación
# incorrecta. Miguel Ángel: "eso no es, eso es un libro de historial,
# no es la tarjeta de la ITV".
_GENERIC_FILENAME_WORDS = {
    "SCAN", "ESCANEO", "ESCANEADO", "DIGITALIZACION", "DIGITALIZADO",
    "IMG", "IMAGEN", "IMAGE", "DOC", "DOCUMENTO", "DOCUMENT",
    "FOTO", "PHOTO", "PICTURE", "FILE", "ARCHIVO", "PDF", "COPIA",
    "COPY", "NUEVO", "NEW", "SINTITULO", "UNTITLED", "DSC", "IMG_",
}


def _extract_candidate_keyword(filename: str, machine=None) -> str:
    """
    Extrae la palabra/frase candidata a aprender de un nombre de
    archivo cuyo tipo NO reconoció la heurística -- quita código de
    máquina/matrícula, la fecha (mismo patrón que
    parse_date_from_filename), la extensión, y separadores/números
    sueltos. Si lo que queda es demasiado corto para ser una palabra
    con sentido (ruido), o si es una de las palabras GENÉRICAS de
    _GENERIC_FILENAME_WORDS (nombre puesto por el propio escáner, sin
    relación con el contenido -- ver esa constante), devuelve "" -- el
    llamador (learn_from_classification) no aprende nada en ese caso,
    en vez de ensuciar el diccionario con basura (Miguel Ángel no
    pidió aprender "lo que sea", pidió aprender palabras que
    "diferencian el documento", mismo criterio que ya aplicamos para
    excluir máquina/matrícula del agrupamiento).
    """
    stripped = _strip_machine_reference(filename, machine)
    stripped = re.sub(r"\.PDF$", "", stripped)
    stripped = _DATE_PATTERN.sub(" ", stripped)
    stripped = re.sub(r"[0-9_./-]+", " ", stripped)
    candidate = " ".join(stripped.split()).strip()
    if len(candidate) < 3:
        return ""
    if candidate in _GENERIC_FILENAME_WORDS:
        return ""
    return candidate


def _canonical_group_for_gemini_type(gemini_document_type: str, company) -> str:
    """
    Decide el grupo canónico para una keyword nueva aprendida a
    partir de lo que clasificó Gemini: si el propio texto de
    `gemini_document_type` ya contiene una palabra clave conocida
    (estática, aseguradora real, o ya aprendida antes), se reutiliza
    ESE grupo -- si no, se crea un grupo nuevo a partir del propio
    `gemini_document_type`, normalizado (Miguel Ángel, S016: Gemini
    puede proponer categorías libres, sin lista cerrada -- este
    aprendizaje hereda esa libertad en vez de forzar todo a los
    grupos ya conocidos).
    """
    pairs = _dynamic_keyword_group_pairs(company)
    matched = _group_for_text(gemini_document_type, pairs)
    if matched:
        return matched
    return _strip_accents_upper(gemini_document_type)


def learn_from_classification(
    filename: str, gemini_document_type: str, machine=None, company=None,
) -> None:
    """
    Aprendizaje automático (Miguel Ángel, S026: "el propio sistema
    propone automáticamente nuevas entradas de diccionario... se usa
    en la propia sesión de subida"). Se llama desde
    machine_documents.tasks cada vez que la heurística de nombre NO
    reconoció el tipo de un documento y Gemini lo clasificó -- nunca
    al revés (si la heurística ya lo tenía claro, no hay nada que
    aprender). Activa de inmediato (is_active=True por defecto en el
    modelo) -- el resto de archivos del MISMO lote, procesados a
    continuación en la misma tarea, ya pueden beneficiarse de esta
    keyword nueva.

    Sin `company` o sin `gemini_document_type`, o si no queda ninguna
    palabra candidata aprovechable en el nombre (ver
    _extract_candidate_keyword), no se aprende nada -- nunca se
    inventa una entrada de diccionario sin una señal real de nombre
    de archivo que la respalde.
    """
    if not company or not gemini_document_type:
        return

    from document_ingestion.models import LearnedDocumentTypeKeyword

    candidate = _extract_candidate_keyword(filename, machine)
    if not candidate:
        logger.info(
            "# [learn_from_classification] %s: sin palabra clave "
            "aprovechable tras quitar máquina/matrícula/fecha/"
            "extensión -- no se aprende nada.",
            filename,
        )
        return

    canonical_group = _canonical_group_for_gemini_type(
        gemini_document_type, company,
    )

    obj, created = LearnedDocumentTypeKeyword.objects.get_or_create(
        company=company,
        keyword=candidate,
        defaults={
            "canonical_group": canonical_group,
            "source_filename": filename,
            "source_document_type": gemini_document_type,
        },
    )
    if not created:
        obj.occurrences += 1
        obj.canonical_group = canonical_group
        obj.source_filename = filename
        obj.source_document_type = gemini_document_type
        obj.save(update_fields=[
            "occurrences", "canonical_group", "source_filename",
            "source_document_type", "last_seen",
        ])

    logger.info(
        "# [learn_from_classification] %s -> keyword=%r grupo=%r "
        "(nueva=%s, empresa=%s).",
        filename, candidate, canonical_group, created, company,
    )


# Periodo AAAA-AAAA (S026, hallazgo real de la sesión: certificados
# OCA/pólizas de seguro con nombres como "OCA 2015-2016.pdf",
# "OCA 2016-2017.pdf"... nunca llevan una fecha D-M-Y única, solo el
# rango de años del periodo de vigencia -- _DATE_PATTERN nunca los
# reconocía (exige TRES grupos numéricos, un rango de año solo tiene
# dos), así que cada uno caía en "sin fecha -- se sube siempre" y la
# REGLA B nunca los comparaba entre sí. Cadena real detectada por
# Miguel Ángel en la subida de la A-36: "2014, 2015, 2016, 2017,
# 2018... hemos ido encadenando una serie de errores". Se usa el año
# MÁS RECIENTE del rango (fin del periodo) como fecha de referencia,
# como respaldo SOLO si no hay ningún patrón D-M-Y reconocible.
_YEAR_RANGE_PATTERN = re.compile(r"(?<!\d)(\d{4})[-_./](\d{4})(?!\d)")


def parse_date_from_filename(filename: str) -> date | None:
    """
    Extrae la fecha del nombre de archivo. Dos formatos reconocidos,
    en este orden:

    1. D-M-Y (formato español, ancho de dígitos y separador
       desconocidos de antemano -- ver _DATE_PATTERN).
    2. Periodo AAAA-AAAA (ver _YEAR_RANGE_PATTERN arriba) -- solo si
       el (1) no encontró nada. Se usa el año más reciente del rango.

    Devuelve None si ninguno de los dos patrones aparece, o si el
    único patrón D-M-Y encontrado no es una fecha válida (ej. un
    número de expediente que por casualidad tiene la forma X-Y-Z pero
    no es una fecha real) -- en cualquiera de los casos, el llamador
    debe tratarlo como "no identificado" y subir el archivo sin
    comparar (Miguel Ángel, S026: "los que no se identifiquen bien,
    hay que subirlos").
    """
    matches = _DATE_PATTERN.findall(filename)
    if matches:
        day_str, month_str, year_str = matches[-1]
        try:
            day = int(day_str)
            month = int(month_str)
            year = int(year_str)
            if year < 100:
                year += 2000
            return date(year, month, day)
        except ValueError:
            logger.info(
                "# [parse_date_from_filename] %s: patron %s-%s-%s no "
                "es una fecha valida -- tratado como sin fecha "
                "identificada.",
                filename, day_str, month_str, year_str,
            )
            return None

    range_matches = _YEAR_RANGE_PATTERN.findall(filename)
    if range_matches:
        year1_str, year2_str = range_matches[-1]
        year = max(int(year1_str), int(year2_str))
        logger.info(
            "# [parse_date_from_filename] %s: periodo %s-%s -- usando "
            "%d (año más reciente del rango) como fecha de "
            "referencia.",
            filename, year1_str, year2_str, year,
        )
        return date(year, 1, 1)

    return None


@dataclass(frozen=True)
class PreflightFile:
    """Un archivo del lote a evaluar -- entrada de evaluate_batch()."""
    filename: str


@dataclass(frozen=True)
class PreflightVerdict:
    """
    Resultado de evaluar un archivo del lote. `discard` True implica
    `reason` no vacio. `parsed_date`/`group` se exponen para que la
    vista pueda mostrarlos en la lista de descarte (transparencia para
    la conformidad del supervisor -- nunca se descarta "a ciegas").
    """
    filename: str
    discard: bool
    reason: str = ""
    group: str | None = None
    parsed_date: date | None = None


def evaluate_batch(
    filenames: list[str],
    machine=None,
    company=None,
    persisted_documents: list | None = None,
) -> list[PreflightVerdict]:
    """
    Evalua un lote de nombres de archivo (una sola maquina -- el
    llamador ya debe haber resuelto machine con
    document_ingestion.entity_matching_service.match_machine_asset_by_filename()
    antes de invocar esto, agrupando el lote por maquina si hace
    falta). `company` habilita el diccionario dinámico completo
    (aseguradoras reales + aprendizaje, ver
    _dynamic_keyword_group_pairs) -- sin él, solo se usa el
    diccionario estático de arranque. `persisted_documents` son
    objetos con .document_type, .issue_date, .period_end,
    .expiry_date -- normalmente
    machine_documents.models.MachineDocument.objects.filter(machine_asset=machine)
    ya resuelto por el llamador (este modulo nunca consulta BD, salvo
    Insurer/LearnedDocumentTypeKeyword para el diccionario dinámico).

    Devuelve un veredicto por archivo, en el mismo orden de entrada.
    """
    persisted_documents = persisted_documents or []
    verdicts: list[PreflightVerdict] = []

    # Diccionario dinámico calculado UNA sola vez para todo el lote
    # (evita una consulta a Insurer/LearnedDocumentTypeKeyword por
    # archivo) -- se reutiliza tanto para agrupar los archivos del
    # lote como para reconocer el grupo de los documentos ya
    # persistidos.
    keyword_pairs = _dynamic_keyword_group_pairs(company)

    # Paso 1 -- REGLA A, y de paso, fecha/grupo de los que la superan
    # (necesarios para la REGLA B en el paso 2). Sin MAQUINA
    # identificada, la REGLA B no se aplica en absoluto -- "principal,
    # encontrar el código de la máquina" (Miguel Ángel, S026): sin
    # ese primer factor no hay contra qué agrupar ni comparar con
    # seguridad, ni siquiera dentro del propio lote.
    survivors: list[tuple[str, str | None, date | None]] = []
    for filename in filenames:
        if is_structural_discard_candidate(filename):
            verdicts.append(PreflightVerdict(
                filename=filename,
                discard=True,
                reason=(
                    "Nombre de archivo indica documento maestro/dossier "
                    "combinado (\"+\" entre tipos, o sufijo de "
                    "compresión) -- su contenido ya está cubierto por "
                    "los documentos individuales del mismo lote."
                ),
            ))
            continue
        if machine is None:
            verdicts.append(PreflightVerdict(filename=filename, discard=False))
            continue
        group = find_obsolescence_group(
            filename, machine=machine, keyword_pairs=keyword_pairs,
        )
        parsed_date = parse_date_from_filename(filename) if group else None
        survivors.append((filename, group, parsed_date))

    # Paso 2 -- REGLA B, solo entre los que tienen grupo Y fecha
    # identificados. Un archivo sin grupo, o con grupo pero sin fecha,
    # se sube directo (verdict discard=False) sin pasar por esta
    # comparación -- ver docstring del módulo.
    by_group: dict[str, list[tuple[str, date]]] = {}
    for filename, group, parsed_date in survivors:
        if group is not None and parsed_date is not None:
            by_group.setdefault(group, []).append((filename, parsed_date))

    # Candidato mas moderno del lote por grupo -- nunca se comparan los
    # mas antiguos del lote entre si (Miguel Angel, S026: perdida de
    # tiempo), se descartan todos salvo el maximo directamente.
    batch_winner_by_group: dict[str, tuple[str, date]] = {
        group: max(entries, key=lambda entry: entry[1])
        for group, entries in by_group.items()
    }

    # Fecha mas reciente ya persistida en BD por grupo, para comparar
    # el candidato del lote contra ella -- mismo diccionario dinámico
    # que el paso 1, para que un documento persistido clasificado bajo
    # una aseguradora real o una keyword aprendida también se
    # reconozca aquí (no solo el estático).
    persisted_latest_by_group: dict[str, date] = {}
    for document in persisted_documents:
        group = _group_for_text(
            getattr(document, "document_type", "") or "", keyword_pairs,
        )
        if group is None:
            continue
        candidate_date = (
            getattr(document, "issue_date", None)
            or getattr(document, "period_end", None)
            or getattr(document, "period_start", None)
            or getattr(document, "expiry_date", None)
        )
        if candidate_date is None:
            continue
        current_latest = persisted_latest_by_group.get(group)
        if current_latest is None or candidate_date > current_latest:
            persisted_latest_by_group[group] = candidate_date

    for filename, group, parsed_date in survivors:
        if group is None or parsed_date is None:
            verdicts.append(PreflightVerdict(
                filename=filename, discard=False, group=group,
                parsed_date=parsed_date,
            ))
            continue

        winner_filename, _winner_date = batch_winner_by_group[group]
        if filename != winner_filename:
            verdicts.append(PreflightVerdict(
                filename=filename,
                discard=True,
                reason=(
                    f"Versión obsoleta de \"{group}\" -- hay otro archivo "
                    f"del mismo lote de fecha más reciente."
                ),
                group=group,
                parsed_date=parsed_date,
            ))
            continue

        persisted_latest = persisted_latest_by_group.get(group)
        if persisted_latest is not None and persisted_latest >= parsed_date:
            verdicts.append(PreflightVerdict(
                filename=filename,
                discard=True,
                reason=(
                    f"Versión obsoleta de \"{group}\" -- ya existe un "
                    f"documento persistido más reciente o igual "
                    f"({persisted_latest.isoformat()})."
                ),
                group=group,
                parsed_date=parsed_date,
            ))
            continue

        verdicts.append(PreflightVerdict(
            filename=filename, discard=False, group=group,
            parsed_date=parsed_date,
        ))

    return verdicts
