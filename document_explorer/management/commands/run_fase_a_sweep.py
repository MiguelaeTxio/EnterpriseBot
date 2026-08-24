# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_a_sweep.py
"""
H30 (S48) -- recorrido dirigido de Fase A sobre DOC. MAQUINAS y
DOC. PERSONAL (ver ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md, "Hoja de
Ruta para la Siguiente Sesion", punto 1). Sin llamada a Gemini ni OCR
en esta fase (S46) -- solo heuristica de nombre de archivo, ya
calibrada contra el corpus real en `calibrate_fase_a_keywords`.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa lo que HARIA -- no
escribe nada en la base de datos. Con `--apply`, escribe de verdad:
- `document_type`/`domain_content_type`/`domain_object_id` en
  `DocumentIndexEntry` para archivos resueltos sin ambiguedad.
- Manda a papelera (`trash_dossier_entry`, 4.12, nunca toca GCS) los
  archivos detectados como dosier real (documentos distintos
  escaneados juntos -- framework confirmado por Miguel Angel en S48).

Framework de prioridades y dosieres: ver la seccion "COMPLETADAS EN
S48" del anexo H30 para el razonamiento completo con datos reales.
Nunca reescribir este framework de memoria en otra sesion -- leer el
anexo primero.

Resolucion de domain_object:
- MACHINE: `classification_service.resolve_or_create_machine_asset()`
  (ya existente, funciona por carpeta, sin Gemini).
- PERSONAL: `PersonIdentity.folder_path` -- ver docstring de
  `_resolve_person_by_folder()` mas abajo. Nunca crea una identidad
  nueva aqui (eso exige DNI real, fuera de alcance de Fase A).
  Sin resolver por carpeta -> respaldo por nombre real de subcarpeta
  (`_resolve_person_by_name()`, S54), SOLO con coincidencia exacta y
  unica -- ver docstring para el criterio completo. Sin ninguna de
  las dos -> el TIPO se guarda igualmente (S54, desacoplo tipo/
  dominio), el dominio queda pendiente para revision manual/Fase B.

BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE se
resuelven por CARPETA real, nunca por la palabra "BAJA" sola (S47).
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    resolve_or_create_machine_asset, trash_dossier_entry,
)
from document_explorer.heuristic_type_service import (
    folder_based_type, resolve_document_type_heuristic,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET, MACHINE_ROOT, PERSONAL_ROOT, _files_for_domain, _strip_accents,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from fleet.models import MachineAsset
from document_explorer.models import PersonIdentity

# Fecha al final del nombre de subcarpeta real, formatos vistos:
# "15-3-17", "8-10-16" -- d(d)-m(m)-aa(aa) opcional al final.
_TRAILING_DATE_RE = re.compile(r"\s+\d{1,2}-\d{1,2}-\d{2,4}\s*$")


def _build_person_name_index():
    """
    Indice de nombre normalizado -> conjunto de pks de PersonIdentity,
    para resolver INVESTIGACION_ACCIDENTE por el nombre real que
    aparece en la subcarpeta (p.ej. "ALEJO GARCIA 15-3-17"), cuando
    `_resolve_person_by_folder()` no encuentra nada porque la carpeta
    es compartida por fecha de incidente, no la carpeta propia de la
    persona.

    S54, decision explicita de Miguel Angel tras una discusion real
    sobre el riesgo de "adivinar por nombre" (ver anexo H30, bloque de
    INVESTIGACION_ACCIDENTE): SOLO coincidencia exacta y UNICA -- si
    el nombre normalizado no aparece en el indice, o aparece para mas
    de una persona, se deja pendiente para revision manual, nunca se
    asigna con ambiguedad. Verbatim: "Si hay dos que se llamen Alejo
    Garcia, dificilmente nadie va a grabar con ese nombre [...] si ya
    se han puesto Alejo Garcia es porque hay [uno solo]."
    """
    index = {}

    def _add(key, pk):
        key = key.strip()
        if not key:
            return
        index.setdefault(key, set()).add(pk)

    for person in PersonIdentity.objects.all():
        given = _strip_accents(person.given_name or "").upper().strip()
        first = _strip_accents(person.first_surname or "").upper().strip()
        second = _strip_accents(person.second_surname or "").upper().strip()
        if not given or not first:
            continue
        _add(f"{given} {first}", person.pk)
        _add(f"{first} {given}", person.pk)
        if second:
            _add(f"{given} {first} {second}", person.pk)
            _add(f"{first} {second} {given}", person.pk)
            # S57: las carpetas antiguas de RECONOCIMIENTO_MEDICO
            # (RM 2010-2016) solo llevan "apellido1 apellido2", sin
            # nombre de pila -- p.ej. "BURGOS FERNANDEZ",
            # "HIDALGO ROSAS". Confirmado contra datos reales: 145 de
            # 146 RECONOCIMIENTO_MEDICO con dominio pendiente no
            # resolvian por ninguna clave existente porque todas
            # exigian el nombre de pila. Misma proteccion de siempre:
            # esta clave entra en el mismo indice de conjuntos, asi
            # que si dos personas comparten apellido1+apellido2 el
            # tamano del conjunto sube a 2+ y sigue sin resolver solo.
            _add(f"{first} {second}", person.pk)
    return index


def _company_hint_from_path(parent_path):
    """
    Extrae, si existe, una pista de empresa real del Grupo Alvarez a
    partir del propio `parent_path` -- S57, desambiguacion de
    RECONOCIMIENTO_MEDICO cuando dos personas comparten apellido1+
    apellido2 pero pertenecen a empresas distintas del grupo (caso
    real: "RECONOCIMIENTO MEDICOS 2010/GRUAS ALVAREZ/..." vs
    ".../TRANSGRUAL/..." bajo el mismo arbol).

    Nunca decide sola: solo se usa para filtrar candidatos ya
    empatados por nombre en `_resolve_person_by_name()`, comparando
    contra `PersonIdentity.employer_company` (columna EMPRESA real del
    Excel de plantilla, ver H30 S54). Devuelve None si no hay pista
    reconocible en la ruta -- en ese caso el llamador sigue sin poder
    resolver, nunca inventa una empresa.
    """
    upper = _strip_accents(parent_path).upper()
    if "TRANSGRUAL" in upper:
        return "TRANSGRUAL"
    if "GRUALDI" in upper:
        return "GRUALDI"
    if "ALVAREZ" in upper:
        return "ALVAREZ"
    return None


def _resolve_person_by_name(entry, person_name_index):
    """
    Resuelve `PersonIdentity` a partir del nombre real que aparece en
    la subcarpeta inmediata de `entry` (p.ej. "ALEJO GARCIA 15-3-17"
    -> "ALEJO GARCIA"), SOLO si hay exactamente una coincidencia en
    `person_name_index`. Cualquier otro caso (cero o mas de una
    coincidencia) devuelve None -- pendiente de revision manual,
    nunca una decision con ambiguedad.

    Corregido S56: bug real de origen -- la coma real de carpetas con
    formato "APELLIDOS, NOMBRE" (p.ej. "ALVAREZ DIAZ, ADELAIDA") nunca
    se quitaba antes de comparar contra `person_name_index`, cuyas
    claves se construyen siempre sin coma (espacio como unico
    separador) -- ninguna carpeta con coma podia matchear jamas, sea
    cual sea el orden. Confirmado contra datos reales en S56: 269
    documentos RECONOCIMIENTO_MEDICO con dominio pendiente, la mayoria
    con la coma real en el nombre de carpeta.

    Ampliado S57: si el nombre solo (via la clave "apellido1
    apellido2" nueva de `_build_person_name_index()`) empata con MAS
    de una persona, se intenta desambiguar por empresa real usando
    `_company_hint_from_path()` contra `employer_company` -- solo si
    esa segunda pasada deja exactamente UN candidato. Sigue sin
    tolerar ambiguedad: si la pista de empresa no reduce a 1, se
    devuelve None igual que siempre.
    """
    last_segment = entry.parent_path.rstrip("/").split("/")[-1]
    last_segment = last_segment.replace(",", " ")
    candidate = _TRAILING_DATE_RE.sub("", last_segment)
    candidate = _strip_accents(candidate).upper().strip()
    candidate = re.sub(r"\s+", " ", candidate)
    pks = person_name_index.get(candidate)
    if not pks:
        return None
    if len(pks) == 1:
        return PersonIdentity.objects.get(pk=next(iter(pks)))

    hint = _company_hint_from_path(entry.parent_path)
    if hint:
        narrowed = [
            p for p in PersonIdentity.objects.filter(pk__in=pks)
            if hint in _strip_accents(p.employer_company or "").upper()
        ]
        if len(narrowed) == 1:
            return narrowed[0]
    return None


# Patron real "APELLIDO1 APELLIDO2,NOMBRE" (coma sin espacio, o con
# espacio antes/despues) dentro de un NOMBRE DE ARCHIVO, no de una
# carpeta -- p.ej. "Control Horarios BAENA MARQUEZ,DANIEL (GR).xlsx".
# Captura los DOS tokens inmediatamente anteriores a la coma (los
# apellidos reales, ignorando cualquier texto descriptivo delante,
# tipo "Control Horarios") y el token inmediatamente posterior (el
# nombre de pila).
_FILENAME_COMMA_PATTERN_RE = re.compile(
    r"([A-Za-zÁÉÍÓÚÑÜáéíóúñü]+)\s+([A-Za-zÁÉÍÓÚÑÜáéíóúñü]+)\s*,\s*"
    r"([A-Za-zÁÉÍÓÚÑÜáéíóúñü]+)"
)


def _resolve_person_by_filename_comma_pattern(entry, person_name_index):
    """
    H30 (S64) -- cuarto resolutor, entre `_resolve_person_by_name()` y
    `_resolve_person_by_sliding_window()`. Cubre el patron real
    "APELLIDO1 APELLIDO2,NOMBRE" cuando vive en el NOMBRE DE ARCHIVO
    (no en la carpeta contenedora, que ya cubre `_resolve_person_by_
    name()`), tipico de REGISTRO_JORNADA ("Control Horarios BAENA
    MARQUEZ,DANIEL (GR).xlsx").

    Motivo real, confirmado con datos de produccion en S64:
    `_resolve_person_by_sliding_window()` tokeniza sin respetar la
    coma, asi que "BAENA MARQUEZ,DANIEL" genera ventanas sueltas de 2
    palabras ("BAENA MARQUEZ", "MARQUEZ DANIEL") que pueden colisionar
    con personas reales DISTINTAS cuando el apellido2 de una persona
    coincide con el apellido1 de otra -- caso real: "BAENA
    MARQUEZ,DANIEL" genera la ventana "MARQUEZ DANIEL", que matchea
    contra DANIEL MARQUEZ SANCHEZ (pk real distinto de DANIEL BAENA
    MARQUEZ). La ambiguedad resultante (dos personas en found_pks)
    hace que la ventana deslizante devuelva None por diseno -- nunca
    arriesga --, aunque el nombre completo con coma sea inequivoco.

    Esta funcion reconstruye la clave completa "apellido1 apellido2
    nombre" respetando la coma (mismo formato de clave de tres
    palabras que ya genera `_build_person_name_index()`), evitando asi
    la ambiguedad de ventanas sueltas de 2 palabras. Solo resuelve si
    hay coincidencia EXACTA y UNICA en el indice -- mismo criterio de
    siempre, nunca decide con ambiguedad.
    """
    file_stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", entry.name)
    match = _FILENAME_COMMA_PATTERN_RE.search(file_stem)
    if not match:
        return None

    apellido1, apellido2, nombre = match.groups()
    candidate = _strip_accents(
        f"{apellido1} {apellido2} {nombre}"
    ).upper().strip()
    candidate = re.sub(r"\s+", " ", candidate)

    pks = person_name_index.get(candidate)
    if pks and len(pks) == 1:
        return PersonIdentity.objects.get(pk=next(iter(pks)))
    return None


# Separador de tokens para la ventana deslizante: cualquier cosa que
# no sea letra/digito rompe palabra (coma, parentesis, guion, punto).
_TOKEN_SPLIT_RE = re.compile(r"[^A-Z0-9]+")


def _tokenize_segment(segment):
    """
    Normaliza un segmento de ruta o de nombre de archivo (sin
    extension) a una lista de palabras en mayusculas sin acentos,
    para la ventana deslizante de `_resolve_person_by_sliding_
    window()`.
    """
    upper = _strip_accents(segment).upper()
    return [t for t in _TOKEN_SPLIT_RE.split(upper) if t]


def _resolve_person_by_sliding_window(entry, person_name_index):
    """
    Bloque 4 de S56 (hoja de ruta punto 6, hasta ahora un script
    suelto, no reutilizable) -- ultimo recurso cuando ni `_resolve_
    person_by_folder()` ni `_resolve_person_by_name()` (que solo miran
    el ultimo segmento de carpeta) encuentran nada.

    Motivo real (S56): mucho backlog historico (RECONOCIMIENTOS
    MEDICOS 2010-2016) lleva el nombre real de la persona en el
    NOMBRE DE ARCHIVO, no en la carpeta contenedora -- carpetas
    genericas como "GRUAS ALVAREZ/BYN GRUAS" o "TRANSGRUAL/COLOR"
    agrupan por empresa/formato de escaneo, no por trabajador.

    REDISEÑADO EN S64 -- dos pasadas, no una sola mezclando todo:

    PASADA 1 -- SOLO el nombre de archivo (sin extension), tokenizado
    en aislado. Si resuelve a una unica persona, se devuelve
    directamente, SIN tocar ningun segmento de carpeta. Motivo real
    (S64): la carpeta de empresa real "GRUAS ADOLFO ALVAREZ" contiene
    "ADOLFO ALVAREZ", que matchea de verdad contra `PersonIdentity`
    pk=4 (Adolfo Alvarez Diaz, el administrador) -- mezclar esa
    carpeta con el nombre de archivo real de OTRA persona
    (p.ej. "REGISTRO DE JORNADA MANUEL DELGADO ZURERA FIRMADO.pdf")
    metia siempre un segundo pk falso en `found_pks`, viendo ambiguedad
    donde no la habia, y dejando sin resolver CUALQUIER archivo bajo
    esa carpeta de empresa, aunque el nombre de archivo por si solo
    fuera inequivoco. Confirmado con datos reales: "MANUEL DELGADO
    ZURERA", "MONICA CARVAJAL RODRIGUEZ", "CARVAJAL GONZALEZ
    FRANCISCO", "RUIZ LEIVA ANTONIO" resuelven todos a un unico
    candidato mirando solo el nombre de archivo.

    PASADA 2 -- si la pasada 1 no resuelve (cero o varias personas
    solo con el archivo), recorre TODOS los segmentos de
    `entry.parent_path` ademas del nombre de archivo, igual que antes
    -- caso original de S56, nombre real que vive SOLO en la carpeta
    (backlog historico de RECONOCIMIENTOS MEDICOS). Con una excepcion
    nueva, S64, decision explicita de Miguel Angel: cualquier segmento
    de carpeta que contenga a la vez "GRUAS" y "ALVAREZ" (palabra
    completa) se excluye del recorrido -- son carpetas de empresa
    reales ("GRUAS ADOLFO ALVAREZ", "GRUAS ALVAREZ"), nunca carpetas
    de persona (ninguna carpeta real de trabajador de la plantilla
    combina esas dos palabras). Deliberadamente NO se excluye
    "ALVAREZ" a secas -- es primer apellido real y muy comun en la
    plantilla (ALVAREZ SERRANO, ALVAREZ GEA, ALVAREZ VIEIRA...),
    excluirlo sin el marcador "GRUAS" tumbaria carpetas de persona
    legitimas.

    Mismo criterio de siempre en ambas pasadas, sin excepcion: si el
    conjunto final tiene mas de una persona (dos ventanas distintas
    apuntan a gente distinta, o dos personas comparten el mismo
    apellido1+apellido2 -- el caso real de hermanos que Miguel Angel
    confirmo en S57) devuelve None, nunca elige al azar. Solo un
    candidato -> se resuelve.
    """
    file_stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", entry.name)

    def _windows_pks(segment):
        segment = _TRAILING_DATE_RE.sub("", segment)
        tokens = _tokenize_segment(segment)
        pks = set()
        for size in (2, 3, 4):
            if size > len(tokens):
                continue
            for start in range(0, len(tokens) - size + 1):
                window = " ".join(tokens[start:start + size])
                found = person_name_index.get(window)
                if found:
                    pks |= found
        return pks

    # PASADA 1 -- solo el nombre de archivo, aislado.
    solo_archivo = _windows_pks(file_stem)
    if len(solo_archivo) == 1:
        return PersonIdentity.objects.get(pk=next(iter(solo_archivo)))

    # PASADA 2 -- recorrido completo, excluyendo carpetas de empresa
    # reales que combinan GRUAS + ALVAREZ.
    segments = [
        seg for seg in entry.parent_path.split("/") if seg.strip()
    ]
    segments.append(file_stem)

    found_pks = set()
    for segment in segments:
        upper = _strip_accents(segment).upper()
        if (
            re.search(r"\bGRUAS\b", upper)
            and re.search(r"\bALVAREZ\b", upper)
        ):
            continue
        found_pks |= _windows_pks(segment)

    if len(found_pks) == 1:
        return PersonIdentity.objects.get(pk=next(iter(found_pks)))
    return None


def _resolve_person_by_folder(entry):
    """
    Resuelve `PersonIdentity` para un archivo PERSONAL de Fase A
    comparando `entry.parent_path` contra `PersonIdentity.folder_path`
    ya sembrado (por DNI, en su momento) -- nunca por parecido de
    nombre (el propio modelo lo prohibe explicitamente). `folder_path`
    es la carpeta CONTENEDORA de la persona; un archivo resuelve si su
    `parent_path` es exactamente esa carpeta o vive dentro de ella.

    Nunca crea una `PersonIdentity` nueva -- eso exige DNI real
    (fuera de alcance de Fase A, ver `resolve_or_create_person_
    identity`). Sin coincidencia -> None, queda pendiente para Fase B
    (OCR, ampliacion S48).
    """
    path = entry.parent_path
    contained = PersonIdentity.objects.filter(
        folder_path__in=[
            "/".join(path.split("/")[:i])
            for i in range(1, len(path.split("/")) + 1)
        ],
    )
    ids = {p.pk for p in contained}
    if len(ids) == 1:
        return contained[0]
    return None


def _dossier_types_already_filed(obj, content_type, pair):
    """
    True solo cuando CADA tipo del par de dosier ya tiene, para este
    mismo `obj` (maquina/persona), al menos una fila real archivada
    fuera de cuarentena (`document_type` asignado, dentro de
    `DOC. MAQUINAS`/`DOC. PERSONAL`, no borrada ni purgada).

    H30 (S49). Corrige un fallo real: `DOSSIER_PAIRS` mandaba a
    papelera cualquier archivo con dos tipos candidatos a la vez, sin
    comprobar si esos dos documentos ya existian por separado en algun
    otro sitio. Miguel Angel, verbatim (S49), confirmando que la regla
    de siempre exige esa comprobacion: "Siempre y cuando los
    documentos separados esten, el dosier se puede eliminar. Pero si
    no hay documentos separados, ese dosier no se puede eliminar."

    Si `obj` no se pudo resolver, o si algun tipo del par no tiene
    todavia una fila separada archivada, devuelve False -- nunca se
    elimina un dosier que podria ser la unica copia real de ese
    contenido.
    """
    if obj is None:
        return False
    for code in pair:
        exists = DocumentIndexEntry.objects.filter(
            domain_content_type=content_type, domain_object_id=obj.pk,
            document_type__code=code,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).exclude(parent_path__startswith="_CUARENTENA").exists()
        if not exists:
            return False
    return True


class Command(BaseCommand):
    help = (
        "H30 (S48) -- Fase A: recorrido dirigido con heuristica de "
        "nombre. Dry-run por defecto, usar --apply para escribir de "
        "verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        type_catalog = {
            t.code: t
            for t in DocumentTypeCatalog.objects.filter(is_active=True)
        }
        person_name_index = _build_person_name_index()

        stats = {
            "asignados": 0, "dosier_eliminado": 0,
            "dosier_sin_dividir_pendiente": 0, "sin_resolver_tipo": 0,
            "tipo_ok_dominio_pendiente": 0, "folder_type": 0,
        }

        for domain in ("MACHINE", "PERSONAL"):
            entries = list(_files_for_domain(domain))
            self.stdout.write(
                "--- %s: %d archivos candidatos ---"
                % (domain, len(entries))
            )
            for entry in entries:
                name_upper = _strip_accents(entry.name).upper()

                folder_code = folder_based_type(entry, domain)
                if folder_code:
                    code, dossier_pair = folder_code, None
                    stats["folder_type"] += 1
                else:
                    code, dossier_pair = resolve_document_type_heuristic(
                        entry, domain, name_upper,
                    )

                if dossier_pair:
                    if domain == "MACHINE":
                        obj = resolve_or_create_machine_asset(entry, {})
                        ct = machine_ct
                    else:
                        obj = _resolve_person_by_folder(entry)
                        ct = person_ct

                    if _dossier_types_already_filed(obj, ct, dossier_pair):
                        stats["dosier_eliminado"] += 1
                        self.stdout.write(
                            "DOSIER ELIMINADO (ya dividido en %s) [%s] %s"
                            % (
                                sorted(dossier_pair), entry.parent_path,
                                entry.name,
                            )
                        )
                        if apply_changes:
                            trash_dossier_entry(entry)
                    else:
                        stats["dosier_sin_dividir_pendiente"] += 1
                        self.stdout.write(
                            "DOSIER SIN DIVIDIR, NO SE ELIMINA (revision "
                            "manual) [%s] %s -> %s"
                            % (
                                entry.parent_path, entry.name,
                                sorted(dossier_pair),
                            )
                        )
                    continue

                if not code:
                    stats["sin_resolver_tipo"] += 1
                    continue

                if domain == "MACHINE":
                    asset = resolve_or_create_machine_asset(entry, {})
                    obj, ct = asset, machine_ct
                else:
                    obj = _resolve_person_by_folder(entry)
                    ct = person_ct
                    if not obj:
                        obj = _resolve_person_by_name(
                            entry, person_name_index,
                        )
                    if not obj:
                        obj = _resolve_person_by_sliding_window(
                            entry, person_name_index,
                        )

                if not obj:
                    stats["tipo_ok_dominio_pendiente"] += 1
                    self.stdout.write(
                        "TIPO OK, DOMINIO PENDIENTE -- tipo guardado ya, "
                        "dominio se resuelve aparte  [%s] %s -> %s"
                        % (entry.parent_path, entry.name, code)
                    )
                    if apply_changes:
                        entry.document_type = type_catalog[code]
                        entry.save(update_fields=["document_type"])
                    continue

                stats["asignados"] += 1
                if apply_changes:
                    entry.document_type = type_catalog[code]
                    entry.domain_content_type = ct
                    entry.domain_object_id = obj.pk
                    entry.save(update_fields=[
                        "document_type", "domain_content_type",
                        "domain_object_id",
                    ])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
