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
        # H35 (S107), confirmado con 12+ muestras reales (formato MPE,
        # Medios de Prevencion Externos Sur S.L., el proveedor de PRL
        # mas usado de toda la plataforma): "CERTIFICA: Que el
        # trabajador [NOMBRE] y DNI [numero], perteneciente a la
        # empresa [EMPRESA]... ha sido sometido el dia [fecha]... a
        # reconocimiento medico [periodico/inicial]...". Frase ancla
        # sin el nombre/fecha variables, que es lo unico estable entre
        # las decenas de variantes reales encontradas.
        "HA SIDO SOMETIDO EL DIA", "RECONOCIMIENTO MEDICO PERIODICO",
        "RECONOCIMIENTO MEDICO INICIAL",
        # H35 (S108), cierre de los 25 IDs "sin senal" de RECONOCIMIENTO_
        # MEDICO listados en la hoja de ruta de S107. Confirmado contra
        # el texto OCR real de cada muestra, nunca de memoria.
        # Formato CRC (pk=24883/24884, aptitud grua movil):
        "RECONOCIMIENTO FACULTATIVO DE COMPROBACION DE APTITUDES FISICAS Y PSICOLOGICAS",
        # Formato "Las Carmelitas" (pk=40914/42791/42793/42794,
        # renovacion carnet operador grua torre):
        "RECONOCIMIENTO FACULTATIVO PERTINENTE DE COMPROBACION DE LA CAPACIDAD FISICA Y LA APTITUD PSICOLOGICA",
        # Notificacion Fraternidad Muprespa (12 muestras reales:
        # pk=28937/35686/42752/42756/42765/42774/42779/42780/42782/
        # 42783/42787/42789) -- notificacion de que el reconocimiento
        # ya se realizo, informe de aptitud aun pendiente:
        "NOTIFICACION DE LA REALIZACION DE RECONOCIMIENTO MEDICO",
        # Informe "EXAMEN DE SALUD" formato ANP (pk=33934) -- se usa
        # esta frase de cuerpo del informe, mas especifica que "EXAMEN
        # DE SALUD" suelto (evita falso positivo con otros documentos
        # que solo mencionen un examen de salud de pasada):
        "ANAMNESIS Y ANTECEDENTES CLINICO-LABORALES",
        # Cabecera "Reconocimiento Medico Laboral" formato Grupo MPE
        # (pk=37408):
        "RECONOCIMIENTO MEDICO LABORAL",
        # H35 (S108), tercera plantilla real confirmada por inspeccion
        # VISUAL (no de OCR -- Tesseract fallaba con gibberish por el
        # fondo de seguridad tipo guilloche del papel oficial) de
        # pk=40898/40953: "CERTIFICADO MEDICO OFICIAL" del Consejo
        # General de Colegios Oficiales de Medicos de España,
        # certificando aptitud para operador de grua movil. ocr_text
        # de ambos regenerado a mano con la transcripcion real tras la
        # lectura visual -- ver Comando S de la sesion.
        "SIENDO APTO PARA ACTUAR COMO OPERADOR DE GRUA",
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
    # H36 (S109/S110). Tipos de curso sembrados en migracion 0097 con
    # evidencia real ya confirmada en muestra de contenido -- los
    # restantes quedan pendientes de muestra real todavia, nunca se
    # anaden sin ella.
    "FORMACION_PRL_ART_18_19": [
        # Confirmado con muestra real amplia (pk=24409/24410/24427/
        # 24428/24429/24430/24432/24433, varios trabajadores de GRUAS
        # ADOLFO ALVAREZ y TRANSGRUAL): carta real de M.P.E. Servicio
        # de Prevencion de Riesgos Laborales, frase estable de cierre
        # del parrafo, presente en todas las muestras.
        "EN CUMPLIMIENTO DE LOS ARTICULOS 18 Y 19",
        # H36 (S110), confirmado con muestra real (pk=24361, ANP
        # Servicio de Prevencion Ajeno S.L., autorizacion SP-51/00):
        # otro proveedor, mismo fin legal (art. 19 Ley 31/1995), titulo
        # propio "CERTIFICADO FORMACION EN MATERIA DE PRL".
        "CERTIFICADO FORMACION EN MATERIA DE PRL",
        # H36 (S110), confirmado con muestra real (pk=34131, ASPREMA/
        # PREVEM Servicio de Prevencion Ajeno S.L., ciclo "aula
        # permanente" del Convenio General del Sector de la
        # Construccion): mismo fin legal, titulo propio "CERTIFICADO
        # DE FORMACION DE SEGURIDAD Y SALUD EN CONSTRUCCION".
        "CERTIFICADO DE FORMACION DE SEGURIDAD Y SALUD EN CONSTRUCCION",
    ],
    "FORMACION_PLATAFORMA_ELEVADORA": [
        # Confirmado con muestra real (pk=24267,
        # ALVAREZ_DIAZ_ADOLFO_FORMACION_20140715): certificado real de
        # HAULOTTE IBERICA (fabricante de plataformas elevadoras),
        # formacion de formadores segun norma UNE58923 de categorias
        # de plataforma. Nombre del fabricante como ancla, mismo
        # criterio que HAULOTTE/ANP/ANAGRUAL en otras entradas de este
        # diccionario.
        "HAULOTTE IBERICA", "NORMA UNE58923",
        # H36 (S110), confirmado con muestra real (pk=34328/34329/
        # 34330/34331, Fundacion Estatal para la Formacion en el
        # Empleo, ENRIQUE ALVAREZ SERRANO, 13/04/2024): diploma
        # acreditativo real, titulo exacto "PLATAFORMAS ELEVADORAS
        # MOVILES".
        "PLATAFORMAS ELEVADORAS MOVILES",
    ],
    "FORMACION_OPERADOR_CAMION_AUTOCARGANTE": [
        # H36 (S110), confirmado con muestra real (pk=34055/34777,
        # certificado Ceunes Formacion, MANUEL ALONSO PEDROSA/MANUEL
        # BURGOS FERNANDEZ): curso presencial de 6 horas, titulo exacto
        # "Camion grua autocargante" en ambas muestras.
        "CAMION GRUA AUTOCARGANTE",
        # H36 (S110), confirmado con muestra real (pk=36406, plantilla
        # M.P.E., JOSE CARLOS MARTINEZ SEGURA, "TRABAJOS CON GRUA
        # AUTOCARGANTE"): variante corta de PRL informativa sobre el
        # mismo equipo, mismo tipo.
        "GRUA AUTOCARGANTE",
    ],
    "FORMACION_PRIMEROS_AUXILIOS": [
        # H36 (S110), confirmado con muestra real (pk=34774/34780,
        # certificado Ceunes Formacion, MANUEL BURGOS FERNANDEZ): curso
        # presencial de 4 horas, titulo exacto "Primeros Auxilios" en
        # ambas muestras.
        "PRIMEROS AUXILIOS",
    ],
    "FORMACION_SUBESTACIONES": [
        # H36 (S110), confirmado con muestra real (pk=34776/34778,
        # certificado Ceunes Formacion, MANUEL BURGOS FERNANDEZ): curso
        # presencial de 6 horas, titulo exacto "Subestaciones y centros
        # de distribucion" en ambas muestras.
        "SUBESTACIONES Y CENTROS DE DISTRIBUCION",
    ],
    "FORMACION_EXTINCION_INCENDIOS": [
        # H36 (S110), confirmado con muestra real amplia (pk=25757,
        # 34954/35097/35296 -- certificado GWO BST "Fire Awareness",
        # 35096/35295 -- Ceunes Formacion "Extincion de incendios y
        # emergencias"): frase estable presente en todas las variantes
        # tras strip de acentos. pk=25757 es un curso mixto real
        # ("Primeros Auxilios Y Extincion de Incendios") -- queda
        # correctamente ambiguo al coincidir tambien con la senal de
        # FORMACION_PRIMEROS_AUXILIOS, decision humana pendiente, nunca
        # asignado en automatico a ninguna de las dos.
        "EXTINCION DE INCENDIOS",
    ],
    "FORMACION_TRABAJOS_ALTURA": [
        # H36 (S110), confirmado con muestra real amplia (pk=34970/
        # 35117/35211/40171, certificado EPICENTER MALAGA S.L.): frase
        # de cabecera estable, formato repetido letra a letra en las 4
        # muestras ("... HA REALIZADO EL CURSO DE SEGURIDAD EN TRABAJOS
        # EN ALTURA (8 HORAS PRESENCIALES)...").
        "SEGURIDAD EN TRABAJOS EN ALTURA",
        # H36 (S110), corregido tras colision real: "TRABAJOS EN
        # ALTURA" suelto (sin "SEGURIDAD EN") aparece tambien como
        # simple punto de temario en certificados de otros cursos
        # (confirmado real: certificado de Electricidad de Iluro,
        # pk=27743, lista "Trabajos en altura." entre sus contenidos
        # tecnicos) -- nunca usar la frase suelta. Variante real de
        # Ceunes Formacion (pk=35300) que si es titulo de curso real,
        # identificada por el contexto estable que la acompaña siempre
        # en su plantilla ("...en Trabajos en altura / Codigo Accion
        # Formativa:").
        "TRABAJOS EN ALTURA CODIGO ACCION FORMATIVA",
    ],
    "FORMACION_PRL_60H": [
        # H36 (S110), confirmado con muestra real (pk=25096, ficha de
        # inscripcion "CURSO: 60H NIVEL BASICO PRL"; pk=25519, "60 H
        # NIVEL BASICO PRL"). Deliberadamente exige el digito "60"
        # pegado a "NIVEL BASICO PRL" -- muestra real en el mismo lote
        # (variante "20H NIVEL BASICO PRL") confirma que existen cursos
        # de nivel basico PRL de otra duracion que NO son este tipo,
        # nunca usar "NIVEL BASICO PRL" suelto como senal.
        "60H NIVEL BASICO PRL", "60 H NIVEL BASICO PRL",
        # H36 (S110), confirmado con muestra real (pk=25220, ficha de
        # inscripcion ILURO, "Titulo del curso: 60H NIVEL BASICO
        # PREVENCION PRL"): variante de orden real, mismo digito 60
        # exigido junto a la palabra clave.
        "60H NIVEL BASICO PREVENCION PRL",
        # H36 (S110), confirmado con muestra real amplia (pk=24467 y
        # ~11 mas, Centro Liber Formacion, 50 horas; pk=25192,
        # Fundacion Laboral de la Construccion, 60h): mismo curso
        # real de nivel basico PRL con nombres/duraciones distintos al
        # patron "NIVEL BASICO PRL" ya cubierto -- sin conflicto de
        # duracion conocido para estas dos redacciones concretas.
        "PREVENCION DE RIESGOS LABORALES BASICO",
        "NIVEL BASICO DE PREVENCION EN CONSTRUCCION",
        # H36 (S110), corregido tras muestra real (pk=27906, MAUDE
        # STUDIO, ALBERTO ALVAREZ DIAZ): variante real con articulo
        # "EN LA CONSTRUCCION", no cubierta por la frase sin "LA".
        "NIVEL BASICO DE PREVENCION EN LA CONSTRUCCION",
    ],
    "FORMACION_OPERADOR_APARATOS_ELEVACION": [
        # H36 (S110), confirmado con muestra real (pk=25368/25732,
        # ficha de inscripcion ILURO DE PREVENCION SL, titulo de curso
        # "... OPERADOR DE APARATOS ELEVADORES)"; pk=34793, certificado
        # MAUDE STUDIO, "acción formativa Operador de aparatos
        # elevadores"). Frase con orden estable en las 3 muestras tras
        # normalizar espacios/saltos de linea.
        "OPERADOR DE APARATOS ELEVADORES",
        # H36 (S110), tercer lote: variante en plural confirmada con
        # muestra real (pk=25060, "PRL PARA OPERADORES DE APARATOS
        # ELEVADORES"; pk=36454, "Operadores de aparatos elevadores")
        # -- singular y plural no son intercambiables por substring,
        # necesitan su propia frase.
        "OPERADORES DE APARATOS ELEVADORES",
        # H36 (S110), cuarto lote: fichas de inscripcion reales
        # abreviadas (pk=25316/25317/25333, "6H PRL OP.APARATOS
        # ELEVADORES"/"6H OP.APART.ELEVADORES"/"6H PRL OP APARATOS
        # ELEVADORES") -- demasiadas grafias de puntuacion distintas
        # para listarlas todas; se usa el fragmento estable comun
        # "APARATOS ELEVADORES" solo, seguro porque no colisiona con
        # ninguna otra senal de esta lista.
        "APARATOS ELEVADORES",
        # H36 (S110), confirmado con muestra real amplia (~10 pk,
        # plantilla TVGV Formacion): grafia real con error de imprenta
        # estable en la plantilla, "APARATOS ELEVADORAS" (con A final,
        # no E) -- no es ruido de OCR de una sola muestra, se repite
        # igual en todas las certificaciones de este mismo proveedor.
        "APARATOS ELEVADORAS",
    ],
    "FORMACION_CARRETILLAS_TRASPALETAS": [
        # H36 (S110), confirmado con muestra real (pk=40094/40095/
        # 40003, certificado Ceunes Formacion, PABLO CAÑAMERO NAVARRO):
        # curso presencial de 6 horas, titulo exacto "Operador de
        # carretilla elevadora" en las 3 muestras.
        "OPERADOR DE CARRETILLA ELEVADORA",
        # H36 (S110), tercer lote: variante en plural confirmada con
        # muestra real (pk=36010, BASILIO MUÑOZ CRUZ S.L.U., "OPERADOR
        # DE CARRETILLAS ELEVADORAS").
        "OPERADOR DE CARRETILLAS ELEVADORAS",
        # H36 (S110), confirmado con muestra real (pk=27980, TVGV
        # Formacion/Taga Formacion S.L., ALEJANDRO SERGIO ALVAREZ DIAZ,
        # "MANEJO SEGURO DE CARRETILLAS ELEVADORAS Y TRASPALETAS").
        "MANEJO SEGURO DE CARRETILLAS ELEVADORAS",
    ],
    "FORMACION_ELECTRICIDAD": [
        # H36 (S110), confirmado con muestra real subida por Miguel
        # Angel (diploma Fundacion Laboral de la Construccion,
        # ENRIQUE ALVAREZ SERRANO, NIF 30976093S, 23/07/2022, 6 horas):
        # titulo exacto "PRL PARA TRABAJOS DE ELECTRICIDAD, MONTAJE Y
        # MANTENIMIENTO DE INSTALACIONES ELECTRICAS DE ALTA Y BAJA
        # TENSION. PARTE ESPECIFICA". Confirma ademas columna propia
        # "ELECTRICIDAD 4H O 6H" en el Excel real de Yolanda (RRHH),
        # curso 15 del catalogo, ya sembrado en 0097 pero sin senal
        # hasta ahora. Frase acortada a la parte estable, sin la
        # duracion (4H/6H varia segun la muestra).
        "PRL PARA TRABAJOS DE ELECTRICIDAD",
        # H36 (S110), confirmado con muestra real (pk=35100, Iluro
        # Prevencion S.L./Fundacion del Metal, ANTONIO JESUS DIAZ
        # QUINTERO, curso "Electricidad: montaje y mantenimiento de
        # instalaciones electricas de alta y baja tension"): variante
        # de otro proveedor, mismo fragmento estable central.
        "MONTAJE Y MANTENIMIENTO DE INSTALACIONES ELECTRICAS",
    ],
    "FORMACION_OPERADOR_MINIGRUA": [
        # H36 (S110), confirmado con muestra real subida por Miguel
        # Angel (certificado GRUAS ADOLFO ALVAREZ, LEANDRO JAVIER
        # ALVAREZ VIEIRA, DNI 77233157P, 8 de mayo de 2019 -- fecha
        # que cuadra exacta con la columna "OPERAD.MINI GRUA" del
        # Excel real de Yolanda para esta misma persona): 2 horas,
        # titulo exacto "OPERADOR DE MINI GRUA DE ORUGA". Frase
        # acortada a "OPERADOR DE MINI GRUA" por si existe variante sin
        # "DE ORUGA" (otro tipo de minigrua) en otras muestras.
        "OPERADOR DE MINI GRUA",
    ],
    "FORMACION_GRUAS_ASISTENCIA_CARRETERA": [
        # H36 (S110), confirmado con muestra real subida por Miguel
        # Angel (certificado M.P.E. Servicio de Prevencion, CARLOS M.
        # CARLIN CARVAJAL, DNI 74879491R, Malaga 30/09/2015 -- fecha
        # que cuadra exacta con la columna "GRUAS ASIST.CARRETERA" del
        # Excel real de Yolanda para esta misma persona): titulo
        # exacto "TRABAJOS CON GRUA DE ASISTENCIA EN CARRETERA".
        "GRUA DE ASISTENCIA EN CARRETERA",
    ],
    "FORMACION_GRUA_HIDRAULICA_ARTICULADA": [
        # H36 (S110), confirmado con muestra real subida por Miguel
        # Angel (certificado ANAGRUAL, ANTONIO JESUS DIAZ QUINTERO, DNI
        # 33390084H, Madrid 20/10/2022 -- fecha que cuadra exacta con
        # la columna "OPER.GRUA HIDRAUL.ARTIC." del Excel real de
        # Yolanda para esta misma persona): titulo exacto "CERTIFICADO
        # DE OPERADOR DE GRUA HIDRAULICA ARTICULADA - UNE 58161:2021".
        "GRUA HIDRAULICA ARTICULADA",
    ],
    "FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA": [
        # H36 (S110), confirmado con muestra real (pk=34124, ALBERTO
        # A. ALVAREZ GEA, M.P.E., Malaga 06/11/2015; pk=36061, GABRIEL
        # ALEJANDRO HIDALGO ROSAS, M.P.E., Malaga 23/10/2017 -- este
        # ultimo en carpeta OBSOLETOS): mismo molde M.P.E. que
        # FORMACION_GRUAS_ASISTENCIA_CARRETERA, titulo exacto
        # "TRABAJOS CON GRUA MOVIL AUTOPROPULSADA".
        "GRUA MOVIL AUTOPROPULSADA",
    ],
    "FORMACION_GWO_SEGURIDAD_EOLICA": [
        # H36 (S110), confirmado con muestra real amplia (~15 pk,
        # WINDA Delegate Training Certificate, SGS TECNOS S.A.):
        # frase estable en todos los modulos (Fire Awareness, Working
        # at Height, First Aid, Manual Handling, Sea Survival),
        # cabecera identica en todos.
        "GLOBAL WIND ORGANISATION", "WINDA DELEGATE TRAINING CERTIFICATE",
    ],
    "FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA": [
        # H36 (S110), confirmado con muestra real amplia (~10 pk,
        # formacionavsec.com y avsecformacion.es): titulo estable en
        # ambos proveedores reales.
        "CERTIFICADO DE FORMACION AVSEC",
        "CONCIENCIACION DE SEGURIDAD AEROPORTUARIA",
        "CONCIENCIACION EN SEGURIDAD AEROPORTUARIA",
    ],
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
        # H36 (S110), confirmado con muestra real amplia (~19 pk,
        # plantilla real Junta de Andalucia/Delegacion Territorial de
        # Conocimiento y Empleo: "inscrito en el Registro de
        # OPERADORES de Gruas Moviles de esta provincia"): variante en
        # plural real, distinta de "OPERADOR DE GRUAS MOVILES" (que
        # exige singular pegado a plural) -- no colisiona con ella.
        "OPERADORES DE GRUAS MOVILES",
    ],
    # H35 (S107), corregido tras falso positivo real (pk=35635/35637/
    # 35639/35640/35641/35684, contratos Mod. PE-177A de Gomez
    # Garcia): "INCAPACIDAD TEMPORAL" sola aparecia como clausula
    # boilerplate estandar de CUALQUIER contrato de este modelo
    # ("...trabajadores con discapacidad que tengan suspendido su
    # contrato por incapacidad temporal..."), marcando como ambiguos
    # 6 contratos reales sin ningun parte de baja mezclado. Retirada
    # como frase suelta -- las otras 4 frases ya son especificas de
    # cabecera real de un parte medico, nunca boilerplate legal.
    "PARTE_BAJA_MEDICA": [
        "PARTE MEDICO DE BAJA", "PARTE MEDICO DE ALTA",
        "PARTE MEDICO DE CONFIRMACION DE INCAPACIDAD",
        "PARTE DE BAJA",
    ],
    "CERTIFICADO_BANCARIO": ["CERTIFICADO DE TITULARIDAD"],
    # H35 (S108). Confirmados con muestra real durante el cierre de los
    # 25 IDs "sin senal" de RECONOCIMIENTO_MEDICO -- decision explicita
    # de Miguel Angel de retipar en vez de forzarlos como reconocimiento
    # medico (ver migracion 0093 para el alta de catalogo de ambos
    # codigos).
    "FACTURA_SERVICIOS_PERSONAL": [
        # pk=28456 (Medios de Prevencion Externos Sur S.L., factura de
        # "VS GESTION CUPO"): frase de pie de factura, estable entre
        # las facturas reales de este mismo proveedor.
        "SOLICITE CITA PARA RECONOCIMIENTOS MEDICOS AL TELEFONO",
        # H36 (S109), confirmado con muestra real (pk=24307/24308,
        # ALVAREZ_GEA_ALBERTO_ADOLFO; pk=24309, ZAFRA_PERALTA_JOSE_
        # ANTONIO): facturas reales de "Informa Consultoria y
        # Formacion S.L." por servicios de formacion, archivadas hoy
        # bajo el tipo generico FORMACION -- el nombre del proveedor
        # en la propia cabecera de la factura es la senal estable.
        "INFORMA CONSULTORIA Y FORMACION",
        # H36 (S109), confirmado con muestra real (pk=24286,
        # CASTILLA_NAVARRO_FRANCISCO_MIGUEL): albaran/factura real de
        # "Facilauto Consulting S.L." -- mismo patron, otro proveedor.
        "FACILAUTO CONSULTING",
    ],
    "CITACION_RECONOCIMIENTO_MEDICO": [
        # pk=35241: carta de cita de Fraternidad Muprespa, distinta de
        # la notificacion de realizacion ya cubierta por
        # RECONOCIMIENTO_MEDICO -- aqui el reconocimiento todavia no se
        # ha hecho, solo se está citando a la persona.
        "ESTA CITADO EN NUESTRO CENTRO MEDICO",
    ],
    # H36 (S109). Confirmados con muestra real durante la primera
    # muestra de contenido de FORMACION generico de trabajadores
    # activos -- mismo patron de "cajon de sastre" que motivo H35 con
    # BAJA_PERSONAL, a menor escala (ver migracion 0098 para el alta
    # de catalogo de los 3 codigos).
    "CUESTIONARIO_FORMACION": [
        # pk=24414/24415/24419/24422/24424 (varios trabajadores):
        # cuestionario real de evaluacion de la formacion COVID-19,
        # nunca un certificado de curso tecnico.
        "CUESTIONARIO COVID-19",
        # H36 (S110), confirmado con muestra real amplia (multiples
        # pk, plantilla M.P.E. "CUESTIONARIO DE EVALUACION" en varias
        # variantes: oficinas, talleres de automocion, vigilante/
        # auxiliar, instalaciones de alta tension): examen real de la
        # formacion, nunca el certificado del curso en si.
        "CUESTIONARIO DE EVALUACION",
    ],
    "PACTO_PERMANENCIA": [
        # pk=24670/24671 (CASTILLA_NAVARRO_FRANCISCO_MIGUEL): pacto de
        # permanencia real ligado a una formacion bonificada, nunca el
        # certificado del curso en si.
        "PACTO DE PERMANENCIA",
    ],
    "JUSTIFICANTE_PAGO_PERSONAL": [
        # pk=24296 (RAMIREZ_GARCIA_JORGE): justificante de
        # transferencia bancaria real (Cajamar), nunca un certificado
        # de curso. "DETALE DE LA OPERACION" es el artefacto real de
        # OCR de esta muestra concreta (falta una L) -- se anade
        # tambien la grafia correcta por si otra muestra real la trae
        # sin ese artefacto.
        "DETALLE DE LA OPERACION", "DETALE DE LA OPERACION",
        # H36 (S110), confirmado con muestra real amplia (multiples
        # pk, plantillas CaixaBank y otro banco no identificado):
        # justificantes de transferencia bancaria reales para pagar
        # cursos/servicios, nunca certificados. Frases estables de
        # cabecera de justificante bancario.
        "JUSTIFICANTE DE OPERACION", "OPERACION REALIZADA CORRECTAMENTE",
        # H36 (S110), cuarto lote: variante real Santander
        # ("Justificante provisional de transferencia").
        "JUSTIFICANTE PROVISIONAL DE TRANSFERENCIA",
    ],
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
        # H35 (S108), cierre de los 71 IDs "sin senal" (excluido
        # pk=26847, deuda tecnica 4.21) de la hoja de ruta de S107.
        # Confirmadas contra el texto real de cada muestra:
        # Formulario oficial Delt@ "PARTE DE ACCIDENTE DE TRABAJO"
        # (18 muestras reales: pk=26342/26345/26352/26355/26422/26436/
        # 26518/26524/26526/26544/26549/26714/26751/26834/26848/26851/
        # 26978/26982):
        "PARTE DE ACCIDENTE DE TRABAJO",
        # Formulario interno "REGISTRO DE ACCIDENTES" de la empresa,
        # manuscrito/OCR muy degradado en casi todas las muestras pero
        # con esta etiqueta de formulario siempre presente (13 muestras
        # reales: pk=26337/26433/26514/26523/26525/26538/26551/26565/
        # 26600/26749/27019/27154/27201):
        "QUE/COMO OCURRIO",
        # Informe real de investigacion (formato MPE/anp -- 9 muestras
        # reales: pk=26434/26566/26567/26568/26750/26976/27009/27169/
        # 35788):
        "INFORME DE INVESTIGACION DE ACCIDENTE",
        # Carta de reclamacion de documentacion de un accidente concreto
        # a la mutua (pk=27103):
        "PARTE ACCIDENTE LABORAL DE SU TRABAJADOR",
        # Correspondencia real de la aseguradora de RC de la empresa
        # sobre un siniestro/accidente concreto de un trabajador
        # (distinto del caso pk=26847 de la deuda tecnica 4.21, que es
        # una poliza de empresa sin accidente concreto asociado --
        # aqui si hay una fecha de ocurrencia y un trabajador real
        # ligados al siniestro, pk=26845):
        "CENTRO OPERATIVO DE SINIESTROS",
        # Parte de asistencia sanitaria sin baja tras un accidente
        # laboral real (Fraternidad Muprespa, pk=27158) -- distinto de
        # PARTE_BAJA_MEDICA (esa es cuando SI hay incapacidad temporal
        # real, esta es justo la constancia de que NO la hubo):
        "SE HA PRESTADO ASISTENCIA SANITARIA SIN BAJA MEDICA",
    ],
    # H35 (S108). Confirmado con 14 muestras reales durante el cierre
    # del punto 2 de INVESTIGACION_ACCIDENTE (ver migracion 0094 para
    # el alta de catalogo) -- ninguna de las dos plantillas reales es
    # una investigacion de accidente, ambas son constancia de
    # informacion PRL recibida de un tercero (cliente/obra).
    "INFORMACION_RIESGOS_PRL_TERCEROS": [
        # Certificado Endesa (10 muestras: pk=27031/27032/27037/27038/
        # 27039/27040/27047/27048/27049/27050):
        "CERTIFICADO DE INFORMACION DE LOS RIESGOS DE LAS INSTALACIONES",
        # Entrega de Plan de Seguridad y Salud de obra F.C.C. (4
        # muestras: pk=27068/27078/27082/27087):
        "COPIA DEL PLAN DE SEGURIDAD Y SALUD",
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
        # H36 (S110). Senal retirada -- confirmado con el Excel real de
        # Yolanda (RRHH), columna propia "ART.18 Y 19 PRL" sin ninguna
        # columna "generica" aparte: es el mismo curso real que
        # FORMACION_PRL_ART_18_19, nunca dos tipos distintos. La frase
        # que tenia aqui ("HA RECIBIDO FORMACION E INFORMACION, EN
        # CUMPLIMIENTO DE LOS ARTICULOS 18 Y 19") es un superconjunto
        # exacto de la senal de FORMACION_PRL_ART_18_19 -- disparaba
        # ambas siempre, nunca solo esta. Ver migracion de retipado de
        # los documentos ya existentes con este codigo.
    ],
    "RECURSO_PREVENTIVO": ["DESIGNACION DE RECURSO PREVENTIVO"],
    "TITULACION_ACADEMICA": [
        # H36 (S110), confirmado con muestra real (pk=24896/24938,
        # GOMEZ_GARCIA_JOSE_ANTONIO/RAMIREZ_GARCIA_JORGE, 1970):
        # titulo academico antiguo real, expedido por el Ministerio de
        # Educacion, archivado hoy como FORMACION generico -- no tiene
        # nada que ver con formacion laboral/PRL.
        "EL MINISTRO DE EDUCACION Y CIENCIA",
        # H36 (S110), confirmado con muestra real (pk=24903, HIDALGO_
        # ROSAS_GABRIEL_ALEJANDRO, I.E.S. Fuente Luna): certificacion
        # academica oficial de expediente, mismo criterio.
        "CERTIFICACION OFICIAL DE EXPEDIENTE",
    ],
    "CONVENIO_FORMACION_BONIFICADA": [
        # H36 (S110), confirmado con muestra real (pk=25085, ALVAREZ_
        # SERRANO_ENRIQUE, TRANSGRUAL S.L.): contrato real de
        # encomienda de gestion de formacion bonificada (FUNDAE, Ley
        # 30/2015), archivado hoy como FORMACION generico -- es el
        # acuerdo administrativo con la entidad de formacion, nunca un
        # curso en si.
        "CONTRATO DE ENCOMIENDA DE ORGANIZACION DE LA FORMACION",
    ],
    "SOLICITUD_ADMINISTRATIVA": [
        # H36 (S110), confirmado con muestra real amplia (multiples
        # pk: ALVAREZ_VIEIRA, MOYANO_GUTIERREZ, ZAFRA_PERALTA,
        # ALVAREZ_SERRANO, CARVAJAL_GONZALEZ): formulario real de
        # autorizacion a la Junta de Andalucia para tramites
        # telematicos, archivado hoy como FORMACION generico. Tipo ya
        # existia en el catalogo pero sin ninguna senal hasta ahora.
        "PARA LA FIRMA Y PRESENTACION POR VIA TELEMATICA DE SOLICITUDES",
    ],
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
    # H35 (S107). Confirmado con pk=28255/28256 (mismo documento
    # duplicado, N/REF: 29/0117186/21) -- comunicacion real de la
    # Inspeccion de Trabajo sobre fraude en contratacion temporal.
    # Frase ancla especifica al organismo, nunca "COMUNICACION" sola
    # (palabra generica que aparece tambien en COMUNICACION_CONTRATO/
    # COMUNICACION_JORNADA).
    "COMUNICACION_INSPECCION_TRABAJO": [
        "ORGANISMO ESTATAL INSPECCION DE TRABAJO Y SEGURIDAD SOCIAL",
    ],
}

# Pares "gana X sobre Y" -- mismo principio que SPECIFIC_WINS de
# heuristic_type_service.py, pero para senales de CONTENIDO. Se aplica
# antes de declarar ambiguo un archivo con mas de una senal.
CONTENT_WINS = [
    ("PARTE_BAJA_MEDICA", "RECONOCIMIENTO_MEDICO"),
    ("PARTE_BAJA_MEDICA", "DNI"),
    ("CARNET_GRUISTA", "DNI"),
    ("CARNET_CONDUCIR", "DNI"),
    # H35 (S108), hallazgo real (pk=40898/40953): el "CERTIFICADO
    # MEDICO OFICIAL" de aptitud psicofisica cita textualmente
    # "OPERADOR DE GRUA MOVIL" dentro de su propia frase ancla --
    # coincide por casualidad con la senal de CARNET_GRUISTA (el
    # carnet real, un documento distinto). El certificado medico
    # de aptitud nunca es el carnet en si -- gana siempre.
    ("RECONOCIMIENTO_MEDICO", "CARNET_GRUISTA"),
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
    # H36 (S110), hallazgo real: campaña de retipado de CURSO (277
    # documentos activos) dio 178 "tipo ambiguo", de los cuales 162
    # (91%) eran choque estructural con la propia señal de CURSO
    # ("DIPLOMA"/"CERTIFICADO DE APROVECHAMIENTO"/"HAN REALIZADO EL
    # CURSO") -- estos documentos SON diplomas por definicion, asi que
    # CURSO dispara siempre a la vez que cualquier tipo especifico de
    # FORMACION_*. Mismo criterio que (FORMACION, CURSO) de mas arriba
    # (S104), extendido a los 14 tipos especificos sembrados en 0097
    # que todavia no lo tenian.
    ("FORMACION_EXTINCION_INCENDIOS", "CURSO"),
    ("FORMACION_ELECTRICIDAD", "CURSO"),
    ("FORMACION_SUBESTACIONES", "CURSO"),
    ("FORMACION_PRIMEROS_AUXILIOS", "CURSO"),
    ("FORMACION_OPERADOR_CAMION_AUTOCARGANTE", "CURSO"),
    ("FORMACION_TRABAJOS_ALTURA", "CURSO"),
    ("FORMACION_PLATAFORMA_ELEVADORA", "CURSO"),
    ("FORMACION_PRL_ART_18_19", "CURSO"),
    ("FORMACION_OPERADOR_APARATOS_ELEVACION", "CURSO"),
    ("FORMACION_PRL_60H", "CURSO"),
    ("FORMACION_OPERADOR_MINIGRUA", "CURSO"),
    ("FORMACION_CARRETILLAS_TRASPALETAS", "CURSO"),
    ("FORMACION_GRUAS_ASISTENCIA_CARRETERA", "CURSO"),
    ("FORMACION_GRUA_HIDRAULICA_ARTICULADA", "CURSO"),
    # H36 (S110): FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA es un tipo
    # real distinto de CARNET_GRUISTA y de FORMACION_PRL_ART_18_19,
    # aunque su propio molde M.P.E. dispare ambas senales a la vez
    # (menciona "grua movil" y trae el boilerplate legal de siempre).
    ("FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA", "CARNET_GRUISTA"),
    ("FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA", "CURSO"),
    ("FORMACION_GWO_SEGURIDAD_EOLICA", "FORMACION"),
    ("FORMACION_GWO_SEGURIDAD_EOLICA", "CURSO"),
    ("FORMACION_GWO_SEGURIDAD_EOLICA", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA", "FORMACION"),
    ("FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA", "CURSO"),
    ("FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA", "FORMACION_PRL_ART_18_19"),
    # H36 (S110), hallazgo real: 6 de los ambiguos restantes eran el
    # mismo tipo de choque estructural que CURSO/PRIMEROS_AUXILIOS,
    # pero contra el propio "FORMACION" generico ("FICHA DE
    # INSCRIPCION", firma en cualquier ficha de inscripcion real de
    # cualquier curso especifico) y contra "FORMACION_PRL_ART_18_19"
    # (mismo boilerplate legal presente en varios moldes M.P.E. de
    # cursos especificos, ya visto con GRUAS_ASISTENCIA_CARRETERA y
    # PRL_GRUA_MOVIL_AUTOPROPULSADA). Cualquier tipo especifico gana
    # siempre sobre ambos.
    ("FORMACION_EXTINCION_INCENDIOS", "FORMACION"),
    ("FORMACION_ELECTRICIDAD", "FORMACION"),
    ("FORMACION_SUBESTACIONES", "FORMACION"),
    ("FORMACION_PRIMEROS_AUXILIOS", "FORMACION"),
    ("FORMACION_OPERADOR_CAMION_AUTOCARGANTE", "FORMACION"),
    ("FORMACION_TRABAJOS_ALTURA", "FORMACION"),
    ("FORMACION_PLATAFORMA_ELEVADORA", "FORMACION"),
    ("FORMACION_PRL_ART_18_19", "FORMACION"),
    ("FORMACION_OPERADOR_APARATOS_ELEVACION", "FORMACION"),
    ("FORMACION_PRL_60H", "FORMACION"),
    ("FORMACION_OPERADOR_MINIGRUA", "FORMACION"),
    ("FORMACION_CARRETILLAS_TRASPALETAS", "FORMACION"),
    ("FORMACION_GRUAS_ASISTENCIA_CARRETERA", "FORMACION"),
    ("FORMACION_GRUA_HIDRAULICA_ARTICULADA", "FORMACION"),
    ("FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA", "FORMACION"),
    ("FORMACION_EXTINCION_INCENDIOS", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_ELECTRICIDAD", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_SUBESTACIONES", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_OPERADOR_CAMION_AUTOCARGANTE", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_TRABAJOS_ALTURA", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_PLATAFORMA_ELEVADORA", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_OPERADOR_APARATOS_ELEVACION", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_PRL_60H", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_OPERADOR_MINIGRUA", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_CARRETILLAS_TRASPALETAS", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_GRUAS_ASISTENCIA_CARRETERA", "FORMACION_PRL_ART_18_19"),
    ("FORMACION_GRUA_HIDRAULICA_ARTICULADA", "FORMACION_PRL_ART_18_19"),
    # H36 (S110), hallazgo real (pk=24671, CASTILLA NAVARRO FCO.
    # MIGUEL, 30/09/2021): documento real es un "PACTO DE PERMANENCIA"
    # (compromiso de permanencia tras formacion cara pagada por la
    # empresa) -- no es ni CARNET_GRUISTA ni CONTRATO, gana siempre
    # sobre ambos.
    ("PACTO_PERMANENCIA", "CARNET_GRUISTA"),
    ("PACTO_PERMANENCIA", "CONTRATO"),
    # H36 (S110), mismo documento (pk=24671) chocando esta vez con la
    # senal nueva de FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA -- el
    # pacto de permanencia menciona el curso que lo justifica, pero
    # sigue sin ser el curso en si.
    ("PACTO_PERMANENCIA", "FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA"),
    # H36 (S110), hallazgo real (pk=36103, HIDALGO ROSAS GABRIEL
    # ALEJANDRO, 29/01/2018): documento real es una "DESIGNACION DE
    # RECURSO PREVENTIVO" -- no es CURSO, gana siempre sobre el.
    ("RECURSO_PREVENTIVO", "CURSO"),
    # H36 (S110), hallazgo real (pk=34963, CARLIN CARVAJAL): documento
    # real de "grua de asistencia en carretera" (M.P.E., 30/09/2015)
    # estaba mal tipado como FORMACION_PRIMEROS_AUXILIOS -- el propio
    # temario del certificado incluye "Primeros Auxilios: P.A.S." como
    # punto 16 del indice de contenidos, simple mencion de pasada, no
    # un curso aparte. La senal de FORMACION_PRIMEROS_AUXILIOS (frase
    # suelta "PRIMEROS AUXILIOS") dispara con cualquier temario que la
    # mencione. Cualquier tipo especifico de FORMACION_* gana siempre
    # sobre FORMACION_PRIMEROS_AUXILIOS -- explica ademas buena parte
    # de los "tipo ambiguo" ya vistos en las campanas de FORMACION y
    # CURSO que se atribuyeron a cursos combinados reales.
    ("FORMACION_EXTINCION_INCENDIOS", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_ELECTRICIDAD", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_SUBESTACIONES", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_OPERADOR_CAMION_AUTOCARGANTE", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_TRABAJOS_ALTURA", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_PLATAFORMA_ELEVADORA", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_PRL_ART_18_19", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_OPERADOR_APARATOS_ELEVACION", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_PRL_60H", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_OPERADOR_MINIGRUA", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_CARRETILLAS_TRASPALETAS", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_GRUAS_ASISTENCIA_CARRETERA", "FORMACION_PRIMEROS_AUXILIOS"),
    ("FORMACION_GRUA_HIDRAULICA_ARTICULADA", "FORMACION_PRIMEROS_AUXILIOS"),
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
