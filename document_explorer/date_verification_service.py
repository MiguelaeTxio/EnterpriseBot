# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/date_verification_service.py
"""
H30 (S48). Servicio compartido de extraccion/contraste de fecha para
consumidores reales:

1. `run_fase_b1_ocr_dates` (comando de gestion, recorrido masivo por
   lotes sobre el histórico ya indexado).
2. `expiry_resolution_service.resolve_expiry_date()` -- resolucion de
   fecha en tiempo real tras la reubicacion de un archivo (H30 S50).
3. `classification_service._extract_dni_via_ocr()` -- lectura de
   DNI/NIE del contenido real de un documento.

CENTRALIZADO EN S102: `extract_text()` ya NO usa Tesseract local para
PDF/imagen -- delega en `cloud_vision_service.extract_text()` (texto
embebido del PDF primero, Cloud Vision API despues). Decision
explicita de Miguel Angel, verbatim: "el texto lo tenemos que extraer
con llamadas a... Cloud Vision, nunca jamas con OCR de PythonAnywhere"
-- origen real: un Comando S tardo "lo mas grande" ejecutando OCR
local sobre un unico documento desde la ficha (S102), mismo sintoma ya
resuelto para el alta en H31/S100 (cuota diaria de CPU compartida de
PythonAnywhere).

`extract_expiry_via_gemini()` sigue siendo el ultimo recurso, acotado
a `DocumentTypeCatalog.ocr_unreliable=True` (verificado con datos
reales -- hoy solo ITV, tarjetas manuscritas con fondo de seguridad
que domina cualquier lectura visual, ver anexo H30 "COMPLETADAS EN
S48"): nunca se usa Gemini para tipos que ya resuelve el texto
extraido, o que el propio supervisor ya introduce a mano.
"""
import io
import json
import re
import unicodedata
from datetime import date

import fitz
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot

_EXPIRY_CONTEXT = [
    "CADUCA", "CADUCIDAD", "VALIDO HASTA", "VALIDA HASTA", "VENCE",
    "VENCIMIENTO", "HASTA EL", "PROXIMA REVISION", "PROXIMA INSPECCION",
    "FECHA LIMITE",
    # H30 (S91). Impreso oficial "COMUNICACION DE LA PRORROGA DEL
    # CONTRATO DE TRABAJO" (SEPE/Seguridad Social) -- campo
    # estructurado "Fecha de Termino: DD/MM/AAAA", verificado en
    # COMUNICACION_CONTRATO (id=34826, id=36361). Plantilla oficial
    # fija, probable que se repita en mas comunicaciones de prorroga.
    "FECHA DE TERMINO",
]
_ISSUE_CONTEXT = [
    "EXPEDICION", "EXPEDIDO", "EXPEDIDA", "EMISION", "EMITIDO",
    "EMITIDA", "CON FECHA", "SOMETIDO EL DIA", "MALAGA A",
    # H30 (S87): "CONFECHA" fusionado sin espacio -- ver comentario
    # completo en la copia standalone.
    "CONFECHA",
    # H30 (S87): etiqueta real de impreso antiguo REA -- ver
    # comentario completo en la copia standalone.
    "FECHA DE ALTA",
    # H30 (S87): etiqueta real del "PARTE MEDICO DE BAJA/ALTA DE
    # INCAPACIDAD TEMPORAL (P.9)" -- "PARTE DE BAJA [X] Fecha de la
    # baja 19/10/2020".
    "FECHA DE LA BAJA",
    # H31 (S97): mismo campo, fusionado sin espacios por OCR de baja
    # calidad -- ver comentario completo en la copia standalone.
    "FECHADELA BAJA",
    # H30 (S91). Plantilla real de "Firma/recibi del trabajador... A
    # fecha(DD/MM/AAAA)" -- verificada en EVALUACION_RIESGO (id=22002,
    # id=22018, mismo impreso "ENTREGA DE EVALUACION DE RIESGO" de
    # GRUPO ALVAREZ). "CON FECHA" ya estaba cubierto, "A FECHA" suelta
    # nunca lo estuvo -- template usado en varios tipos con recibi
    # firmado, no solo en este.
    "A FECHA",
    # H30 (S91). Cierre real de "CLAUSULA_PROTECCION_DATOS" (LOPD,
    # plantilla de 2014) -- "...mediante la presente y firma de
    # conformidad, en Santa Rosalía a 30 de septiembre de 2014."
    # Verificado en 8 documentos reales (Delgado Hurtado, Alvarez Gea,
    # Carlin Carvajal, Diaz Quintero, Garcia Luque, Ramos Zambrana,
    # Zafra Peralta, Fontalba Seron) -- mismo cierre "en <Ciudad> a
    # <fecha>" que "MALAGA A", pero con ciudad variable
    # (Santa Rosalía, no Málaga). "FIRMA DE CONFORMIDAD" es la frase
    # fija que precede a la fecha en todos los casos, sin depender de
    # la ciudad.
    "FIRMA DE CONFORMIDAD",
    # H30 (S91). Mismo impreso oficial que "FECHA DE TERMINO" arriba
    # -- campo estructurado "Fecha de Inicio: DD/MM/AAAA" del mismo
    # formulario de prorroga de contrato.
    "FECHA DE INICIO",
]
# H30 (sesion de continuidad tras S79). Incidente real: 3 de 5
# RECONOCIMIENTO_MEDICO reales devolvieron la fecha de NACIMIENTO
# como si fuera la fecha del examen -- cuando la fecha real de
# emision no se reconoce (contexto roto por huecos de formulario,
# OCR degradado), la unica fecha "suelta" que queda es la de
# nacimiento (siempre presente en la cabecera de estos certificados,
# "nacido el..."), y el criterio de "unica fecha, por defecto" la
# acepta sin saber que es una fecha de nacimiento, no de emision.
# Estas fechas se descartan por completo (nunca entran ni siquiera en
# el cubo "otras fechas") en vez de solo evitarlas como contexto de
# emision/caducidad -- una fecha de nacimiento nunca es la fecha
# buscada, sea cual sea el tipo documental.
_BIRTHDATE_CONTEXT = [
    "NACIDO", "NACIDA", "NACIO", "FECHA DE NACIMIENTO", "NACIMIENTO",
]

# H30 (S89). Recibos domiciliados de cuotas (AUTONOMO, CSS) traen
# SIEMPRE 2-3 fechas ruido ademas de la fecha real del recibo (campo
# "FECHA" arriba, repetido como "FECHA VALOR" abajo), impidiendo
# resolver por "unica fecha, por defecto" -- verificado contra OCR
# real (id=27493, 27503, 27525) y foto real aportada por Miguel Angel
# (id=27494):
# 1. "PERIODO 12/12-2012" -- notacion de periodo, NO una fecha; el
#    regex general de fecha (separadores "/" y "-" mezclados) la
#    parsea igualmente como si fuera dia/mes/anio. Exclusion por
#    palabra cercana (ventana estandar _CONTEXT_WINDOW) -- funciona
#    bien, la etiqueta esta pegada a su propia fecha.
# 2. "Inscrita Reg. Mercantil ... Inscripc.1a DD/MM/AAAA" -- fecha de
#    inscripcion registral de la entidad bancaria, constante en TODOS
#    los recibos. Misma exclusion por palabra cercana.
# 3. "FECHA MAXIMA DEVOLUCION PARA RECIBOS NO AUTORIZADOS...: DD/MM/AAAA"
#    -- plazo legal de devolucion del banco. El tramo legal entre la
#    etiqueta y la fecha supera cualquier ventana de contexto por
#    palabra razonable; un primer intento con ventana ampliada (140)
#    provoco una REGRESION REAL (id=27525): tambien excluia la fecha
#    buena cuando caia cerca. Corregido con exclusion por POSICION
#    EXACTA: se captura la fecha concreta dentro de la frase completa
#    de principio a fin (ver _NOISE_SPAN_PATTERNS), nunca por cercania
#    de palabra.
# 4. "https://www.cajamar.es/BE/ServletOperation DD/MM/AAAA" -- fecha
#    de generacion del documento en el pie de pagina de la web del
#    banco, sin relacion con el recibo (id=27503). Misma exclusion por
#    posicion exacta.
# Estas fechas se descartan por completo (igual que _BIRTHDATE_CONTEXT),
# nunca solo se evitan como contexto de emision/caducidad.
# H30 (S89). "https://www.cajamar.es/BE/ServletOperation DD/MM/AAAA"
# (o "DD/MM/AAAA https://www.cajamar.es/BE/ServletOperation" -- el
# sello de impresion del navegador puede ir en cualquier orden segun
# el documento, verificado real id=27503 (fecha despues) vs id=27510
# (fecha antes)) -- fecha de generacion/impresion, no del recibo.
# Por contexto bidireccional (like PERIODO/INSCRIPC), no por posicion
# exacta direccional -- un primer intento solo cubria un sentido y no
# excluia la duplicidad del mismo valor en el otro sentido (id=27510).
_RECEIPT_NOISE_CONTEXT = [
    # H30 (S89): ambas variantes conviven -- SERVLETOPERATION para el
    # caso normal (palabra intacta), ELOPERATION para cuando el OCR
    # rompe la palabra con un espacio insertado ("Serv elOperation",
    # verificado real id=27516). La palabra completa NO contiene el
    # fragmento como substring (hay una T donde ELOPERATION lleva L),
    # asi que sustituir una por otra en vez de anadir es una
    # regresion real -- verificado (id=27510/27503 volvieron a fallar
    # tras el primer intento de sustitucion).
    "PERIODO", "INSCRITA", "INSCRIPC", "SERVLETOPERATION", "ELOPERATION",
    # H30 (S89): sello de cabecera "DD/MM/AAAA Grupo Cooperativo
    # Cajamar" en el formato SEPA 2018-2019 -- fecha de
    # impresion/generacion duplicada, sin relacion con el recibo
    # (verificado real id=27599, id=27612).
    "COOPERATIVO CAJAMAR",
]
_NOISE_SPAN_PATTERNS = [
    # H30 (S89): la palabra "IMPORTE" NO es fiable como ancla -- hay
    # variantes reales distintas para la misma frase de plazo legal
    # de devolucion: "...DEVOLUCION RECIBO: DD/MM/AAAA" (documentos
    # 2010-2013, verificado id=27791/27794/27923/27952/28041/28059) y
    # caracteres sueltos de OCR entre "IMPORTE:" y la fecha en
    # documentos 2018-2019 (verificado id=27596/27599). "DEVOLUCION"
    # es la unica ancla que aparece limpia en todos los casos vistos;
    # se toma la primera fecha que aparezca despues, sin exigir
    # ninguna palabra intermedia concreta.
    re.compile(r"DEVOLUCION[\s\S]{0,200}?(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})"),
    # H31 (S111). Clausula de proteccion de datos "REGLAMENTO (UE)
    # 2016/679 del Parlamento Europeo, de 27 de abril de 2016" -- cita
    # legal fija en TODOS los impresos oficiales de CONTRATO DE
    # TRABAJO del SEPE, sin relacion con la fecha real de firma.
    # Verificado real (ids 27970/34685/36124/36632/37460/40115,
    # ALVAREZ DIAZ ALEJANDRO SERGIO / BARBERO CUENCA MANUEL / IORDACHI
    # PETRU / MUNOZ GONZALEZ ANTONIO JAVIER / RUIZ PORTILLO MANUEL /
    # CRUCES HEREDIA JOSE MANUEL): la fecha real de firma esta tan
    # degradada por el OCR antiguo (previo a la migracion a Cloud
    # Vision de S102) que no se reconoce, y la unica fecha legible que
    # queda es esta cita legal -- capturada por el criterio de "unica
    # fecha, por defecto" (`subject_upload_service.resolve_document_
    # date`), dando 27/04/2016 como issue_date en los 6 casos.
    # Exclusion por POSICION EXACTA (nunca por palabra cercana, como
    # "REGLAMENTO" o "PARLAMENTO" a secas -- ambas demasiado genericas
    # y con riesgo real de regresion, mismo motivo que obligo al
    # cambio de enfoque de "IMPORTE" a posicion exacta en el caso
    # DEVOLUCION de arriba): se ancla a la cadena literal fija
    # "REGLAMENTO (UE) 2016/679", que solo aparece en esta clausula.
    re.compile(
        r"REGLAMENTO \(UE\) 2016/679[\s\S]{0,60}?"
        r"(\d{1,2} DE [A-Z]+ DE \d{4})"
    ),
]
# H30 (S89): fecha de inscripcion registral de Cajamar en el pie de
# pagina, constante en TODOS los recibos ("Inscripc.1a 31/10/2012").
# La palabra "INSCRIPCION" se rompe por OCR de formas demasiado
# dispares para cubrir por lista de palabras clave (verificado real:
# "INSURPUON" en id=27893/27953, sin relacion reconocible con
# "INSCRIPC"). Como es un valor CONOCIDO y CONSTANTE verificado en
# decenas de recibos distintos esta sesion, se excluye por valor
# literal en vez de perseguir mas variantes de rotura de OCR.
_NOISE_LITERAL_DATES = {date(2012, 10, 31)}

_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")
_CONTEXT_WINDOW = 70

# H30 (S78). Fecha en formato largo espanol -- "7 de marzo de 2018",
# "12 de noviembre de 2022", "6 de septiembre del 2014". Miguel Angel,
# hallazgo real de sesion: la mayoria de certificados/comunicaciones
# oficiales (reconocimiento medico, contrato, formacion, carnet de
# gruista...) escriben la fecha asi en el cuerpo del texto, nunca en
# formato numerico -- el patron numerico de arriba nunca las
# reconocia, aunque el documento SI trajera fecha real y legible.
_MESES_LARGO = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
# H30 (sesion de continuidad tras S79). Miguel Angel confirmo con
# documento real (certificado CENTRO MEDICO ALAMEDA) un segundo
# formato real: "10 Enero 2022", SIN la palabra "de" entre dia/mes ni
# entre mes/anio -- el patron anterior exigia "DE"/"DEL" siempre y no
# reconocia esta fecha en absoluto (ni siquiera como fecha suelta sin
# contexto). "DE"/"DEL" pasa a opcional en los dos huecos, cubriendo
# ambos formatos con la misma expresion.
_DATE_LARGO_RE = re.compile(
    r"(\d{1,2})\s+(?:DE\s+)?(" + "|".join(_MESES_LARGO.keys()) + r")\s+(?:DEL?\s+)?(\d\.?\d{3})",
)

# H30 (S78). Impresos oficiales estructurados (IDC, similares) traen
# VARIAS fechas numericas a la vez (periodo, alta, nacimiento...) --
# la regla de "unica fecha del documento" se rompe ahi siempre.
# Miguel Angel, hallazgo real de sesion, ejemplo real (IDC de
# Seguridad Social): "PERIODO: DESDE 24-10-2018." Con etiqueta
# explicita al lado, se coge esa por encima de cualquier otra regla.
#
# Extendido con los patrones reales de CONTRATO (varios formatos
# oficiales distintos, todos verificados con documentos reales
# legibles, S78): "Fecha de Inicio del Contrato: 01/03/2016",
# "Fecha de Transformacion: 24/10/2018" (comunicacion SEPE); "se
# extendera desde 01/03/2016... hasta FIN DE OBRA", "iniciandose la
# relacion laboral en fecha 21/11/2023" (contrato largo, clausulas);
# "desde 11/12/2019, hasta 31/08/2020" (prorroga, sin la palabra
# "extendera"). El separador entre etiqueta y fecha NO siempre es solo
# espacio/dos puntos -- caso real detectado: "Fecha de Inicio del
# Contrato : — 11/09/2019" (guion largo de relleno del propio
# impreso), por eso el hueco se acepta como cualquier caracter que no
# sea digito (`[^\d]{0,15}`), nunca solo `\s*:?\s*`.
# Todos con maxima prioridad -- etiqueta explicita nunca es ambigua.
_GAP = r"[^\d]{0,15}"
_LABELED_DATE_PATTERNS = [
    re.compile(r"PERIODO" + _GAP + r"DESDE" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"FECHA\s+DE\s+INICIO\s+DEL\s+CONTRATO" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"FECHA\s+DE\s+TRANSFORMACION" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"(?:SE\s+)?EXTENDER[AÁ]\s+DESDE" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    re.compile(r"RELACION\s+LABORAL\s+EN\s+FECHA" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    # Prorroga (formato real distinto, sin la palabra "extendera"):
    # "...PRORROGA... DESDE 11/12/2019 ... HASTA 31/08/2020" -- se usa
    # la fecha de inicio de la prorroga (DESDE), mismo criterio que el
    # resto de patrones de este tipo documental. El hueco entre
    # PRORROGA y DESDE SI contiene digitos reales ("8 MESES Y 21
    # DIAS"), a diferencia del resto de patrones -- por eso aqui es
    # "cualquier caracter" (re.DOTALL), no "no digito".
    re.compile(
        r"PRORROGA[\s\S]{0,120}?DESDE" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})",
        re.DOTALL,
    ),
    # H30 (S86, sincronizado aqui en S87 -- esta copia se habia
    # desincronizado de la standalone sin que nadie lo notara, mismo
    # patron de incidente que motivo esta nota en S80). "A FECHA
    # (DD/MM/AAAA)" -- sello real junto a la firma del administrador.
    re.compile(r"A\s+FECHA" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    # H30 (S87): "...es la que se indica a continuacion: DD-MM-AAAA"
    # -- boilerplate real de las resoluciones de Alta/Baja de la
    # Seguridad Social.
    re.compile(r"INDICA\s+A\s+CONTINUACION" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
    # H30 (S87): etiqueta "ALTA:" pegada a la fecha real, formato fijo
    # del impreso "Informe de Datos para la Cotizacion" (IDC) -- ver
    # comentario completo en la copia standalone.
    re.compile(r"AL?TA" + _GAP + r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})"),
]
# Mantiene el nombre antiguo por compatibilidad con codigo que lo
# importe directamente (VM scripts standalone que copian esta logica).
_PERIODO_DESDE_RE = _LABELED_DATE_PATTERNS[0]

# H35 (S107). Fecha real de emision de un IDC (bloque "REFERENCIA(S
# ELECTRONICAS)/FECHA: DD-MM-AAAA/HORA:" -- verificado en las dos
# variantes reales del impreso, "CODIFICACIONES INFORMATICAS" (mas
# antiguo) y "REFERENCIAS ELECTRONICAS" (mas reciente): en ambas,
# "FECHA:" va seguido siempre de "HORA:" justo despues de la fecha,
# ancla suficientemente especifica para no confundirse con ninguna
# otra "FECHA:" del documento. Ver classify_dates_in_text() para el
# porque (PERIODO/DESDE no sirve para este tipo).
_IDC_REFERENCE_DATE_RE = re.compile(
    r"FECHA:\s*(\d{1,2})[-.](\d{1,2})[-.](\d{2,4})\s*HORA:"
)

# H30 (S79). MRZ (zona de lectura por maquina) de DNI/NIE espanol --
# hallazgo real de sesion: cuando la cara frontal es ilegible para
# Tesseract (fondo de seguridad que domina la lectura, mismo problema
# ya documentado arriba para ITV), el MRZ del reverso SI se lee
# limpio casi siempre, y trae la caducidad codificada. Verificado
# contra 4 documentos reales de S79: la fecha de caducidad extraida
# del MRZ coincidio exactamente con la fecha visible en el propio
# nombre de archivo original (evidencia historica, nunca usada como
# fuente de extraccion) en 3 casos, y con la fecha impresa en la cara
# frontal ("EMISION VALIDEZ") en el 4o. Formato TD1, linea 2:
# NACIMIENTO(6)+control(1)+SEXO(1)+CADUCIDAD(6)+control(1)+
# NACIONALIDAD(3). Nunca usa el nombre de archivo -- el MRZ es
# contenido real impreso en el propio documento.
# ---
# MRZ (machine readable zone) of the Spanish DNI/NIE -- real session
# finding: when the front face is unreadable for Tesseract (security
# background dominating the read, same issue already documented above
# for ITV), the MRZ on the back almost always reads cleanly and
# carries the expiry date. Verified against 4 real S79 documents.
# TD1 format, line 2: BIRTH(6)+check(1)+SEX(1)+EXPIRY(6)+check(1)+
# NATIONALITY(3). Never uses the filename -- the MRZ is real content
# printed on the document itself.
_MRZ_LINE2_RE = re.compile(r"(\d{6})(\d)([MF])(\d{6})(\d)([A-Z]{3})")
_MRZ_WEIGHTS = (7, 3, 1)


def _mrz_check_digit(digits):
    """
    Digito de control ICAO 9303 (pesos 7-3-1 ciclicos) sobre una
    cadena de digitos.
    ---
    ICAO 9303 check digit (cyclic 7-3-1 weights) over a digit string.
    """
    total = 0
    for i, ch in enumerate(digits):
        total += int(ch) * _MRZ_WEIGHTS[i % 3]
    return total % 10


def extract_dni_mrz_expiry(text):
    """
    Busca la linea 2 del MRZ del DNI/NIE espanol y devuelve la fecha
    de caducidad SOLO si su propio digito de control ICAO es
    correcto -- evita falsos positivos de OCR. Devuelve None si no
    hay MRZ reconocible o si el digito de control no valida.
    ---
    Looks for MRZ line 2 of the Spanish DNI/NIE and returns the
    expiry date ONLY if its own ICAO check digit is correct -- avoids
    OCR false positives. Returns None if no recognizable MRZ is found
    or the check digit doesn't validate.
    """
    norm = _strip_accents(text).upper()
    for match in _MRZ_LINE2_RE.finditer(norm):
        _, _, _, expiry_digits, expiry_check, _ = match.groups()
        if _mrz_check_digit(expiry_digits) != int(expiry_check):
            continue
        year, month, day = (
            int(expiry_digits[0:2]), int(expiry_digits[2:4]),
            int(expiry_digits[4:6]),
        )
        try:
            return date(2000 + year, month, day)
        except ValueError:
            continue
    return None


# H30 (S83). El mismo match MRZ que valida la caducidad ya trae, en
# los 2 primeros grupos, la fecha de nacimiento con su propio digito
# de control ICAO -- hasta ahora se descartaba con "_, _, _, ...".
# Punto 3 de la hoja de ruta H30 (birth_date para el resto de
# activos): ninguna lectura nueva, el mismo contenido MRZ ya validado.
#
# Ventana de siglo (2 digitos -> 4): nadie de la plantilla puede haber
# nacido despues de hoy, asi que un año AA se resuelve como 20AA si
# AA <= año actual (2 digitos), y como 19AA en caso contrario. Con hoy
# en 2026 (AA=26): 00-26 -> 2000-2026, 27-99 -> 1927-1999. No es una
# ventana fija de por vida -- revisar el corte segun el año real de
# ejecucion (ver `_MRZ_CENTURY_CUTOFF`).
def _mrz_century_cutoff():
    return date.today().year % 100


def extract_dni_mrz_birthdate(text):
    """
    Busca la linea 2 del MRZ del DNI/NIE espanol y devuelve la fecha
    de nacimiento SOLO si su propio digito de control ICAO es
    correcto -- evita falsos positivos de OCR. Devuelve None si no
    hay MRZ reconocible o si el digito de control no valida.
    ---
    Looks for MRZ line 2 of the Spanish DNI/NIE and returns the
    birth date ONLY if its own ICAO check digit is correct -- avoids
    OCR false positives. Returns None if no recognizable MRZ is found
    or the check digit doesn't validate.
    """
    norm = _strip_accents(text).upper()
    cutoff = _mrz_century_cutoff()
    for match in _MRZ_LINE2_RE.finditer(norm):
        birth_digits, birth_check, _, _, _, _ = match.groups()
        if _mrz_check_digit(birth_digits) != int(birth_check):
            continue
        year_2d, month, day = (
            int(birth_digits[0:2]), int(birth_digits[2:4]),
            int(birth_digits[4:6]),
        )
        century = 2000 if year_2d <= cutoff else 1900
        try:
            return date(century + year_2d, month, day)
        except ValueError:
            continue
    return None


# H30 (S79). Cara frontal del DNI/NIE espanol -- etiquetas reales
# EMISION y VALIDEZ, fecha en formato "DD MM AAAA" separada por
# espacios (nunca guion/punto). Verificado contra imagen real del
# documento (28466: "VALIDEZ ... 23 02 2028" == caducidad real
# confirmada visualmente por Miguel Angel). Se usa cuando no hay MRZ
# en el texto cacheado (solo se escaneo la cara frontal).
_DNI_FRONT_LABEL_RE = re.compile(r"(EMISION|VALIDEZ)")
_SPACED_DATE_RE = re.compile(
    r"(\d{1,2})[\s./,;\"'\u2019\u201c\u201d]+"
    r"(\d{1,2})[\s./,;\"'\u2019\u201c\u201d]+(\d{4})"
)
_DNI_FRONT_PLAUSIBLE_YEARS = range(2015, 2046)


def extract_dni_front_expiry(text):
    """
    Caducidad real del DNI/NIE espanol tras EMISION/VALIDEZ. Nunca
    decide cual fecha es la caducidad por posicion/orden de texto --
    si aparecen las dos etiquetas pero el ruido de OCR solo deja leer
    UNA fecha limpia, no se adivina cual es (podria ser la de
    EMISION): se devuelve None. Solo se confia en una unica fecha
    cuando solo aparece la etiqueta VALIDEZ. Entre varias fechas
    validas, se coge la MAS TARDIA -- la caducidad es siempre
    posterior a la emision, nunca al reves.
    ---
    Real expiry of the Spanish DNI/NIE after EMISION/VALIDEZ. Never
    decides which date is the expiry by text position/order -- if
    both labels appear but OCR noise only lets one clean date through,
    it is not guessed (could be the EMISION date): returns None.
    A single date is only trusted when just the VALIDEZ label is
    present. Among several valid dates, the LATEST one is taken --
    expiry is always after issuance, never the reverse.
    """
    norm = _strip_accents(text).upper()
    label_matches = list(_DNI_FRONT_LABEL_RE.finditer(norm))
    if not label_matches:
        return None
    labels_found = {m.group(1) for m in label_matches}
    window = norm[label_matches[0].end():label_matches[0].end() + 100]
    candidatas = []
    for d, m, y in _SPACED_DATE_RE.findall(window):
        year = int(y)
        if year not in _DNI_FRONT_PLAUSIBLE_YEARS:
            continue
        try:
            candidatas.append(date(year, int(m), int(d)))
        except ValueError:
            continue
    if not candidatas:
        return None
    if "EMISION" in labels_found and "VALIDEZ" in labels_found and len(candidatas) < 2:
        return None
    return max(candidatas)


# H30 (sesion de continuidad tras S79). Tarjeta de conductor de
# tacografo digital -- campos armonizados UE 4a (comienzo de validez)
# / 4b (caducidad administrativa), igual que el DNI/NIE frontal, pero
# el OCR de Tesseract destroza casi siempre la etiqueta "4b" (fondo
# de seguridad de la tarjeta) aunque SI deja pasar limpias las dos
# fechas numericas en si. Confirmado contra fuente oficial (Reglamento
# CEE 3821/85 y normativa posterior): la validez de la tarjeta de
# conductor es SIEMPRE de 5 anos exactos, nunca variable -- por eso,
# entre las fechas ya extraidas sin contexto por classify_dates_in_text
# (other_dates), dos que compartan dia y mes y difieran en exactamente
# 5 anos identifican la pareja comienzo/caducidad de la propia tarjeta
# sin depender de leer la etiqueta. Nunca se basa en el nombre de
# archivo -- solo en fechas ya OCR'd del contenido real.
#
# ---
#
# Digital tachograph driver card -- harmonised EU fields 4a (validity
# start) / 4b (administrative expiry), same layout as the Spanish
# DNI/NIE front. Tesseract OCR almost always mangles the "4b" label
# itself (the card's security background) while still reading the two
# raw dates cleanly. Confirmed against an official source (EEC
# Regulation 3821/85 and later rules): driver card validity is ALWAYS
# exactly 5 years, never variable -- so among dates already extracted
# without context by classify_dates_in_text (other_dates), two that
# share day and month and differ by exactly 5 years identify the
# card's own start/expiry pair without needing to read the label.
# Never based on the filename -- only on dates already OCR'd from the
# real content.
def extract_five_year_card_expiry(dates, min_year=2010, max_year=2040):
    """
    Busca, entre `dates` (fechas ya parseadas sin contexto asignado),
    una pareja que comparta dia y mes y difiera en exactamente 5 anos
    -- devuelve la mas tardia (la caducidad) si hay una unica pareja
    asi. Si hay cero o mas de una pareja candidata (ambiguo), devuelve
    None -- nunca adivina entre varias.

    ---

    Looks among `dates` (already-parsed dates with no assigned
    context) for a pair sharing day and month and differing by
    exactly 5 years -- returns the later one (the expiry) if there is
    exactly one such pair. Returns None if there are zero or more than
    one candidate pair (ambiguous) -- never guesses between several.
    """
    candidatas = [d for d in dates if min_year <= d.year <= max_year]
    pares_encontrados = set()
    for i, d1 in enumerate(candidatas):
        for d2 in candidatas[i + 1:]:
            if (
                d1.month == d2.month and d1.day == d2.day
                and abs(d1.year - d2.year) == 5
            ):
                pares_encontrados.add(max(d1, d2))
    if len(pares_encontrados) == 1:
        return pares_encontrados.pop()
    return None


_GEMINI_DATE_SCHEMA = {
    "type": "object",
    "properties": {
        "expiry_date": {"type": "string"},
        "found": {"type": "boolean"},
    },
    "required": ["expiry_date", "found"],
}

_GEMINI_DATE_PROMPT = (
    "Eres un asistente que lee documentos administrativos españoles "
    "de maquinaria/personal (tarjetas ITV, certificados, permisos). "
    "Busca la fecha de CADUCIDAD o VALIDEZ (\"valedera hasta\", "
    "\"fecha de la próxima inspección\") escrita en el documento -- "
    "puede ser manuscrita. Devuelve SOLO la más reciente/última "
    "anotada, en formato AAAA-MM-DD. Si no encuentras ninguna fecha "
    "de caducidad legible, found=false."
)


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _parse_date(day_s, month_s, year_s):
    # H30 (S87): anno impreso con separador de miles espanol ("1.996")
    # -- ver comentario completo en la copia standalone
    # (h28_migration_agent/extract_personal_dates_bulk.py).
    year_s = year_s.replace(".", "") if year_s else year_s
    try:
        day, month, year = int(day_s), int(month_s), int(year_s)
    except ValueError:
        return None
    # H30 (S87): ventana de siglo real para anno de 2 digitos -- ver
    # comentario completo en la copia standalone. Reutiliza el mismo
    # criterio que _mrz_century_cutoff().
    if year < 100:
        year += 2000 if year <= _mrz_century_cutoff() else 1900
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def classify_dates_in_text(text):
    """
    Devuelve (expiry_date o None, issue_date o None, [otras fechas])
    a partir de texto plano -- busca cada fecha (numerica DD/MM/AAAA
    y en formato largo "DD de MES de AAAA") y mira el contexto a
    ambos lados (_CONTEXT_WINDOW caracteres) por palabras de
    caducidad/emision.
    """
    # H30 (S87): normalizar espacios en blanco (incluidos saltos de
    # linea reales del OCR) a un unico espacio ANTES de la comprobacion
    # de contexto -- si no, una etiqueta de dos palabras como "CON
    # FECHA" que el OCR parte justo en el salto de linea ("CON" al
    # final de una linea, "FECHA" al principio de la siguiente) nunca
    # coincide con el "in context" literal, porque el hueco real es un
    # "\n", no un espacio. Incidente real (ALTA, S87): "con | fecha
    # 21/04/2025" (el "|" es solo el separador de impresion de depuracion,
    # el texto real lleva "\n") se marcaba SIN FECHA pese a tener la
    # etiqueta de emision justo al lado.
    norm = _strip_accents(text).upper()
    norm = re.sub(r"\s+", " ", norm)
    # H30 (S91). Misma logica que el fix de saltos de linea de arriba,
    # pero para comas: "En MALAGA, a 16 de JUNIO de 2026" (plantilla
    # real de AUTORIZACION_MEDIOS_COMUNICACION, GRUALDI S.L.) nunca
    # coincidia con el patron ya existente "MALAGA A" porque el texto
    # real lleva una coma entre medias ("MALAGA, A"). Se quita la coma
    # (sustituida por espacio, nunca eliminada sin mas, para no pegar
    # dos palabras) ANTES de la comprobacion de contexto -- igual
    # principio que la normalizacion de saltos de linea: el separador
    # real de impresion no debe romper una coincidencia de dos
    # palabras que en el documento van pegadas por sentido.
    norm = re.sub(r",", " ", norm)
    norm = re.sub(r"\s+", " ", norm)
    expiry_candidates = []
    issue_candidates = []
    other_dates = []

    # H30 (S89): fechas de ruido detectadas por POSICION EXACTA dentro
    # de una frase completa (nunca por cercania de palabra -- ver
    # comentario junto a _NOISE_SPAN_PATTERNS mas arriba, incluye el
    # historial de la regresion real que motivo este enfoque).
    _noise_spans = [
        m.span(1)
        for pattern in _NOISE_SPAN_PATTERNS
        for m in pattern.finditer(norm)
    ]

    def _en_fecha_ruido(match, parsed=None):
        for s, e in _noise_spans:
            if match.start() >= s - 1 and match.end() <= e + 1:
                return True
        if parsed is not None and parsed in _NOISE_LITERAL_DATES:
            return True
        return False

    # H35 (S107), incidente real (pk=35596/35597/35598/35691/42895,
    # Gomez Garcia Jose Antonio, IDC): el patron PERIODO/DESDE de
    # arriba es correcto para CONTRATO (ahi si es la fecha real de
    # inicio del propio contrato) pero incorrecto para IDC -- ahi
    # "PERIODO: DESDE" es el inicio de la relacion laboral, que se
    # repite IDENTICO en cada nueva emision del informe (se puede
    # volver a pedir en cualquier momento para certificar que el
    # trabajador sigue de alta). La fecha real de CADA emision vive en
    # el bloque "REFERENCIA(S ELECTRONICAS)/FECHA: DD-MM-AAAA/HORA:"
    # al final del documento -- unica forma de que el vigente real sea
    # siempre la emision mas reciente (decision explicita de Miguel
    # Angel, S107: "el vigente siempre va a ser el ultimo, el mas
    # moderno"), nunca las 4-5 emisiones distintas empatadas en la
    # misma fecha de inicio de contrato. Se detecta por el propio
    # encabezado real de IDC (misma frase que su CONTENT_SIGNALS en
    # personal_content_classification.py) para no afectar a ningun
    # otro tipo -- comprobado ANTES que _LABELED_DATE_PATTERNS.
    if "INFORME DE DATOS PARA LA COTIZACION" in norm:
        ref_match = _IDC_REFERENCE_DATE_RE.search(norm)
        if ref_match:
            parsed = _parse_date(*ref_match.groups())
            if parsed:
                return None, parsed, []

    # Maxima prioridad: etiqueta explicita (PERIODO/FECHA DE INICIO/
    # SE EXTENDERA DESDE/etc.) -- nunca ambigua, se prueba primero.
    for pattern in _LABELED_DATE_PATTERNS:
        match = pattern.search(norm)
        if match:
            parsed = _parse_date(*match.groups())
            if parsed:
                return None, parsed, []

    matches = list(_DATE_RE.finditer(norm))
    for match in matches:
        parsed = _parse_date(*match.groups())
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + \
            norm[match.end():window_end]
        if any(word in context for word in _BIRTHDATE_CONTEXT):
            continue
        if any(word in context for word in _RECEIPT_NOISE_CONTEXT):
            continue
        if _en_fecha_ruido(match, parsed):
            continue
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    for match in _DATE_LARGO_RE.finditer(norm):
        day_s, mes_s, year_s = match.groups()
        month = _MESES_LARGO.get(mes_s)
        parsed = _parse_date(day_s, month, year_s) if month else None
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + \
            norm[match.end():window_end]
        if any(word in context for word in _BIRTHDATE_CONTEXT):
            continue
        if any(word in context for word in _RECEIPT_NOISE_CONTEXT):
            continue
        if _en_fecha_ruido(match, parsed):
            continue
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    expiry = max(expiry_candidates) if expiry_candidates else None
    issue = min(issue_candidates) if issue_candidates else None
    return expiry, issue, other_dates


_DOCUTEN_SIGNATURE_RE = re.compile(
    r"Fecha y hora:\s*(\d{1,2})-(\d{1,2})-(\d{4})"
)


# H30 (sesion S91). Documentos multi-pagina firmados via Docuten (visto
# en PLAN_ACTUACION_CALOR, boletin nacional de varias decenas de
# paginas de boilerplate identico para todos los empleados) llevan la
# fecha real -- la firma individual de ESE empleado concreto, no la
# fecha de aprobacion del plan nacional que aparece en las primeras
# paginas -- en la ULTIMA pagina del PDF ("Firmado por: NOMBRE...
# Fecha y hora: DD-MM-AAAA HH:MM UTC+N"), fuera del alcance del texto
# embebido/Cloud Vision de las 2 primeras paginas que usa el resto del
# motor. Verificado real: id=40356 (gomez gomez), pagina 54, "Fecha y
# hora: 25-06-2025 17:30 UTC+2". Se OCRea solo la ultima pagina (nunca
# el documento completo -- estos PDFs rondan 10MB/50+ paginas de
# imagenes, procesarlo entero es coste real innecesario) y se busca el
# patron literal de la cabecera de firma de Docuten, nunca el regex
# generico de fecha (evita capturar cualquiera de las decenas de
# fechas de boilerplate que pueda arrastrar la ultima pagina).
def extract_docuten_signature_date(data):
    """
    Devuelve la fecha de la firma electronica individual (bloque
    "Firmado por... Fecha y hora: DD-MM-AAAA") de la ULTIMA pagina de
    un PDF firmado via Docuten, o None si no aparece ese patron
    exacto.

    CENTRALIZADO EN S102 -- NUNCA Tesseract local: la ultima pagina se
    renderiza a PNG y se lee con
    `cloud_vision_service.cloud_vision_image_text()`.
    """
    from document_explorer.cloud_vision_service import (
        cloud_vision_image_text,
    )

    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count == 0:
        doc.close()
        return None
    page = doc.load_page(doc.page_count - 1)
    pix = page.get_pixmap(dpi=300)
    png_bytes = pix.tobytes("png")
    doc.close()

    text = cloud_vision_image_text(png_bytes)
    match = _DOCUTEN_SIGNATURE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def docx_to_text(data):
    """
    H30 (sesion tras S89). Bug real corregido: la version anterior
    solo leia doc.paragraphs, nunca doc.tables -- en documentos con
    formato de tabla (nombre del trabajador, DNI, "A fecha (...)"
    dentro de celdas), el texto real quedaba invisible por completo
    para classify_dates_in_text(). Descubierto en ENTREGA_MANUAL_
    COMBUSTIBLE: 23/23 documentos devolvian el mismo texto generico
    (solo el boilerplate de parrafos, identico en todos), 0 fechas
    encontradas pese a que las 23 SI tenian "A fecha (DD/MM/AAAA)"
    real dentro de una tabla.
    ---
    H30 (session after S89). Real bug fixed: the previous version
    only read doc.paragraphs, never doc.tables -- in table-formatted
    documents (worker name, DNI, "A fecha (...)" inside cells), the
    real text was completely invisible to classify_dates_in_text().
    Discovered in ENTREGA_MANUAL_COMBUSTIBLE: 23/23 documents
    returned the same generic text (only paragraph boilerplate,
    identical across all), 0 dates found despite all 23 having a
    real "A fecha (DD/MM/AAAA)" inside a table.
    """
    import docx
    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def txt_to_text(data):
    """
    H30 (sesion S91). Bug real corregido: extract_text() no
    reconocia .txt en absoluto -- descubierto en CERTIFICADO_BANCARIO,
    donde 4 de 15 documentos pendientes son notas de texto plano
    ("cta bco Apellido.txt") nunca leidas por ningun barrido anterior
    (ocr_text_cacheado=0 para los cuatro). No requiere OCR: se
    decodifica directamente. utf-8 primero (mayoria real de estos
    ficheros); latin-1 como red de seguridad para el resto sin fallar
    nunca por encoding.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def msg_to_text(data):
    """
    H30 (S92). Lectura de correos Outlook .msg -- primer tipo del
    catalogo que los usa (ALTA_MEDICA, partes de baja/alta medica
    recibidos por email, nunca auditado hasta esta sesion). Usa
    extract-msg (verificado por web_search en S92 como libreria
    vigente, https://github.com/TeamMsgExtractor/msg-extractor).
    Incluye asunto y cuerpo -- la fecha real de estos partes suele
    estar en el asunto o en las primeras lineas del cuerpo, nunca en
    metadatos de envio del correo (esos son la fecha de reenvio, no
    la fecha real del parte).
    """
    import extract_msg
    import io as _io
    msg = extract_msg.openMsg(_io.BytesIO(data))
    try:
        parts = []
        if msg.subject:
            parts.append(msg.subject)
        if msg.body:
            parts.append(msg.body)
        return "\n".join(parts)
    finally:
        msg.close()


def extract_text(filename, data):
    """
    Devuelve el texto legible de `data` segun la extension de
    `filename`, o None si la extension no esta soportada (nunca se
    fuerza OCR sobre un tipo de archivo que no se sabe leer).

    CENTRALIZADO EN S102 -- pdf/imagen ya NO usan Tesseract local:
    delegan en `cloud_vision_service.extract_text()` (texto embebido
    del PDF primero, Cloud Vision despues). Decision explicita de
    Miguel Angel, verbatim: "el texto lo tenemos que extraer con
    llamadas a... Cloud Vision, nunca jamas con OCR de PythonAnywhere."
    """
    name_lower = filename.lower()
    if name_lower.endswith((".pdf", ".jpg", ".jpeg", ".png")):
        from document_explorer.cloud_vision_service import (
            extract_text as _cloud_vision_extract_text,
        )
        return _cloud_vision_extract_text(filename, data)
    if name_lower.endswith(".docx"):
        return docx_to_text(data)
    if name_lower.endswith(".txt"):
        return txt_to_text(data)
    if name_lower.endswith(".msg"):
        return msg_to_text(data)
    return None


def extract_expiry_via_gemini(data, filename):
    """
    Ultimo recurso, acotado a document_type.ocr_unreliable=True
    (verificado con datos reales, ver docstring del modulo). Solo pide
    una fecha de caducidad, nunca reclasifica el tipo documental ni
    el sujeto -- eso ya lo sabe el llamador por contexto (viene de la
    ficha del sujeto). Devuelve un `date` o None si Gemini no
    encuentra ninguna fecha legible.
    """
    if filename.lower().endswith(".pdf"):
        part = Part.from_bytes(data=data, mime_type="application/pdf")
    elif filename.lower().endswith((".jpg", ".jpeg", ".png")):
        mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        part = Part.from_bytes(data=data, mime_type=mime)
    else:
        return None

    client = get_gemini_client()
    acquire_gemini_slot()
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=[part, _GEMINI_DATE_PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=90_000),
            response_mime_type="application/json",
            response_schema=_GEMINI_DATE_SCHEMA,
            temperature=0.0,
        ),
    )
    result = json.loads(response.text.strip())
    if not result.get("found"):
        return None
    try:
        year, month, day = (int(x) for x in result["expiry_date"].split("-"))
        return date(year, month, day)
    except (ValueError, KeyError, AttributeError):
        return None
