# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/personal_content_classification.py
"""
H35 (S105). Extraido de `run_personal_retype_and_date.py` (H31-S104)
para que el mismo diccionario CONTENT_SIGNALS/CONTENT_WINS y la misma
logica de resolucion de tipo por contenido las use tambien el agente
H28 standalone (`h28_migration_agent/extract_personal_dates_bulk.py`,
sin Django, corre en las VMs de OCR) -- decision explicita de Miguel
Angel en el anexo H35: "mismo diccionario, evitar mantener dos copias
divergentes".

Modulo deliberadamente SIN dependencias de Django (solo `re` y
`unicodedata` de la libreria estandar) para que sea importable tal
cual desde un script standalone anadiendo la raiz del repo a
`sys.path` -- verificado que `document_explorer/__init__.py` esta
vacio, asi que importar este submodulo nunca dispara el registro de
apps de Django ni requiere `DJANGO_SETTINGS_MODULE`.

El comando Django (`run_personal_retype_and_date.py`) importa de aqui
sin cambio de comportamiento -- este modulo es una extraccion literal,
no una reescritura.
"""
import re
import unicodedata


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


# H31 (S104), corregido tras revisar muestras reales con Miguel Angel:
# "FICHA DE INSCRIPCION" con el numero de horas en el propio titulo del
# curso ("20H PRL...", "6H PRL...") es la senal real y fiable de
# FORMACION (coincide letra a letra con la definicion del propio
# catalogo, "Formacion (2H/6H/60H)") -- nunca "ACCION FORMATIVA"/
# "DIPLOMA" sueltos, que salian igual de bien en documentos de CURSO
# real y producian el ambiguo CURSO/FORMACION visto en el primer lote.
_FORMACION_HOURS_RE = re.compile(r"\b\d{1,3}\s*H\b")

# Frases largas y especificas, confirmadas contra documentos reales
# (nunca palabras sueltas -- ver incidentes "IDESP" y "RECONOCIMIENTO
# MEDICO" en el docstring de run_personal_retype_and_date.py, y el
# hallazgo COMUNICACION_CONTRATO/CONTRATO de H35-S105 mas abajo).
# "IBAN" se retira como senal de CERTIFICADO_BANCARIO (S104, muestra
# real): aparecia como falso positivo en fichas de formacion que solo
# citan un IBAN de pago, nunca en un certificado bancario real -- sin
# sustituto todavia, queda pendiente de una frase mas especifica.
CONTENT_SIGNALS = {
    "TARJETA_SANITARIA": [
        "TARJETA SANITARIA INDIVIDUAL", "NUMERO DE HISTORIA UNICA DE SALUD",
        # H35 (S105), confirmado con muestra real (pk=29196, tarjeta
        # sanitaria formato Junta de Andalucia): "SISTEMA NACIONAL DE
        # SALUD DE ESPANA" + "Tarjeta Sanitaria" -- variante regional
        # sin "INDIVIDUAL" y sin "NUMERO DE HISTORIA UNICA DE SALUD"
        # (esta trae "NUMERO DE HISTORIA DE SALUD DE ANDALUCIA", frase
        # distinta). El nombre de archivo original decia "TARJ.S.
        # SOCIAL", pero el contenido real es sanitaria, no de
        # afiliacion a la Seguridad Social -- otra confirmacion mas de
        # nunca fiarse del nombre de archivo.
        "SISTEMA NACIONAL DE SALUD DE ESPANA",
    ],
    "DNI": ["DOCUMENTO NACIONAL DE IDENTIDAD"],
    "NIE": ["NUMERO DE IDENTIDAD DE EXTRANJERO", "CERTIFICADO DE REGISTRO DE CIUDADANO"],
    "RECONOCIMIENTO_MEDICO": [
        "EXAMEN MEDICO ESPECIFICO", "APTO PARA EL PUESTO", "VIGILANCIA DE LA SALUD",
    ],
    "NOMINA": ["RECIBO DE SALARIOS", "LIQUIDO A PERCIBIR", "PERIODO DE LIQUIDACION"],
    "CONTRATO": ["CONTRATO DE TRABAJO", "DECLARAN QUE REUNEN LOS REQUISITOS"],
    "ALTA": ["RESOLUCION SOBRE RECONOCIMIENTO DE ALTA", "ALTA NORMAL PREVIA"],
    "BAJA_PERSONAL": ["RESOLUCION SOBRE RECONOCIMIENTO DE BAJA"],
    "MOD_145": ["MODELO 145", "COMUNICACION DE DATOS AL PAGADOR"],
    "IDC": ["INFORME DE DATOS PARA LA COTIZACION"],
    "TC2": ["RELACION NOMINAL DE TRABAJADORES", "BOLETIN DE COTIZACION"],
    "VACACIONES": ["PARTE DE VACACIONES", "SOLICITUD DE VACACIONES"],
    "CURSO": [
        "CERTIFICADO DE APROVECHAMIENTO", "DIPLOMA",
        # H35 (S105), confirmado con muestra real (pk=28931,
        # certificado de Fraternidad Muprespa): "CERTIFICA: Que los
        # trabajadores... Han realizado el Curso [nombre]" -- formato
        # de certificacion de un servicio de prevencion externo,
        # distinto de "CERTIFICADO DE APROVECHAMIENTO"/"DIPLOMA".
        "HAN REALIZADO EL CURSO",
    ],
    "FORMACION": ["FICHA DE INSCRIPCION"],
    "CARNET_CONDUCIR": ["PERMISO DE CONDUCCION", "DRIVING LICENCE"],
    "CARNET_GRUISTA": [
        "OPERADOR DE GRUAS MOVILES", "HABILITACION PROFESIONAL",
        "CARNE DE OPERADOR DE GRUAS",
        # H35 (S105), confirmado con 2 muestras reales (pk=30576,
        # 31972 -- certificados de la Delegacion Provincial de
        # Industria, Energia y Minas de la Junta de Andalucia): el
        # documento real dice "GRUA MOVIL" en singular, no "GRUAS
        # MOVILES" en plural -- variante de redaccion no cubierta
        # por el signal existente.
        "OPERADOR DE GRUA MOVIL",
    ],
    "PARTE_BAJA_MEDICA": [
        "PARTE MEDICO DE BAJA", "PARTE MEDICO DE ALTA",
        "PARTE MEDICO DE CONFIRMACION DE INCAPACIDAD",
        "PARTE DE BAJA", "INCAPACIDAD TEMPORAL",
    ],
    "CERTIFICADO_BANCARIO": ["CERTIFICADO DE TITULARIDAD"],
    # ------------------------------------------------------------
    # H35 (S105). Confirmados con muestra real (2 lotes de 20
    # ficheros BAJA_PERSONAL de Jorge Ramirez Garcia, texto embebido
    # + OCR Tesseract espanol) -- ver migraciones 0084/0085 para el
    # alta de catalogo de los 3 codigos que no existian todavia
    # (AUTORIZACION_GENERICA, CAPACITACION, FORMACION_PRL_GENERICA).
    # CAMBIO_IRPF, COMUNICACION_CONTRATO y AUTORIZACION_USO_
    # MAQUINARIA YA existian en el catalogo (migraciones 0004/0045/
    # 0046) pero sin entrada aqui todavia.
    # ------------------------------------------------------------
    "CAPACITACION": [
        "CAPACITACION POR PARTE DE LA EMPRESA DE LAS ACTIVIDADES "
        "QUE PUEDE REALIZAR EL TRABAJADOR",
    ],
    "CAMBIO_IRPF": [
        "SOLICITUD DE TIPO DE RETENCION IRPF SUPERIOR AL CALCULADO "
        "REGLAMENTARIAMENTE",
    ],
    "COMUNICACION_CONTRATO": ["COMUNICACION DEL CONTRATO DE TRABAJO"],
    "AUTORIZACION_USO_MAQUINARIA": [
        "AUTORIZACION DE MANEJO DE MAQUINARIA",
        # H35 (S105), confirmado con muestra real (pk=32725): el OCR
        # real de este documento concreto trae un espacio insertado
        # en medio de la palabra ("MA QUINARIA") -- ruido real del
        # motor, no una redaccion distinta del documento. Variante
        # literal añadida para cubrir este artefacto conocido.
        "AUTORIZACION DE MANEJO DE MA QUINARIA",
    ],
    "INVESTIGACION_ACCIDENTE": [
        # H35 (S105), confirmado con muestra real (pk=37334): "RELACION
        # DE ACCIDENTES DE TRABAJO SIN BAJA" -- formulario Delt@ oficial
        # de declaracion de accidentes de trabajo. Cubre tambien la
        # variante "CON BAJA" al ser solo el prefijo comun.
        "RELACION DE ACCIDENTES DE TRABAJO",
    ],
    "EXPEDIENTE_DISCIPLINARIO": [
        # H35 (S105), confirmado con muestra real (pk=39463): carta de
        # la empresa concediendo "TRAMITE DE AUDIENCIA PREVIA" antes de
        # un despido por faltas graves/muy graves.
        "TRAMITE DE AUDIENCIA PREVIA",
    ],
    "AUTORIZACION_GENERICA": [
        "PARA EL USO DE LOS SIGUIENTES VEHICULOS Y/O MAQUINARIA",
    ],
    "FORMACION_PRL_GENERICA": [
        "HA RECIBIDO FORMACION E INFORMACION, EN CUMPLIMIENTO DE LOS "
        "ARTICULOS 18 Y 19",
    ],
    "RECURSO_PREVENTIVO": ["DESIGNACION DE RECURSO PREVENTIVO"],
    # H35 (S105). TACOGRAFO y TARJETA_CUALIF_CONDUCTOR ya existian en
    # el catalogo (migraciones 0004/0045) pero sin signal todavia --
    # confirmados y diferenciados con muestra real: "TARJETA DE
    # CONDUCTOR" (pk=32835/42316, sin "CUALIFICACION DEL" en medio)
    # es TACOGRAFO; "TARJETA DE CUALIFICACION DEL CONDUCTOR"
    # (pk=32833) es TARJETA_CUALIF_CONDUCTOR -- frases sin solape
    # entre si (la de TACOGRAFO no es substring de la otra).
    "TACOGRAFO": ["TARJETA DE CONDUCTOR"],
    "TARJETA_CUALIF_CONDUCTOR": ["TARJETA DE CUALIFICACION"],
    # H35 (S105). Confirmado con pk=42128/41145 (dos personas
    # distintas, mismo formato Grupo Alvarez) -- "ENTREGA DE EPI'S.
    # FECHA: ...". Sin el apostrofo en la frase de busqueda (su
    # codificacion varia entre recto/tipografico segun el documento
    # y no siempre sobrevive la extraccion de texto).
    "EPIS": ["ENTREGA DE EPI"],
}

# Pares "gana X sobre Y" -- mismo principio que SPECIFIC_WINS de
# heuristic_type_service.py, pero para senales de CONTENIDO. Se aplica
# antes de declarar ambiguo un archivo con mas de una senal.
CONTENT_WINS = [
    ("PARTE_BAJA_MEDICA", "RECONOCIMIENTO_MEDICO"),
    ("PARTE_BAJA_MEDICA", "DNI"),
    ("CARNET_GRUISTA", "DNI"),
    ("CARNET_CONDUCIR", "DNI"),
    ("CONTRATO", "ALTA"),
    # S104, corregido tras revisar muestras: FORMACION (senal
    # estructural, "ficha de inscripcion" + horas en el titulo) gana
    # siempre sobre CURSO (senal generica, "diploma"/"certificado de
    # aprovechamiento") -- un mismo PDF de varias paginas puede traer
    # tambien un cuestionario/examen suelto que dispara CURSO por
    # error, pero la ficha de inscripcion real manda.
    ("FORMACION", "CURSO"),
    # H35 (S105), hallazgo real (pk=32740): la cabecera "COMUNICACION
    # DEL CONTRATO DE TRABAJO..." contiene literalmente la frase
    # "CONTRATO DE TRABAJO", que tambien es senal de CONTRATO --
    # cuando aparece la cabecera de comunicacion, es siempre el
    # documento de comunicacion (mucho mas corto, sin firma de las
    # partes), nunca el contrato en si.
    ("COMUNICACION_CONTRATO", "CONTRATO"),
    # H35 (S105), hallazgo real (pk=27484/27948, formulario oficial de
    # alta de autonomo en el RETA): "RESOLUCION SOBRE RECONOCIMIENTO DE
    # ALTA" es la senal decisiva y especifica de ALTA, pero el mismo
    # formulario estandar de la Tesoreria General de la Seguridad
    # Social siempre trae una clausula de cobertura ("...cobertura de
    # la incapacidad temporal derivada de contingencias comunes...")
    # que dispara el signal generico "INCAPACIDAD TEMPORAL" de
    # PARTE_BAJA_MEDICA -- falso positivo sistematico, no contenido
    # mixto real (a diferencia del caso CONTRATO+PARTE_BAJA_MEDICA
    # visto en BAJA_PERSONAL, que si es mezcla real de dos documentos
    # en el mismo PDF). Cuando aparece la frase especifica de ALTA,
    # gana siempre sobre la señal generica de PARTE_BAJA_MEDICA.
    ("ALTA", "PARTE_BAJA_MEDICA"),
    # H35 (S105), hallazgo real (pk=26289/26291, formulario oficial
    # "Informe de Datos para la Cotizacion"): el propio formulario IDC
    # trae los campos "INICIO CONTRATO DE TRABAJO"/"FIN CONTRATO DE
    # TRABAJO" como etiquetas de casilla (tipo de contrato, fechas),
    # nunca un contrato real incrustado -- dispara el signal generico
    # de CONTRATO ("CONTRATO DE TRABAJO") por simple coincidencia de
    # frase. Confirmado con 2 muestras reales, mismo patron sistematico
    # en las 2 -- IDC (senal especifica y decisiva, "INFORME DE DATOS
    # PARA LA COTIZACION") gana siempre sobre CONTRATO.
    ("IDC", "CONTRATO"),
]

# H31 (S104), hallazgo real: algunos PDF de la migracion historica son
# formularios dinamicos de Adobe (XFA) -- el texto que devuelve
# cualquier extractor (embebido o Cloud Vision sobre el render
# estatico) es solo el aviso generico de "tu lector no soporta este
# documento", nunca el contenido real. Ninguna regla de contenido
# puede resolver esto -- se detecta aparte y se deja fuera del
# retipado/fechado automatico, nunca se cuenta como "sin señal".
ADOBE_DYNAMIC_PLACEHOLDER = "PLEASE WAIT"

# H31 (S104), hallazgo real (pk=40287, VELOSO_SAMPAIO_ESTEVAO): algunos
# PDF tienen la capa de texto interna con el mapa de codificacion roto
# (fuente incrustada sin ToUnicode real) -- el texto extraido sale
# integramente en simbolos/digitos/letras de otros alfabetos sin
# sentido, aunque el PDF se vea perfectamente legible al abrirlo. Se
# detecta por AUSENCIA de palabras españolas comunisimas, no por ratio
# de letras.
_SPANISH_COMMON_WORDS = re.compile(
    r"\b(DE|LA|EL|EN|QUE|LOS|LAS|PARA|CON|POR|UNA?|SE)\b"
)
MIN_LENGTH_FOR_ENCODING_CHECK = 200


def text_encoding_is_broken(text_upper):
    if len(text_upper) < MIN_LENGTH_FOR_ENCODING_CHECK:
        return False
    return not _SPANISH_COMMON_WORDS.search(text_upper)


# H31 (S104), corregido tras revisar muestra real (los 4 CERTIFICADO_
# BANCARIO en .txt): un documento cuyo CONTENIDO REAL es solo un IBAN
# nunca va a llevar el nombre de la persona -- no es un fallo de
# archivo, es que el documento entero mide 28-30 caracteres. El
# chequeo de persona solo tiene sentido a partir de un texto con
# longitud minima razonable para que quepa un nombre en alguna parte.
MIN_LENGTH_FOR_PERSON_CHECK = 80


def resolve_type_from_content(text_upper, current_code):
    """
    Devuelve (code, is_ambiguous, matched_codes). `code` es None si no
    hay ninguna senal o si sigue habiendo mas de una tras aplicar
    CONTENT_WINS -- en ese caso is_ambiguous=True y matched_codes trae
    lo encontrado, para que el dry-run lo muestre y un humano decida.
    Si el unico codigo encontrado coincide con el actual, se devuelve
    igualmente (permite confirmar sin retipar).

    FORMACION (S104): ademas de la senal de frase normal, "FICHA DE
    INSCRIPCION" solo cuenta como FORMACION si el propio texto trae
    tambien un patron de horas en el titulo del curso (r"\\d+H") --
    confirmado contra muestras reales que esa combinacion es la que
    de verdad distingue FORMACION de CURSO, nunca la frase sola.

    H35 (S105), hallazgo real (pk=30353, CAPACITACION): el texto OCR
    trae saltos de linea/espacios multiples exactamente donde una
    frase de CONTENT_SIGNALS tiene un espacio simple ("...ACTIVIDADES"
    seguido de salto de linea, luego "QUE PUEDE...") -- una frase
    escrita como una sola linea en el diccionario nunca haria match
    contra ese texto real aunque un humano la reconozca al instante.
    Se normaliza aqui, en el unico punto donde se comparan frases
    contra texto real, cualquier secuencia de espacios en blanco
    (saltos de linea incluidos) a un espacio simple -- nunca se toca
    `text_upper` fuera de esta funcion, para no afectar otras
    comparaciones (MRZ, deteccion de codificacion rota) que si
    dependen de la estructura real del texto.
    """
    normalized = re.sub(r"\s+", " ", text_upper)
    matched = set()
    for code, phrases in CONTENT_SIGNALS.items():
        for phrase in phrases:
            if phrase in normalized:
                matched.add(code)
                break
    if "FORMACION" in matched and not _FORMACION_HOURS_RE.search(normalized):
        matched.discard("FORMACION")
    for winner, loser in CONTENT_WINS:
        if winner in matched and loser in matched:
            matched.discard(loser)
    if len(matched) == 1:
        return next(iter(matched)), False, matched
    if len(matched) > 1:
        return None, True, matched
    return None, False, matched


def person_name_missing(text_upper, person):
    """
    H31 (S104), hallazgo real de esta sesion (pk=25140 -- un contrato
    de prestacion de servicios con una academia externa, archivado
    bajo una persona cuyo nombre no aparecia en ninguna parte del
    documento). Senal de aviso, nunca de retipado automatico: si ni el
    primer apellido ni el segundo (cuando existe) aparecen en el texto
    extraido, es posible que el documento este archivado bajo la
    persona equivocada -- se marca para revision manual, nunca se
    reasigna solo.

    CORREGIDO EN LA MISMA SESION: coincidencia exacta de substring
    daba demasiados falsos positivos reales (el apellido SI estaba en
    el documento, pero el OCR lo devolvio tan degradado -- "ADQLFO
    PlvAREZ DI=" en vez de "ADOLFO ALVAREZ DIAZ" -- que ninguna
    comparacion exacta lo reconocia). Ahora se acepta tambien una
    coincidencia aproximada (SequenceMatcher, ratio>=0.72) contra
    cualquier palabra suficientemente larga (>=4 caracteres) del
    texto, mismo umbral de tolerancia a ruido de OCR.

    `person` debe exponer `.first_surname` y `.second_surname`
    (cadenas, `second_surname` puede ser vacia).
    """
    import difflib

    surnames = [s for s in (person.first_surname, person.second_surname) if s]
    if not surnames:
        return False
    norm_surnames = [_strip_accents(s).upper() for s in surnames]
    if any(s in text_upper for s in norm_surnames if s):
        return False
    words = [w for w in re.split(r"[^A-Z]+", text_upper) if len(w) >= 4]
    for surname in norm_surnames:
        for word in words:
            if difflib.SequenceMatcher(None, surname, word).ratio() >= 0.72:
                return False
    return True
