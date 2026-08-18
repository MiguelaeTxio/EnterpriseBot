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
    ("PROFORMA", "DOC_VENTA"),
    ("CONTRATO_COMPRAVENTA", "DOC_VENTA"),
    ("ITV", "FICHA_TECNICA"),
    ("PERMISO_CIRCULACION", "DOC_VENTA"),
    ("PERMISO_CIRCULACION", "FICHA_TECNICA"),
    ("RECIBO_LEASING", "LEASING"),
    ("ALTA_MEDICA", "ALTA"),
    ("ALTA", "SEG_SOCIAL"),
    ("CURSO", "TACOGRAFO"),
    # Añadida S49, confirmada por Miguel Angel: una factura entre dos
    # terceros (ninguno es la empresa) sigue siendo, para todos los
    # efectos, una factura de compra ligada al vehiculo/maquina -- no
    # tiene sentido un tipo aparte solo porque la empresa no sea parte
    # directa. FACTURA_TERCEROS queda para casos donde de verdad no
    # aplique FACTURA_COMPRA, nunca cuando ambas coinciden.
    ("FACTURA_COMPRA", "FACTURA_TERCEROS"),
]
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
]


def folder_based_type(entry, domain):
    """
    BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE se
    resuelven por carpeta real, nunca por la palabra "BAJA" sola
    (S47) -- se comprueba ANTES que la heurística de nombre.
    """
    if domain != "PERSONAL":
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
