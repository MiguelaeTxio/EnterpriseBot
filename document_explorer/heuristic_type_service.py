# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/heuristic_type_service.py
"""
H30 (S51). Heuristica de resolucion de TIPO documental por nombre de
archivo -- extraida de `run_fase_a_sweep.py` (S48/S49), donde vivio
como codigo local hasta ahora. Se mueve aqui para que la use tambien
el pipeline de clasificacion en tiempo real (`classification_service.
apply_quarantine_classification()`), sin duplicar el framework de
prioridades ya validado contra 11.149 documentos reales.

`run_fase_a_sweep.py` pasa a importar desde aqui en vez de definir
estas mismas funciones/constantes localmente -- mismo comportamiento,
cero duplicacion. `calibrate_fase_a_keywords.py` sigue siendo la
fuente real de los diccionarios de palabras clave (CANDIDATES_SAFE/
CANDIDATES_RISKY/EXCLUSIONS) -- este modulo los importa, no los
redefine.

Nunca reescribir el framework de prioridades de memoria en otra
sesion -- leer este modulo y la seccion "COMPLETADAS EN S48" del
anexo H30 primero.
"""
import re

from document_explorer.management.commands.calibrate_fase_a_keywords import (
    CANDIDATES_RISKY, CANDIDATES_SAFE, EXCLUSIONS, _build_pattern,
    _strip_accents,
)

# --- Framework de prioridades, confirmado por Miguel Angel S48 ---
# Pares DOSIER: documentos distintos escaneados juntos -> papelera,
# nunca se les asigna document_type.
DOSSIER_PAIRS = frozenset({
    frozenset({"FICHA_TECNICA", "PERMISO_CIRCULACION"}),
    frozenset({"CARNET_CONDUCIR", "DNI"}),
    frozenset({"CARNET_CONDUCIR", "TACOGRAFO"}),
    frozenset({"ITV", "TACOGRAFO"}),
    # Añadido S49: poliza + recibo del seguro escaneados juntos en el
    # mismo PDF (patron real "POLIZA+REC.SEG...."), confirmado por
    # Miguel Angel como el mismo caso de dosier ya conocido.
    frozenset({"POLIZA_SEGURO", "SEGURO"}),
})

# Pares "gana X sobre Y" -- orden (winner, loser). Se aplican en orden;
# la primera regla cuyo par este presente en las coincidencias del
# archivo decide.
SPECIFIC_WINS = [
    ("PROFORMA", "FACTURA_VENTA"),
    ("CONTRATO_COMPRAVENTA", "FACTURA_VENTA"),
    ("ITV", "FICHA_TECNICA"),
    ("PERMISO_CIRCULACION", "FACTURA_VENTA"),
    ("PERMISO_CIRCULACION", "FICHA_TECNICA"),
    ("RECIBO_LEASING", "LEASING"),
    ("ALTA_MEDICA", "ALTA"),
    ("ALTA", "SEG_SOCIAL"),
    ("CURSO", "TACOGRAFO"),
    # Retirada S56 (migracion 0036): FACTURA_TERCEROS se fusiono en
    # FACTURA_COMPRA -- ya no hay dos codigos que puedan colisionar
    # aqui, la regla queda obsoleta y se retira en vez de dejarla
    # muerta (nunca podria hacer match, FACTURA_TERCEROS ya no se
    # asigna a nada).
]
# DOC_VENTA renombrado a FACTURA_VENTA en S56 (migracion 0036) --
# mismo objeto de catalogo, ver docstring de la migracion.
# Cualquier tipo especifico gana siempre sobre SOLICITUD_ADMINISTRATIVA.
GENERIC_LOSER = "SOLICITUD_ADMINISTRATIVA"

# CURSO <-> FORMACION: gana FORMACION si hay patron de horas
# (2H/6H/60H/20 HORAS...), si no gana CURSO (S48).
_HOUR_PATTERN = re.compile(r"\b\d{1,3}\s*H(?:ORAS?)?\b")

# Pares sin decision todavia (S48) -- se dejan sin document_type.
UNRESOLVED_PAIRS = frozenset({
    frozenset({"ENTREGA_INFORMACION", "FORMACION"}),
    frozenset({"DNI", "FORMACION"}),
})

# BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE (S47):
# se resuelven por carpeta real, nunca por palabra "BAJA" sola.
# PAGO_CORRIENTE / AUTORIZACION_USO_MAQUINARIA anadidos S54, tras
# confirmar sus carpetas reales con datos reales (Comando S contra
# DocumentIndexEntry, ver anexo H30 S54): "DOC. PERSONAL/DECLARACION
# AL CORRIENTE/..." (1.762 archivos) y "DOC. PERSONAL/AUTORIZACION
# USO DE MAQUINARIA/..." (383 archivos). PARTE_BAJA_MEDICA gana un
# segundo needle real: "INCAPACIDAD LABORAL" (carpeta real distinta
# de "PARTES BAJA ENF.COMUN Y ACC.NO LABORAL", mismo tipo, coherente
# con el caos real de nomenclatura que Miguel Angel describio en S54
# -- distintas personas archivando el mismo tipo de documento con
# nombres de carpeta distintos segun el dia.
FOLDER_TYPE_RULES = [
    ("PARTES BAJA ENF.COMUN Y ACC.NO LABORAL", "PARTE_BAJA_MEDICA"),
    ("INCAPACIDAD LABORAL", "PARTE_BAJA_MEDICA"),
    ("INVESTIGACION ACCIDENTES", "INVESTIGACION_ACCIDENTE"),
    ("PERSONAL/BAJAS", "BAJA_PERSONAL"),
    # Corregido en esta sesion: el needle original solo cazaba una
    # carpeta "BAJAS" colgando literalmente de un segmento "PERSONAL"
    # (".../PERSONAL/BAJAS/..."). Deja fuera "TALLER/BAJAS",
    # "OPERARIOS/.../TRABAJADORES INACTIVOS/.../BAJA", etc. -- mismo
    # concepto de carpeta real, misma decision de diseno S47 (por
    # carpeta, nunca por la palabra BAJA sola). Regla generica de
    # segmento de carpeta completo "BAJAS" (plural, con barras a
    # ambos lados para exigir que sea el nombre exacto de una
    # carpeta, nunca una subcadena de otra palabra). Confirmado sin
    # colision real: en MACHINE el patron real es siempre "BAJA"
    # singular ("VEHICULOS DE BAJA", "GONDOLAS/BAJA DEFINITIVA"),
    # nunca "BAJAS" plural. Ver EnterpriseBot_016_GET.txt.
    ("/BAJAS/", "BAJA_PERSONAL"),
    # Añadido en esta sesion: carpeta de proposito unico, confirmado
    # por Miguel Angel (codigo nuevo REGISTRO_JORNADA, opcion A). 251
    # archivos reales bajo "DOC. PERSONAL/REGISTRO DE JORNADA/..."
    # (ver EnterpriseBot_016_GET.txt) -- mas fiable por carpeta que
    # por palabra clave, mismo criterio que BAJA_PERSONAL/
    # INVESTIGACION_ACCIDENTE.
    ("PERSONAL/REGISTRO DE JORNADA", "REGISTRO_JORNADA"),
    ("DECLARACION AL CORRIENTE", "PAGO_CORRIENTE"),
    ("AUTORIZACION USO DE MAQUINARIA", "AUTORIZACION_USO_MAQUINARIA"),
    # Añadido S55: CERT_ACCESORIO_ELEVACION resuelto por carpeta, no
    # por palabra -- caso real detectado "Cert.revision eslinga cable
    # acero...pdf" dentro de estas carpetas, que colisionaria con la
    # heuristica de CERT_REVISION si se resolviera por palabra clave
    # ("REVISION" aparece en el propio nombre). Solo las 3 carpetas
    # reales sin ambiguedad confirmada (S55, dry-run de
    # run_fase_a_sweep) -- "CERTIFICADOS"/"CERTIFICADOS DE EQUIPOS DE
    # TRABAJO" quedan fuera deliberadamente, son mas genericas y
    # podrian mezclar otros tipos de certificado, pendiente de revision
    # aparte.
    ("ESLINGAS CABLE ACERO", "CERT_ACCESORIO_ELEVACION"),
    ("ESLINGAS HUELVA", "CERT_ACCESORIO_ELEVACION"),
    ("ESLINGAS MINIGRUA", "CERT_ACCESORIO_ELEVACION"),
    # Añadidas S56: calibracion de solo lectura sobre TODO lo ya
    # clasificado (22.231 documentos vivos), cruzando cada segmento de
    # carpeta contra el catalogo real -- candidatas con min. 8
    # documentos y pureza >=97%, filtradas para descartar nombres de
    # persona (no generalizan) y carpetas ya cubiertas por una regla
    # existente (para no proponer reglas redundantes). Cada una
    # verificada contra el documento real antes de confirmarse (ver
    # anexo H30, registro de sesion S56) -- "CURSO 2022" se descarto
    # de esta lista (17 documentos reales resultaron ser listas de
    # examenes de mas de 5 años, sin valor de archivo segun Miguel
    # Angel, enviados a papelera en la misma sesion en vez de
    # convertirse en regla).
    ("ENTREGA INFORMACION", "ENTREGA_INFORMACION"),
    ("RECONOCIMIENTOS MEDICOS", "RECONOCIMIENTO_MEDICO"),
    ("CAPACITACION", "CAP"),
    ("CERT MANTENIMIENTO", "CERT_MANTENIMIENTO"),
    ("CERT. MANTENIMIENTO", "CERT_MANTENIMIENTO"),
    ("CERTIF. MANTENIMIENTOS", "CERT_MANTENIMIENTO"),
    # Confirmada con documento real (Z-04 CERTIFICADO MODELO
    # MANTENIMIENTO MAQUINARIA.docx) -- nomenclatura interna sin
    # explicacion clara ("como Z-13"), pero contenido verificado.
    ("COMO Z-13", "CERT_MANTENIMIENTO"),
    ("AUTOMOMOS", "CSS"),  # errata real de "AUTONOMOS", consistente
    ("NOMINAS", "NOMINA"),
    ("IMPUESTO SOBRE VEHICULOS DE TRACCION MECANICA", "IVTM"),
    ("PARTE DE VACACIONES", "VACACIONES"),
    ("SEGURO 2015 (TR)", "SEGURO"),
    # Confirmada con documento real (2013 02 05 BAJA RAE GRUAS.pdf,
    # formulario oficial "SE SOLICITA LA BAJA DE LA GRUA MOVIL... EN
    # EL REGISTRO DE GRUAS MOVILES", RAE4-MA-29/...).
    ("SOLICITUD BAJA INDUSTRIA", "RAE"),
    # Confirmada con documento real (Resolucion sobre Reconocimiento
    # de Alta, Regimen General, Seguridad Social) pese a la fecha en
    # el nombre de carpeta -- contenido inequivoco.
    ("PARTES ALTA OPERARIOS 27-12-17", "ALTA"),
    # Confirmada con documento real (FORMULARIO SOLICITUD CERTIFICADO
    # NORMA UNE 58161 FORMACION GRUA HIDRAULICA ARTICULADA).
    ("CARNE CAMION AUTOCARGANTE", "FORMACION"),
    # Confirmada con documento real (Idc -- Informe de Datos para la
    # Cotizacion, Tesoreria General de la Seguridad Social).
    ("SEPT 2014", "IDC"),
]


def folder_based_type(entry, domain):
    """
    BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE (dominio
    PERSONAL) y CERT_ACCESORIO_ELEVACION (dominio MACHINE, S55) se
    resuelven por carpeta real, nunca por palabra sola -- se comprueba
    ANTES que la heuristica de nombre.

    CORREGIDO en esta sesion: la decision de S48 de dejar EPIS
    deliberadamente fuera de este recorrido (van a EpiDelivery/
    EpiReview, flujo distinto, confirmado de nuevo por Miguel Angel
    en esta misma sesion) solo estaba implementada en la via de
    palabra clave (EPIS ausente de CANDIDATES_SAFE/CANDIDATES_RISKY).
    Nunca se aplico a esta funcion, que se comprueba ANTES -- efecto
    real detectado tras ampliar la regla de carpeta BAJA_PERSONAL a
    "/BAJAS/": archivos "EPIS ... PEREZ VALVERDE...pdf" dentro de una
    carpeta BAJAS se tipaban como BAJA_PERSONAL por carpeta, saltandose
    la exclusion. La exclusion de EPI debe ser universal a esta
    funcion, no solo a una regla de carpeta concreta -- ninguna regla
    de FOLDER_TYPE_RULES, presente o futura, puede tipar un archivo
    con "EPI" en el nombre. Ver EnterpriseBot_017_GET.txt.

    Corregido S55: esta funcion devolvia None sin comprobar nada para
    cualquier dominio distinto de PERSONAL -- correcto mientras todas
    las reglas de FOLDER_TYPE_RULES eran de personal, pero un bug real
    en cuanto se anadieron las 3 reglas de ESLINGAS (dominio MACHINE):
    nunca llegaban a evaluarse. Las rutas de MACHINE y PERSONAL nunca
    colisionan (viven bajo raices distintas, DOC. MAQUINAS/DOC.
    PERSONAL), asi que comprobar todas las reglas sin filtrar por
    dominio es seguro.
    """
    if "EPI" in _strip_accents(entry.name).upper():
        return None
    path_upper = _strip_accents(entry.parent_path).upper()
    for needle, code in FOLDER_TYPE_RULES:
        if needle.upper() in path_upper:
            return code
    return None


def _match_candidates(entry, domain, candidates_dict, name_upper):
    matched = set()
    # Bug real corregido S48: "SEGURO"/"TACOGRAFO"/"MANDATO" viven bajo
    # la clave "BOTH" del diccionario (aplican a MACHINE y PERSONAL por
    # igual) -- el bucle solo recorria domain in ("MACHINE", "PERSONAL"),
    # asi que nunca se comprobaban, pese a tener coincidencias reales
    # verificadas en la calibracion (SEGURO: 1347, TACOGRAFO: 199,
    # MANDATO: 47). Se comprueban ahora las dos claves para cada
    # dominio real.
    for lookup_domain in (domain, "BOTH"):
        codes = candidates_dict.get(lookup_domain, {})
        for code, phrases in codes.items():
            for phrase in phrases:
                pattern = _build_pattern(_strip_accents(phrase).upper())
                if not pattern.search(name_upper):
                    continue
                excl_phrases = EXCLUSIONS.get(
                    (lookup_domain, code, phrase), [],
                )
                if any(
                    _build_pattern(_strip_accents(p).upper()).search(
                        name_upper,
                    )
                    for p in excl_phrases
                ):
                    continue
                matched.add(code)
    return matched


def resolve_document_type_heuristic(entry, domain, name_upper=None):
    """
    Resuelve el TIPO documental de `entry` por nombre de archivo,
    sin Gemini, sin OCR -- misma heuristica validada contra 11.149
    documentos reales en la Fase A (S48/S49). Comprueba primero
    `folder_based_type()` (BAJA_PERSONAL/PARTE_BAJA_MEDICA/
    INVESTIGACION_ACCIDENTE, por carpeta real), y solo si no aplica
    recurre al framework de candidatos por palabra clave + prioridades.

    Devuelve (code, dossier_pair): `code` es el tipo resuelto sin
    ambiguedad (o None si no se pudo resolver); `dossier_pair` es un
    frozenset de dos codigos cuando se detecta un dosier real
    (documentos distintos escaneados juntos) -- en ese caso `code` es
    siempre None, la decision de papelera/pendiente la toma quien
    llama (ver `apply_quarantine_classification`/`run_fase_a_sweep`).

    `name_upper` es opcional -- si no se pasa, se calcula aqui mismo
    con `_strip_accents(entry.name).upper()` (mismo criterio que
    `run_fase_a_sweep.py`).
    """
    if name_upper is None:
        name_upper = _strip_accents(entry.name).upper()

    folder_code = folder_based_type(entry, domain)
    if folder_code:
        return folder_code, None

    matched = _match_candidates(entry, domain, CANDIDATES_SAFE, name_upper)
    matched |= _match_candidates(
        entry, domain, CANDIDATES_RISKY, name_upper,
    )
    if not matched:
        return None, None

    if len(matched) == 1:
        return next(iter(matched)), None

    # Mas de un candidato -- aplicar framework de prioridades.
    for pair in DOSSIER_PAIRS:
        if pair <= matched:
            return None, pair

    for winner, loser in SPECIFIC_WINS:
        if winner in matched and loser in matched:
            matched = {winner} | (matched - {winner, loser})

    if GENERIC_LOSER in matched and len(matched) > 1:
        matched = matched - {GENERIC_LOSER}

    if "CURSO" in matched and "FORMACION" in matched:
        if _HOUR_PATTERN.search(name_upper):
            matched = matched - {"CURSO"}
        else:
            matched = matched - {"FORMACION"}

    if len(matched) == 1:
        return next(iter(matched)), None

    for pair in UNRESOLVED_PAIRS:
        if pair <= matched:
            return None, None

    # Solape real no cubierto por el framework -- no se adivina.
    return None, None
