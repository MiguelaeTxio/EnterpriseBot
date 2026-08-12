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
  Sin resolver por carpeta -> se deja pendiente para Fase B (OCR,
  ampliacion de alcance confirmada en S48).

BAJA_PERSONAL / PARTE_BAJA_MEDICA / INVESTIGACION_ACCIDENTE se
resuelven por CARPETA real, nunca por la palabra "BAJA" sola (S47).
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    resolve_or_create_machine_asset, trash_dossier_entry,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    CANDIDATES_RISKY, CANDIDATES_SAFE, EXCLUSIONS, BUCKET, MACHINE_ROOT,
    PERSONAL_ROOT, _build_pattern, _files_for_domain, _strip_accents,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from fleet.models import MachineAsset
from document_explorer.models import PersonIdentity

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
    ("DOC_BAJA_DEFINITIVA", "BAJA_DEFINITIVA"),
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
_FOLDER_TYPE_RULES = [
    ("PARTES BAJA ENF.COMUN Y ACC.NO LABORAL", "PARTE_BAJA_MEDICA"),
    ("INVESTIGACION ACCIDENTES", "INVESTIGACION_ACCIDENTE"),
    ("PERSONAL/BAJAS", "BAJA_PERSONAL"),
]


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


def _folder_based_type(entry, domain):
    if domain != "PERSONAL":
        return None
    path_upper = _strip_accents(entry.parent_path).upper()
    for needle, code in _FOLDER_TYPE_RULES:
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


def _resolve_document_type(entry, domain, name_upper):
    matched = _match_candidates(entry, domain, CANDIDATES_SAFE, name_upper)
    matched |= _match_candidates(
        entry, domain, CANDIDATES_RISKY, name_upper,
    )
    if not matched:
        return None, None  # (code, dossier_pair)

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

        stats = {
            "asignados": 0, "dosier_eliminado": 0,
            "dosier_sin_dividir_pendiente": 0, "sin_resolver_tipo": 0,
            "sin_resolver_dominio": 0, "folder_type": 0,
        }

        for domain in ("MACHINE", "PERSONAL"):
            entries = list(_files_for_domain(domain))
            self.stdout.write(
                "--- %s: %d archivos candidatos ---"
                % (domain, len(entries))
            )
            for entry in entries:
                name_upper = _strip_accents(entry.name).upper()

                folder_code = _folder_based_type(entry, domain)
                if folder_code:
                    code, dossier_pair = folder_code, None
                    stats["folder_type"] += 1
                else:
                    code, dossier_pair = _resolve_document_type(
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
                    stats["sin_resolver_dominio"] += 1
                    self.stdout.write(
                        "TIPO OK, DOMINIO SIN RESOLVER  [%s] %s -> %s"
                        % (entry.parent_path, entry.name, code)
                    )
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
