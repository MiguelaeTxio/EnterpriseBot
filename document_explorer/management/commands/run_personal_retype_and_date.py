# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_personal_retype_and_date.py
"""
H31 (S104). Tanda unica de relectura con Cloud Vision para el dominio
PERSONAL, cerrando dos hallazgos reales de esta sesion sin volver a
tocar VMs de OCR ni Tesseract -- decision explicita de Miguel Angel
tras el fallo garrafal de las reglas de carpeta/nombre de archivo
("no podemos ni mirar el nombre, no podemos mirar la carpeta [...]
lo que tenemos que hacer es mirar el archivo, leerlo y clasificarlo"):

1. Fecha de nacimiento colada como issue_date -- 9 tipos documentales
   distintos de trabajadores activos donde el pipeline historico
   guardo la fecha de nacimiento de la persona en vez de la fecha real
   del documento (H28, anterior a la proteccion _BIRTHDATE_CONTEXT que
   ya existe en date_verification_service.classify_dates_in_text).
2. Documentos mal TIPADOS de origen (no solo mal fechados) -- 44% real
   confirmado en la muestra de BAJA_PERSONAL/PARTE_BAJA_MEDICA de esta
   misma sesion (Tarjeta Sanitaria, DNI, Carnet de Conducir, Nomina,
   Reconocimiento Medico... archivados bajo un tipo que no les
   corresponde).

Unico motor de lectura: `date_verification_service.extract_text()`
(texto embebido del PDF -> Cloud Vision -- NUNCA Tesseract/VMs,
decision S102 reafirmada explicitamente en esta sesion). Deliberado:
este comando SIEMPRE pide una lectura fresca, incluso si `ocr_text` ya
tenia algo cacheado -- el alcance son justo los archivos donde ese
texto previo (de un pipeline mas antiguo, no Cloud Vision) ya
demostro ser insuficiente. El texto nuevo se cachea igualmente en
`ocr_text` (mismo campo/convencion que `subject_upload_service.py`)
para que futuras herramientas SI puedan reutilizarlo sin gastar otra
llamada.

Alcance (una sola query, sin listas de pk hardcodeadas -- reutilizable
en sesiones futuras): cualquier DocumentIndexEntry de PersonIdentity
activa, tipo con tracks_expiry=True, y O BIEN sin ninguna fecha O BIEN
con issue_date/expiry_date igual a la fecha de nacimiento de esa
persona (con o sin el error de siglo +100 anios) -- ese segundo brazo
es lo que detecta el caso 1 de arriba sin depender de que ya se supiera
la lista de personas afectadas.

CONTENT_SIGNALS / CONTENT_WINS (abajo): igual principio que
CONTENT_MARKERS de `run_fase_b1_ocr_classify.py` -- frases largas y
especificas confirmadas contra documentos reales de esta sesion, nunca
palabras sueltas. Dos trampas reales encontradas y ya corregidas aqui:
"IDESP" aparece en el DNI, el NIE e incluso el permiso de conducir
español (zona MRZ/franja inferior) -- nunca decisivo por si solo. La
frase "RECONOCIMIENTO MEDICO" aparece como ETIQUETA DE CAMPO dentro del
propio formulario oficial "PARTE MEDICO DE BAJA/ALTA/CONFIRMACION DE
INCAPACIDAD TEMPORAL" -- PARTE_BAJA_MEDICA gana siempre sobre
RECONOCIMIENTO_MEDICO cuando aparece la cabecera de ese formulario.

DRY-RUN POR DEFECTO. `--limit N` (defecto 40 -- Cloud Vision es una
llamada de red real por documento). `--apply` escribe de verdad
document_type/issue_date/expiry_date/ocr_text y renombra
canonicamente via `apply_personal_canonical_rename()` (fecha real
encontrada, o el placeholder 2021-01-01 de Miguel Angel si el tipo
queda resuelto pero la fecha sigue sin verse clara).
---
H31 (S104). Single Cloud Vision re-read batch for the PERSONAL domain,
closing two real findings from this session without touching OCR VMs
or Tesseract again -- Miguel Angel's explicit decision after the
folder/filename-rule failure ("we can't even look at the name, we
can't look at the folder [...] what we have to do is look at the
file, read it and classify it"):

1. Birth date leaked as issue_date -- 9 different document types of
   active workers where the historical pipeline stored the person's
   birth date instead of the document's real date (H28, predates the
   _BIRTHDATE_CONTEXT guard that already exists in
   date_verification_service.classify_dates_in_text).
2. Documents mis-TYPED at the source (not just mis-dated) -- a
   confirmed real 44% in this session's BAJA_PERSONAL/
   PARTE_BAJA_MEDICA sample (Health card, DNI, Driving licence,
   Payslip, Medical exam... filed under a type that isn't theirs).

Single reading engine: `date_verification_service.extract_text()`
(PDF embedded text -> Cloud Vision -- NEVER Tesseract/VMs, S102
decision explicitly reaffirmed this session). Deliberate: this command
ALWAYS requests a fresh read, even when `ocr_text` already had
something cached -- the scope is precisely the files where that prior
text (from an older, non-Cloud-Vision pipeline) already proved
insufficient. The new text is still cached back to `ocr_text` (same
field/convention as `subject_upload_service.py`) so future tools CAN
reuse it without spending another call.

Scope (a single query, no hardcoded pk lists -- reusable in future
sessions): any DocumentIndexEntry of an active PersonIdentity, type
with tracks_expiry=True, and EITHER no date at all OR issue_date/
expiry_date equal to that person's birth date (with or without the
+100 year century error) -- that second arm is what catches case 1
above without depending on already knowing which people were
affected.

CONTENT_SIGNALS / CONTENT_WINS (below): same principle as
CONTENT_MARKERS in `run_fase_b1_ocr_classify.py` -- long, specific
phrases confirmed against real documents from this session, never
loose words. Two real traps found and already fixed here: "IDESP"
shows up on the DNI, the NIE, and even the Spanish driving licence
(MRZ/bottom strip) -- never decisive alone. The phrase "RECONOCIMIENTO
MEDICO" appears as a FIELD LABEL inside the official "PARTE MEDICO DE
BAJA/ALTA/CONFIRMACION DE INCAPACIDAD TEMPORAL" form itself --
PARTE_BAJA_MEDICA always wins over RECONOCIMIENTO_MEDICO when that
form's header is present.

DRY-RUN BY DEFAULT. `--limit N` (default 40 -- Cloud Vision is a real
network call per document). `--apply` really writes document_type/
issue_date/expiry_date/ocr_text and canonically renames via
`apply_personal_canonical_rename()` (the real date found, or Miguel
Angel's 2021-01-01 placeholder if the type resolves but the date is
still unclear).
"""
from datetime import date
import difflib
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.db.models import Q

from document_explorer.classification_service import (
    apply_personal_canonical_rename,
)
from document_explorer.date_verification_service import (
    _strip_accents, classify_dates_in_text, extract_expiry_via_gemini,
    extract_text,
)
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

FICTITIOUS_DATE = date(2021, 1, 1)

# H31 (S104), corregido tras revisar muestras reales con Miguel Angel:
# "FICHA DE INSCRIPCION" con el numero de horas en el propio titulo del
# curso ("20H PRL...", "6H PRL...") es la senal real y fiable de
# FORMACION (coincide letra a letra con la definicion del propio
# catalogo, "Formacion (2H/6H/60H)") -- nunca "ACCION FORMATIVA"/
# "DIPLOMA" sueltos, que salian igual de bien en documentos de CURSO
# real y producian el ambiguo CURSO/FORMACION visto en el primer lote.
_FORMACION_HOURS_RE = re.compile(r"\b\d{1,3}\s*H\b")

# Frases largas y especificas, confirmadas contra documentos reales de
# esta sesion (nunca palabras sueltas -- ver incidentes "IDESP" y
# "RECONOCIMIENTO MEDICO" en el docstring de arriba). "IBAN" se retira
# como senal de CERTIFICADO_BANCARIO (S104, muestra real): aparecia
# como falso positivo en fichas de formacion que solo citan un IBAN de
# pago, nunca en un certificado bancario real -- sin sustituto todavia,
# queda pendiente de una frase mas especifica.
CONTENT_SIGNALS = {
    "TARJETA_SANITARIA": [
        "TARJETA SANITARIA INDIVIDUAL", "NUMERO DE HISTORIA UNICA DE SALUD",
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
    "CURSO": ["CERTIFICADO DE APROVECHAMIENTO", "DIPLOMA"],
    "FORMACION": ["FICHA DE INSCRIPCION"],
    "CARNET_CONDUCIR": ["PERMISO DE CONDUCCION", "DRIVING LICENCE"],
    "CARNET_GRUISTA": [
        "OPERADOR DE GRUAS MOVILES", "HABILITACION PROFESIONAL",
        "CARNE DE OPERADOR DE GRUAS",
    ],
    "PARTE_BAJA_MEDICA": [
        "PARTE MEDICO DE BAJA", "PARTE MEDICO DE ALTA",
        "PARTE MEDICO DE CONFIRMACION DE INCAPACIDAD",
        "PARTE DE BAJA", "INCAPACIDAD TEMPORAL",
    ],
    "CERTIFICADO_BANCARIO": ["CERTIFICADO DE TITULARIDAD"],
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
]

# H31 (S104), hallazgo real: algunos PDF de la migracion historica son
# formularios dinamicos de Adobe (XFA) -- el texto que devuelve
# cualquier extractor (embebido o Cloud Vision sobre el render
# estatico) es solo el aviso generico de "tu lector no soporta este
# documento", nunca el contenido real. Ninguna regla de contenido
# puede resolver esto -- se detecta aparte y se deja fuera del
# retipado/fechado automatico, nunca se cuenta como "sin señal".
_ADOBE_DYNAMIC_PLACEHOLDER = "PLEASE WAIT"


def _resolve_type_from_content(text_upper, current_code):
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
    """
    matched = set()
    for code, phrases in CONTENT_SIGNALS.items():
        for phrase in phrases:
            if phrase in text_upper:
                matched.add(code)
                break
    if "FORMACION" in matched and not _FORMACION_HOURS_RE.search(text_upper):
        matched.discard("FORMACION")
    for winner, loser in CONTENT_WINS:
        if winner in matched and loser in matched:
            matched.discard(loser)
    if len(matched) == 1:
        return next(iter(matched)), False, matched
    if len(matched) > 1:
        return None, True, matched
    return None, False, matched


def _person_name_missing(text_upper, person):
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
    daba demasiados falsos positivos reales (pk=27804/27808/27928--
    el apellido SI estaba en el documento, pero el OCR lo devolvio tan
    degradado -- "ADQLFO PlvAREZ DI=" en vez de "ADOLFO ALVAREZ DIAZ"
    -- que ninguna comparacion exacta lo reconocia). Ahora se acepta
    tambien una coincidencia aproximada (SequenceMatcher, ratio>=0.72)
    contra cualquier palabra suficientemente larga (>=4 caracteres) del
    texto, mismo umbral de tolerancia a ruido de OCR que
    `_fuzzy_match_worker` ya usa en otra parte de la plataforma para
    el mismo problema (analytics/views.py).
    """
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


class Command(BaseCommand):
    help = (
        "H31 (S104) -- releer con Cloud Vision y retipar/fechar en una "
        "sola tanda los documentos de Personal con fecha de nacimiento "
        "colada o sin fecha en absoluto. Dry-run por defecto, --apply "
        "para escribir, --limit N (defecto 40)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=40)

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]

        ct = ContentType.objects.get_for_model(PersonIdentity)
        type_catalog = {
            t.code: t for t in DocumentTypeCatalog.objects.filter(is_active=True)
        }
        active_people = {
            p.pk: p
            for p in PersonIdentity.objects.filter(is_active_employee=True)
        }

        no_date = Q(issue_date__isnull=True, expiry_date__isnull=True)
        birthdate_leak = None
        for pk, person in active_people.items():
            if not person.birth_date:
                continue
            bad = (person.birth_date, person.birth_date.replace(
                year=person.birth_date.year + 100,
            ))
            clause = Q(domain_object_id=pk) & (
                Q(issue_date__in=bad) | Q(expiry_date__in=bad)
            )
            birthdate_leak = clause if birthdate_leak is None else birthdate_leak | clause

        scope = no_date if birthdate_leak is None else (no_date | birthdate_leak)
        qs = DocumentIndexEntry.objects.filter(
            domain_content_type=ct, domain_object_id__in=active_people.keys(),
            document_type__tracks_expiry=True,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(scope).select_related(
            "document_type",
        ).order_by("id")[:limit]

        candidatos = list(qs)
        self.stdout.write(
            "--- H31-S104 retipado+fechado Cloud Vision: %d candidatos "
            "en este lote (limit=%d) ---" % (len(candidatos), limit)
        )

        reserved = set()
        stats = {
            "tipo_y_fecha_resueltos": 0,
            "solo_fecha_resuelta": 0,
            "solo_tipo_resuelto": 0,
            "tipo_ambiguo": 0,
            "sin_nada_resoluble": 0,
            "posible_persona_equivocada": 0,
            "pdf_dinamico_sin_texto": 0,
            "texto_vacio_o_ilegible": 0,
            "extension_no_soportada": 0,
            "error_descarga_u_ocr": 0,
        }

        for entry in candidatos:
            close_old_connections()
            person = active_people.get(entry.domain_object_id)
            bad_dates = set()
            if person and person.birth_date:
                bad_dates = {
                    person.birth_date,
                    person.birth_date.replace(
                        year=person.birth_date.year + 100,
                    ),
                }

            # Deliberado: SIEMPRE se pide una lectura fresca aqui, nunca
            # se reutiliza entry.ocr_text si ya existe -- el alcance de
            # este comando son precisamente los archivos donde el texto
            # ya cacheado (de un pipeline mas antiguo, no Cloud Vision)
            # demostro ser insuficiente en el Comando S de esta misma
            # sesion. Reutilizarlo repetiria el mismo resultado pobre.
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text = extract_text(entry.name, data)
            except Exception as exc:
                stats["error_descarga_u_ocr"] += 1
                self.stdout.write(
                    "ERROR [%s] %s -- %s"
                    % (entry.parent_path, entry.name, exc)
                )
                continue
            if text is None:
                stats["extension_no_soportada"] += 1
                continue

            # H31 (S104), hallazgo real: algunos PDF de la migracion
            # historica son formularios dinamicos de Adobe (XFA) --
            # ningun extractor (embebido ni Cloud Vision) devuelve mas
            # que el aviso generico de "tu lector no soporta este
            # documento". Se detecta aparte, antes de cualquier otra
            # comprobacion -- ni es un problema de persona ni de tipo,
            # es que no hay nada real que leer con este mecanismo.
            if _ADOBE_DYNAMIC_PLACEHOLDER in (text or "").upper():
                stats["pdf_dinamico_sin_texto"] += 1
                self.stdout.write(
                    "PDF DINAMICO (Adobe XFA), sin texto real -- SIN "
                    "TOCAR [pk=%s] %s" % (entry.pk, entry.name)
                )
                continue
            if len((text or "").strip()) < 20:
                stats["texto_vacio_o_ilegible"] += 1
                self.stdout.write(
                    "TEXTO VACIO O CASI VACIO -- SIN TOCAR [pk=%s] %s "
                    "(longitud=%d)" % (entry.pk, entry.name, len(text or ""))
                )
                continue

            if apply_changes and text:
                entry.ocr_text = text
                entry.save(update_fields=["ocr_text"])

            text_upper = _strip_accents(text or "").upper()
            current_code = (
                entry.document_type.code if entry.document_type_id else None
            )

            # H31 (S104), corregido tras incidente real en el propio
            # dry-run (pk=25140): el aviso de persona equivocada debe
            # BLOQUEAR cualquier retipado/fechado de esta entrada, no
            # solo mencionarlo de pasada -- de lo contrario un
            # documento ya sospechoso de estar archivado bajo la
            # persona equivocada se retipa igual en la misma pasada.
            # Se comprueba ANTES de resolver tipo/fecha, nunca despues.
            if person and _person_name_missing(text_upper, person):
                stats["posible_persona_equivocada"] += 1
                self.stdout.write(
                    "PERSONA EQUIVOCADA -- SIN TOCAR [pk=%s] %s -- ni "
                    "%r ni %r aparecen en el texto extraido (ni exacto "
                    "ni aproximado)"
                    % (
                        entry.pk, entry.name, person.first_surname,
                        person.second_surname,
                    )
                )
                continue

            new_code, is_ambiguous, matched = _resolve_type_from_content(
                text_upper, current_code,
            )

            expiry, issue, other = classify_dates_in_text(text or "")
            date_field, date_value = None, None
            if expiry:
                date_field, date_value = "expiry_date", expiry
            elif issue:
                date_field, date_value = "issue_date", issue
            elif len(other) == 1:
                date_field, date_value = "issue_date", other[0]
            if date_value and date_value in bad_dates:
                date_field, date_value = None, None

            # H31 (S104), hallazgo real de esta sesion: los tipos con
            # ocr_unreliable=True (DNI, NIE, CARNET_CONDUCIR,
            # TARJETA_CUALIF_CONDUCTOR, TACOGRAFO -- tarjetas fisicas
            # con fondo de seguridad) nunca se fian del motor de
            # reglas para la fecha, aunque haya devuelto algo -- se
            # sustituye siempre por extract_expiry_via_gemini(), unico
            # camino ya validado en la plataforma para este tipo de
            # documento (ver date_verification_service.py).
            resolved_type_code = new_code or current_code
            effective_type = type_catalog.get(resolved_type_code)
            if effective_type and effective_type.ocr_unreliable:
                gemini_expiry = extract_expiry_via_gemini(data, entry.name)
                date_field, date_value = (
                    ("expiry_date", gemini_expiry) if gemini_expiry else (None, None)
                )

            type_changed = bool(new_code and new_code != current_code)

            if is_ambiguous:
                stats["tipo_ambiguo"] += 1
                self.stdout.write(
                    "TIPO AMBIGUO %s [pk=%s] %s (actual=%s)"
                    % (sorted(matched), entry.pk, entry.name, current_code)
                )
                continue

            if not resolved_type_code:
                stats["sin_nada_resoluble"] += 1
                self.stdout.write(
                    "SIN TIPO NI SEÑAL [pk=%s] %s" % (entry.pk, entry.name)
                )
                continue

            if type_changed and date_value:
                stats["tipo_y_fecha_resueltos"] += 1
            elif type_changed:
                stats["solo_tipo_resuelto"] += 1
            elif date_value:
                stats["solo_fecha_resuelta"] += 1
            else:
                stats["sin_nada_resoluble"] += 1

            self.stdout.write(
                "OK [pk=%s] %s -- tipo: %s%s -- fecha: %s%s"
                % (
                    entry.pk, entry.name,
                    current_code, (" -> %s" % new_code) if type_changed else " (confirmado)",
                    date_field or "sin resolver", (" = %s" % date_value) if date_value else "",
                )
            )

            if apply_changes:
                if type_changed:
                    entry.document_type = type_catalog[new_code]
                    entry.save(update_fields=["document_type"])
                if date_value:
                    setattr(entry, date_field, date_value)
                    entry.save(update_fields=[date_field])
                rename_kwargs = {"apply_changes": True, "reserved_names": reserved}
                if not (entry.issue_date or entry.expiry_date):
                    rename_kwargs["fictitious_date"] = FICTITIOUS_DATE
                apply_personal_canonical_rename(entry, **rename_kwargs)

        self.stdout.write("=== RESUMEN (%s, limit=%d) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito", limit,
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
