# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/calibrate_fase_a_keywords.py
"""
H30 (S48) -- calibracion, SOLO LECTURA, del diccionario heuristico de
la Fase A del recorrido dirigido (ver ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md,
"Hoja de Ruta para la Siguiente Sesion", punto 1).

El diccionario real de S46/S47 nunca quedo persistido como codigo --
vivio solo en consultas puntuales de esas sesiones y en la narrativa
del anexo (que solapes se resolvieron, que falsos positivos se
descartaron). Este comando reconstruye candidatos de palabra clave por
tipo del catalogo cerrado (DocumentTypeCatalog, 59 tipos activos,
consultados en S48) y los verifica contra el corpus real -- nunca
escribe nada, solo cuenta coincidencias y muestra ejemplos reales para
que Miguel Angel confirme antes de que un comando separado (Fase A de
verdad) aplique document_type/domain_object en bulk.

Separa candidatos "seguros" (frases especificas, poco riesgo de falso
positivo) de acronimos cortos de riesgo real ya confirmado en S46
(OCA dentro de OCAÑA, CAP dentro de INCAPACIDAD/CAPACITACION) -- estos
ultimos solo se reportan, nunca se dan por buenos aqui.

BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE quedan
deliberadamente fuera de los candidatos por palabra: S47 confirmo que
se separan por carpeta real, nunca por la palabra "BAJA" sola.
"""
import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.models import DocumentIndexEntry

MACHINE_ROOT = "DOC. MAQUINAS"
PERSONAL_ROOT = "DOC. PERSONAL"

# Carpetas deliberadamente FUERA del alcance de clasificacion (S59,
# decision explicita de Miguel Angel): nunca se recorren en Fase A/B,
# nunca cuentan como "sin tipo" pendiente. Ruta completa real, no
# solo el nombre -- para no excluir por error una subcarpeta
# homonima en otro sitio.
OUT_OF_SCOPE_FOLDERS = [
    # FOTOS CARNET: fotografias de carnet (la foto tipo DNI que se
    # entrega para tramitarlo), no documentacion administrativa --
    # nunca van a tener un tipo del catalogo cerrado. Miguel Angel,
    # verbatim: "esa carpeta no la vamos a clasificar, la vamos a
    # sacar del scope."
    "DOC. PERSONAL/FOTOS CARNET",
]
BUCKET = "cgs_grupo_alvarez"

# domain -> {code: [candidatos]}
CANDIDATES_SAFE = {
    "MACHINE": {
        # Añadido S55: nunca tuvo ninguna regla real (confirmado 0
        # coincidencias en el dry-run de run_fase_a_sweep, S55) pese a
        # que los archivos reales llevan la palabra literal en el
        # nombre ("2.026-A-7.466_albaran-camara...", "AC A26
        # 0200005698_...ALBARAN_AC-A26-0200005698..."). Verificado
        # contra 21 nombres reales de la carpeta 2026-07 antes de
        # añadirlo.
        "ALBARAN_ENTREGA": ["ALBARAN"],
        "BAJA_DEFINITIVA": [
            "BAJA DEFINITIVA",
            # Añadido S51: DOC_BAJA_DEFINITIVA se fusiona en
            # BAJA_DEFINITIVA (migración 0033) -- mismo formulario
            # oficial DGT ("BAJA DE VEHÍCULO"/"DATOS BAJA DEFINITIVA"),
            # confirmado con 6 muestras reales sin ninguna diferencia
            # de contenido, incluido el propio desguace (CATV)
            # mencionado indistintamente en ambos casos.
            "DESGUACE",
        ],
        "BAJA_TEMPORAL": ["BAJA TEMPORAL"],
        "CERT_MANTENIMIENTO": [
            "CERTIF MANTENIMIENTO", "CERTIFICADO MANTENIMIENTO",
            # Añadido S49 (hoja de ruta S48, punto 2): variante real sin
            # "IF"/"IFICADO" -- archivos que dicen literalmente "CERT
            # MANTENIMIENTO", detectados en la auditoria de blob de B-38.
            "CERT MANTENIMIENTO",
            # Añadidos S50, medidos con datos reales dentro del mapa
            # acotado de H30 (ver EnterpriseBot_028_GET.txt de la
            # sesion): "CERT MANT" (11 coincidencias reales, variante
            # abreviada) y "REVISION MANTENIMIENTO" (20, mismo concepto
            # de mantenimiento certificado, sin tipo propio en el
            # catalogo -- mapeado aqui por ser el existente mas
            # cercano, mismo criterio ya usado con RECIBO suelto para
            # SEGURO).
            "CERT MANT", "REVISION MANTENIMIENTO",
        ],
        "CERT_NO_TARJ_TTES": [
            "CERT_NO_TARJ_TTES",
            # Añadido S50: primera keyword real verificada para este
            # tipo (llevaba desde su alta sin ninguna confirmada).
            # "CERT NO TARJ TTES" (espacios) cubre via separador
            # flexible tanto "CERT.NO TARJ.TTES" como "CERT_NO_TARJ_
            # TTES" -- 68 coincidencias reales dentro del mapa acotado
            # de H30 (ver EnterpriseBot_028_GET.txt).
            "CERT NO TARJ TTES",
        ],
        # Corregido S55: el candidato original solo cubria "CERTIFICADO
        # REVISION"/"CERTIF REVISION" -- verificado contra el dry-run
        # real de run_fase_a_sweep (S55) que la abreviatura real "CERT
        # REVISION"/"Cert.revision" (sin "IFICADO") aparece en archivos
        # reales sin clasificar y nunca matcheaba. Añadida como
        # candidato propio.
        "CERT_REVISION": [
            "CERTIFICADO REVISION", "CERTIF REVISION", "CERT REVISION",
        ],
        # Añadido S50 (alta S50, ver migracion 0029): certificado de
        # exencion de permiso, caso real "Z-78 Cert.exencion perm
        # 15-02-2021.pdf". "CERT EXENCION" cubre via separador
        # flexible tanto "Cert.exencion" como "Cert exencion".
        "CERT_EXENCION_PERMISO": ["EXENCION PERMISO", "CERT EXENCION"],
        # Añadido S50 (segunda ronda, alta migracion 0030): garantia
        # de fabricante/concesionario, casos reales "Z-124 GARANTIA
        # JLG.pdf", "GARANTIA AUTOCARE.pdf".
        "GARANTIA_FABRICANTE": ["GARANTIA"],
        # Añadido S49 (hoja de ruta S48, punto 3): CERTIFICADO_PODERES
        # (S48) no tenia candidato en este diccionario todavia. "PODERES"
        # ya contaba 28 coincidencias reales segun la auditoria de B-38 --
        # confirmar volumen exacto en calibracion antes de aplicar.
        "CERTIFICADO_PODERES": [
            "PODERES",
            # Añadido S50 (segunda ronda): variante singular real, 7
            # coincidencias (ver EnterpriseBot_049_GET.txt) -- "PODER
            # JESUS MALSA, SLU.pdf", "Z-119 poder bast 77715.pdf".
            "PODER",
            # Añadido S51: MANDATO se fusiona en CERTIFICADO_PODERES
            # (migracion 0033) -- mismo documento real ("DOCUMENTO DE
            # REPRESENTACION DE PERSONAS JURIDICAS"), confirmado con 6
            # muestras reales sin ninguna diferencia de contenido.
            "MANDATO",
        ],
        "CONTRATO_COMPRAVENTA": ["CONTRATO COMPRAVENTA", "COMPRAVENTA"],
        # Añadido S50 (segunda ronda, alta migracion 0030): contrato
        # real de arrendamiento de maquinaria entre empresas del
        # grupo, confirmado por texto extraido del PDF real. "RENTING"
        # incluido como variante -- mismo concepto de alquiler bajo
        # otro nombre comercial, caso real "7038DZX RENTING.pdf".
        "CONTRATO_ARRENDAMIENTO": [
            "CONTRATO ARRENDAMIENTO", "ARRENDAMIENTO", "RENTING",
        ],
        # Añadido S50 (segunda ronda, alta migracion 0030): solicitud
        # de cambio de titularidad de vehiculo, confirmado por texto
        # extraido del PDF real ("JUSTIFICANTE PROFESIONAL DE
        # SOLICITUD DE CAMBIO DE TITULARIDAD", tramite DGT).
        "CAMBIO_TITULARIDAD": ["CAMBIO TITULARIDAD"],
        # Añadido S50 (segunda ronda, alta migracion 0030): carta
        # verde, certificado internacional de seguro. Confirmado por
        # Miguel Angel verbatim: "la carta verde es el seguro
        # internacional".
        "CARTA_VERDE": ["CARTA VERDE"],
        "C_ADECUACION": ["ADECUACION"],
        # Añadido S50 (alta S50, ver migracion 0029): cuadro de
        # amortizacion de prestamo/leasing, caso real "BBVA 1723376
        # CUADRO AMORTIZACIÓN.pdf".
        "CUADRO_AMORTIZACION": ["CUADRO AMORTIZACION"],
        "DECLARACION_HOMOLOGACION": ["HOMOLOGACION"],
        "DNI_COMPRADOR": ["DNI COMPRADOR"],
        # Renombrado S56 (migracion 0036): DOC_VENTA -> FACTURA_VENTA,
        # mismo objeto de catalogo, Miguel Angel confirmo que siempre
        # fue conceptualmente una factura de venta, nunca otra cosa.
        "FACTURA_VENTA": ["VENTA"],
        "FACTURA_COMPRA": [
            "FACTURA COMPRA",
            # Añadido S50 (segunda ronda): "INVOICE" ingles, caso real
            # de proveedor extranjero (JLG) -- 6 coincidencias (ver
            # EnterpriseBot_049_GET.txt).
            "INVOICE",
            # Añadido S56: FACTURA_TERCEROS se fusiona en FACTURA_COMPRA
            # (migracion 0036) -- decision de Miguel Angel de que el
            # unico criterio real de distincion entre tipos de factura
            # es quien emite (Grúas Álvarez/empresa del grupo = factura
            # de venta propia, cualquier otro = factura de compra), no
            # si el destinatario es la empresa o un socio. La keyword
            # suelta "FACTURA" (antes de FACTURA_TERCEROS) se hereda
            # aqui tal cual.
            "FACTURA",
        ],
        "FICHA_TECNICA": ["FICHA TECNICA"],
        # tarjeta de combustible, caso real "Z92 gastos tarjeta
        # gasoil SOLRED.pdf". "SOLRED" es marca real de tarjeta de
        # combustible usada en el corpus -- se incluye como candidato
        # propio junto a las frases genericas.
        "GASTOS_TARJETA_COMBUSTIBLE": [
            "TARJETA GASOIL", "TARJETA COMBUSTIBLE", "SOLRED",
        ],
        # Añadido S50 (alta S50, ver migracion 0029): Impuesto
        # Especial sobre Determinados Medios de Transporte (Modelo
        # 06), caso real "A-69 IMPUESTO MEDIOS TRANSPORTES 06.pdf" --
        # confirmado con Miguel Angel viendo el PDF real, distinto de
        # IVTM (ver mas abajo).
        "IEDMT": ["IMPUESTO MEDIOS TRANSPORTE", "IEDMT"],
        "ITV": ["ITV"],
        # Añadido S50 (alta S50, ver migracion 0029): Impuesto sobre
        # Vehiculos de Traccion Mecanica, autoliquidacion municipal.
        # "IVTA" incluida deliberadamente -- es la errata real que ya
        # usa el corpus (caso real "A-69 E-0124-BJL IVTA.pdf"; el
        # contenido del PDF es IVTM, confirmado con Miguel Angel).
        "IVTM": ["IVTM", "IVTA", "TRACCION MECANICA",
                 # Añadido S50 (segunda ronda): errata real "ITVM"
                 # (letras invertidas), 3 coincidencias.
                 "ITVM"],
        "JUSTIFICANTE_TRANSFERENCIA": ["JUSTIFICANTE_TRANSFERENCIA"],
        # Añadido S50 (segunda ronda, alta migracion 0030): informe de
        # incidencias de maquina, confirmado por texto real (Z106/Z-42
        # "INFORME DE INCIDENCIAS.docx").
        "INFORME_INCIDENCIAS": ["INFORME INCIDENCIAS", "INCIDENCIAS"],
        "LEASING": ["LEASING"],
        "LIBRO_HISTORIAL": [
            "LIBRO HISTORIAL",
            # Añadido S50: variante real, 2 coincidencias dentro del
            # mapa acotado de H30 (ver EnterpriseBot_028_GET.txt).
            "REGISTRO HISTORIAL",
        ],
        "MANUAL_DESPIECE": ["DESPIECE"],
        "MANUAL_USO": ["MANUAL USO"],
        "PERMISO_CIRCULACION": [
            "PERMISO CIRCULACION",
            # Añadido S49 (hoja de ruta S48, punto 2): variante abreviada
            # real detectada en la auditoria de blob de B-38.
            "PERM CIRC",
            # Añadido S49: variante real con "DE" en medio, detectada al
            # investigar el caso 7245GBM (Peugeot 307) -- 133
            # coincidencias reales confirmadas antes de aplicar.
            "PERMISO DE CIRCULACION",
            # Añadidos S50, medidos dentro del mapa acotado de H30 (ver
            # EnterpriseBot_028_GET.txt): "PERM CIRCULACION" (100
            # coincidencias reales, cubre via separador flexible tanto
            # "PERM.CIRCULACION" como "PERM CIRCULACION" y "PERM-
            # CIRCULACION"), "PERMISO CIRCUL" (2, variante truncada),
            # "AUTORIZACION TEMPORAL CIRCULACION" (1, variante formal
            # real), y "PERMISOTEMPORALCIRCULACION" (2, sin separador
            # alguno -- palabra unica pegada, no se puede expresar como
            # frase de varias palabras con el separador flexible).
            "PERM CIRCULACION", "PERMISO CIRCUL",
            "AUTORIZACION TEMPORAL CIRCULACION",
            "PERMISOTEMPORALCIRCULACION",
        ],
        "PRESTAMO": ["PRESTAMO"],
        "PROFORMA": ["PROFORMA"],
        # Añadido S50 (segunda ronda, alta migracion 0030): pedido de
        # compra, distinto de la factura ya emitida (caso real
        # confirmado: "MERCEDES Pedido Firmado.pdf").
        "PEDIDO_COMPRA": ["PEDIDO"],
        # Añadido S50 (segunda ronda, alta migracion 0030):
        # autorizacion de provision de fondos para compra/importacion
        # de maquinaria (caso real confirmado: "Autorizacion provision
        # fondos [...] firmado.pdf").
        "PROVISION_FONDOS": ["PROVISION FONDOS"],
        # Añadido S50 (alta S50, ver migracion 0029): sancion de
        # trafico, caso real "Sancion 5462FJP 2022 02 21 pagada.pdf".
        "SANCION_TRAFICO": ["SANCION"],
        "RECIBO_LEASING": [
            "CUOTA LEASING", "RECIBO LEASING", "FACTURA LEASING",
        ],
        # Añadido S50 (segunda ronda, alta migracion 0030): revision
        # periodica de eslingas y elementos de izado (patron real
        # "REV.ESLINGAS Y ELEM.IZADO GC [fecha]", repetido por maquina
        # -- historico de inspecciones). Miguel Angel confirmo
        # tracks_expiry=True, mismo criterio que IPO/CERT_MANTENIMIENTO.
        "REVISION_ESLINGAS": ["REV ESLINGAS", "REVISION ESLINGAS"],
        "RECIBO_SENAL_COMPRA": ["RECIBO_SENAL_COMPRA"],
        "SOLICITUD_ADMINISTRATIVA": ["SOLICITUD"],
        "TABLA_DE_CARGA": ["TABLA CARGA"],
        "TARJETA_TRANSPORTE": ["TARJETA TRANSPORTE"],
    },
    "BOTH": {
        # S51: MANDATO vivía aquí bajo "BOTH" (aplicaba también a
        # personal) antes de fusionarse en CERTIFICADO_PODERES
        # (MACHINE, migración 0033) -- se preserva la coincidencia
        # para personal aquí, sin duplicar el código en el catálogo.
        "CERTIFICADO_PODERES": ["MANDATO"],
        "SEGURO": [
            "SEGURO", "REC SEG", "REC POL",
            # Añadido S49: recibo suelto sin "SEG"/"POL" inmediato
            # (p.ej. "RECIBO 4417-GHR 151210 A151211.pdf"), detectado
            # al investigar el caso 7245GBM -- 223 coincidencias reales
            # confirmadas antes de aplicar. Se solapara con
            # RECIBO_LEASING/RECIBO_SENAL_COMPRA en archivos que
            # combinen ambas palabras -- revisar en calibracion.
            "RECIBO",
            # Añadidos S50 (segunda ronda), medidos con datos reales
            # (ver EnterpriseBot_049_GET.txt): "REC BCO"/"REC.BCO"
            # (127+87, confirmado por texto real: cargos bancarios de
            # domiciliacion de la prima del seguro), "SEGUROS" (6,
            # variante en plural -- "SEGURO" no la cubria porque el
            # lookaround exige que no venga letra/digito justo
            # despues, y la "S" del plural sí lo es), y "ABONO" (7,
            # confirmado por texto real: abono/devolucion bancaria
            # ligada al seguro, ej. "REC.BCO.HELVETIA...ABONO CAMBIO").
            "REC BCO", "SEGUROS", "ABONO",
        ],
        # Añadido S49 (hoja de ruta S48, punto 3): POLIZA_SEGURO (S48) ya
        # esta deliberadamente separado de SEGURO (Miguel Angel, S48:
        # "una cosa es la poliza y otra cosa es el recibo del seguro") --
        # candidato propio "POLIZA", nunca fusionado con los de SEGURO.
        "POLIZA_SEGURO": [
            "POLIZA",
            # Añadidos S50 (segunda ronda), medidos con datos reales:
            # "CONDICIONES GENERALES"/"CONDICIONES PARTICULARES" (4+2,
            # condiciones de poliza) y "SUPLEMENTO" (5, endoso/
            # suplemento real de poliza -- "SUPLEMENTO ALTA
            # 9834JVJ...pdf").
            "CONDICIONES GENERALES", "CONDICIONES PARTICULARES",
            "SUPLEMENTO",
        ],
        "TACOGRAFO": ["TACOGRAFO"],
    },
    "PERSONAL": {
        "ALTA_MEDICA": ["ALTA MEDICA"],
        "ALTA": ["ALTA"],
        # Añadido S59: variante abreviada real dentro de las carpetas
        # individuales de OPERARIOS -- "AUT USO MAQ ...pdf" /
        # "Aut.uso maq. ...pdf", 168 coincidencias reales verificadas
        # contra Comando S (6,4% de los 2.618 sin tipo de esa carpeta,
        # nunca "el grueso" como se hipotetizaba en S58 con una sola
        # muestra) -- distinta de la regla de carpeta ya existente
        # ("AUTORIZACION USO DE MAQUINARIA" en FOLDER_TYPE_RULES, que
        # cubre una carpeta central de nombre completo, no estos
        # archivos sueltos dentro de la carpeta de cada persona).
        "AUTORIZACION_USO_MAQUINARIA": [
            "AUT USO MAQ",
            # Añadido S59: convencion de nombrado nueva detectada en
            # "PTE CONTRATACION" -- codigo de tipo COMPLETO dentro
            # del nombre, separado por guion bajo (p.ej.
            # "GUTIERREZ_MATEO_CRISTHIAN_AUTORIZACION_USO_MAQUINARIA_
            # 20250410.pdf"). El separador flexible de _build_pattern
            # ya cubre "_" igual que espacio/guion/punto, asi que la
            # frase completa sin "DE" basta -- confirmado por Miguel
            # Angel como regla reutilizable para cualquier tipo que
            # aparezca con este patron APELLIDO_NOMBRE_TIPO_FECHA.
            "AUTORIZACION USO MAQUINARIA",
        ],
        "CARNET_CONDUCIR": [
            "CARNET CONDUCIR", "CARNE CONDUCIR",
            # Añadido S63: la propia etiqueta del catalogo ya dice
            # "Carnet / tarjeta de conductor" -- confirmado con 38
            # coincidencias reales dentro de DOC. PERSONAL/PERSONAL
            # (tacografo, no carnet de conducir, pero mismo tipo de
            # catalogo por diseño). Ver EnterpriseBot_002_GET.txt.
            "TARJETA DEL CONDUCTOR", "TARJETA DE CONDUCTOR",
        ],
        "AUTONOMO": [
            # Añadido S59 (migracion 0039): recibos mensuales de
            # cuota de autonomo de la familia Alvarez, mayoria real
            # de "DOC. PERSONAL/PERSONAL/ADMINISTRACION".
            "AUTONOMO",
        ],
        "CONTRATO": [
            "CONTRATO LABORAL",
            # Añadido S59, confirmado por Miguel Angel: dentro de
            # DOC. PERSONAL casi cualquier archivo con "CONTRATO" en
            # el nombre es un contrato laboral (indefinido o con el
            # nombre del trabajador) -- a diferencia de MACHINE, donde
            # "CONTRATO" puede ser CONTRATO_COMPRAVENTA (ese codigo
            # vive en el diccionario MACHINE, sin colision posible:
            # el emparejamiento siempre esta acotado por dominio, ver
            # _match_candidates). Cubre tambien el patron
            # APELLIDO_NOMBRE_CONTRATO_FECHA de "PTE CONTRATACION".
            "CONTRATO",
        ],
        "CURSO": ["CURSO"],
        "DNI": ["DNI"],
        "ENTREGA_INFORMACION": ["ENTREGA INFORMACION"],
        "EXCEDENCIA": ["EXCEDENCIA"],
        "FORMACION": [
            "FORMACION",
            # Añadido S63: abreviatura real dentro de las carpetas
            # individuales de OPERARIOS/TALLER/ADMINISTRACION -- 940
            # coincidencias reales sobre los 3.275 sin tipo de DOC.
            # PERSONAL/PERSONAL (ver EnterpriseBot_002_GET.txt),
            # patron dominante del bloque. "FORM" cubre via separador
            # flexible "FORM.", "FORM ", "FORM6H", etc.
            "FORM",
        ],
        "MOD_145": [
            "MODELO 145",
            # Añadido S63: variante real sin la palabra "MODELO" --
            # "MOD.145"/"MOD. 145", 55 coincidencias reales (ver
            # EnterpriseBot_002_GET.txt).
            "MOD 145",
        ],
        "NOMINA": ["NOMINA"],
        "PAGO_CORRIENTE": ["PAGO CORRIENTE"],
        "RECONOCIMIENTO_MEDICO": ["RECONOCIMIENTO MEDICO"],
        "SEG_SOCIAL": [
            "SEGURIDAD SOCIAL",
            # Añadido S59: variante abreviada del mismo patron
            # APELLIDO_NOMBRE_TIPO_FECHA de "PTE CONTRATACION" (p.ej.
            # "GUTIERREZ_MATEO_CRISTHIAN_SEG_SOCIAL_20260805.pdf").
            "SEG SOCIAL",
        ],
        "VACACIONES": ["VACACIONES"],
        # EPIS deliberadamente FUERA (S48, correccion de Miguel Angel):
        # los documentos de EPI se consumen hacia EpiDelivery/
        # EpiReview (modelo propio de S47), nunca se clasifican como
        # document_type=EPIS por este recorrido heuristico -- flujo
        # distinto. Sin esta exclusion, ademas, "EPIS ALTA
        # VISIBILIDAD" habria colisionado en falso con ALTA (ver
        # EXCLUSIONS mas abajo).
    },
}

# Exclusiones por falso positivo real, detectado contra el corpus
# (mismo patron que "BAJA TENSION" excluido de BAJA_PERSONAL en S46).
# clave (domain, code, phrase) -> lista de frases que, si aparecen en
# el nombre, anulan esa coincidencia aunque el patron de palabra
# suelta hubiera matcheado.
EXCLUSIONS = {
    ("PERSONAL", "ALTA", "ALTA"): ["ALTA VISIBILIDAD"],
    # Añadido S49: falso positivo real detectado en calibracion --
    # "PAGINA POLIZA RC - FORMACION OPERADORES PEMP.pdf" menciona la
    # poliza RC de pasada en un documento de formacion, no es una
    # poliza real de maquina/vehiculo.
    ("BOTH", "POLIZA_SEGURO", "POLIZA"): ["POLIZA RC - FORMACION"],
    # Añadido S59: falso positivo real detectado en el dry-run de
    # run_fase_a_sweep tras ampliar CONTRATO a la palabra suelta --
    # "CONTRATO DE ENCOMIENDA"/"CONTRATO ENCOMIENDA" es un acuerdo de
    # gestion de formacion con un centro externo (FUNDAE, TAGA,
    # ILURO, EESEA...), nunca un contrato laboral de un trabajador
    # concreto -- decenas de coincidencias reales bajo "FORMACION
    # TRABAJADORES", ninguna es CONTRATO. Ambas variantes (con/sin
    # "DE") porque el separador flexible no salta palabras de por
    # medio -- "CONTRATO ENCOMIENDA" no cubre "CONTRATO DE
    # ENCOMIENDA" sin esta segunda entrada explicita.
    ("PERSONAL", "CONTRATO", "CONTRATO"): [
        "CONTRATO DE ENCOMIENDA", "CONTRATO ENCOMIENDA",
    ],
}

CANDIDATES_RISKY = {
    "MACHINE": {
        "CE": ["CE"],
        # Fusionados S50 (migracion 0031): IPO e ITC resultaron ser el
        # mismo documento real por contenido (acta de inspeccion
        # periodica de grua movil) -- ver
        # sample_known_type_ocr_text, ambos arrojaron el mismo texto
        # de fondo. Un solo codigo, dos palabras candidatas.
        "IPO_ITC": ["IPO", "ITC"],
        "OCA": ["OCA"], "RAE": ["RAE"],
    },
    "PERSONAL": {
        "CAP": ["CAP"], "CSS": ["CSS"], "IDC": ["IDC"],
        # Añadido S63: 117 coincidencias reales de RECONOCIMIENTO_
        # MEDICO abreviado como "RM" dentro de DOC. PERSONAL/PERSONAL
        # (ver EnterpriseBot_002_GET.txt) -- acronimo corto de 2
        # letras, mismo riesgo real ya documentado para CAP/CSS/IDC
        # (colision con acronimos ajenos), por eso va aqui y no en
        # CANDIDATES_SAFE pese a superar el umbral de calibracion.
        "RM": ["RM"],
    },
}


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _build_pattern(phrase):
    parts = [re.escape(w) for w in phrase.split(" ")]
    body = r"[ _\-\.]+".join(parts)
    # Corregido S48: \b trata "_" como caracter de palabra, asi que
    # nunca detectaba un candidato pegado entre guiones bajos (p. ej.
    # "CERT_NO_TARJ_TTES" dentro de "A29_CERT_NO_TARJ_TTES_20230314"
    # -- verificado con datos reales que \b fallaba ahi). Un lookaround
    # que solo trata [A-Z0-9] como caracter de palabra trata "_"/"-"/
    # "."/espacio como frontera valida por igual.
    return re.compile(r"(?<![A-Z0-9])" + body + r"(?![A-Z0-9])")


def _files_for_domain(domain):
    roots = []
    if domain in ("MACHINE", "BOTH"):
        roots.append(MACHINE_ROOT)
    if domain in ("PERSONAL", "BOTH"):
        roots.append(PERSONAL_ROOT)
    cond = Q()
    for root in roots:
        cond |= Q(parent_path=root) | Q(parent_path__startswith=root + "/")
    qs = DocumentIndexEntry.objects.filter(
        cond, bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type__isnull=True,
    )
    exclude_cond = Q()
    for folder in OUT_OF_SCOPE_FOLDERS:
        exclude_cond |= (
            Q(parent_path=folder) | Q(parent_path__startswith=folder + "/")
        )
    if exclude_cond:
        qs = qs.exclude(exclude_cond)
    return qs.only("id", "name", "parent_path")


class Command(BaseCommand):
    help = (
        "H30 (S48) -- calibracion de solo lectura del diccionario "
        "heuristico de Fase A. No escribe nada en la base de datos."
    )

    def _run(self, candidates_dict, label):
        self.stdout.write("========== %s ==========" % label)
        match_index = {}
        for domain, codes in candidates_dict.items():
            entries = list(_files_for_domain(domain))
            norm_names = [
                (e, _strip_accents(e.name).upper()) for e in entries
            ]
            for code, phrases in codes.items():
                for phrase in phrases:
                    pattern = _build_pattern(_strip_accents(phrase).upper())
                    excl_phrases = EXCLUSIONS.get((domain, code, phrase), [])
                    excl_patterns = [
                        _build_pattern(_strip_accents(p).upper())
                        for p in excl_phrases
                    ]
                    hits = [
                        e for e, n in norm_names
                        if pattern.search(n)
                        and not any(ep.search(n) for ep in excl_patterns)
                    ]
                    self.stdout.write(
                        "%s | %-28s | %-30s | %d coincidencias"
                        % (domain, code, phrase, len(hits))
                    )
                    for e in hits[:3]:
                        self.stdout.write(
                            "    ej: [%s] %s" % (e.parent_path, e.name)
                        )
                    for e in hits:
                        match_index.setdefault(e.id, []).append(
                            (code, phrase)
                        )

        overlaps = {
            eid: codes for eid, codes in match_index.items()
            if len(set(c for c, _p in codes)) > 1
        }
        self.stdout.write(
            "--- SOLAPES DETECTADOS (mismo archivo, mas de un tipo "
            "candidato): %d ---" % len(overlaps)
        )
        shown = 0
        for eid, codes in overlaps.items():
            if shown >= 15:
                self.stdout.write(
                    "    ... (%d solapes mas, no mostrados)"
                    % (len(overlaps) - shown)
                )
                break
            entry = DocumentIndexEntry.objects.get(pk=eid)
            self.stdout.write(
                "    [%s] %s -> %s"
                % (entry.parent_path, entry.name, codes)
            )
            shown += 1

        # Agregacion por PAR de tipos -- volumen real, no archivo a
        # archivo, para decidir prioridades con datos (S48). Incluye
        # hasta 3 ejemplos reales por par -- decidir prioridad sin ver
        # nombres reales seria interpretacion propia, prohibido por
        # directriz 4.8.
        from collections import Counter, defaultdict
        pair_counts = Counter()
        pair_examples = defaultdict(list)
        for eid, codes in overlaps.items():
            distinct_codes = sorted(set(c for c, _p in codes))
            for i in range(len(distinct_codes)):
                for j in range(i + 1, len(distinct_codes)):
                    pair = (distinct_codes[i], distinct_codes[j])
                    pair_counts[pair] += 1
                    if len(pair_examples[pair]) < 3:
                        pair_examples[pair].append(eid)
        self.stdout.write("--- SOLAPES AGREGADOS POR PAR DE TIPOS ---")
        for pair, count in pair_counts.most_common():
            self.stdout.write(
                "    %s <-> %s : %d archivos" % (pair[0], pair[1], count)
            )
            for eid in pair_examples[pair]:
                entry = DocumentIndexEntry.objects.get(pk=eid)
                self.stdout.write(
                    "        ej: [%s] %s" % (entry.parent_path, entry.name)
                )

    def handle(self, *args, **options):
        self._run(CANDIDATES_SAFE, "CANDIDATOS SEGUROS")
        self._run(CANDIDATES_RISKY, "ACRONIMOS DE RIESGO -- SOLO REVISION")
