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
        return None, None  # (code, is_dossier)

    if len(matched) == 1:
        return next(iter(matched)), False

    # Mas de un candidato -- aplicar framework de prioridades.
    for pair in DOSSIER_PAIRS:
        if pair <= matched:
            return None, True

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
        return next(iter(matched)), False

    for pair in UNRESOLVED_PAIRS:
        if pair <= matched:
            return None, False

    # Solape real no cubierto por el framework -- no se adivina.
    return None, False


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
            "asignados": 0, "dosier": 0, "sin_resolver_tipo": 0,
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
                    code, is_dossier = folder_code, False
                    stats["folder_type"] += 1
                else:
                    code, is_dossier = _resolve_document_type(
                        entry, domain, name_upper,
                    )

                if is_dossier:
                    stats["dosier"] += 1
                    self.stdout.write(
                        "DOSIER  [%s] %s" % (entry.parent_path, entry.name)
                    )
                    if apply_changes:
                        trash_dossier_entry(entry)
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
