# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/person_facts_service.py
"""
Personnel file facts read from the person's own documents (S145, made
a service in S148).

---

Datos de la ficha de una persona leídos de sus propios documentos.
S145 los sacó en un comando de una sola pasada
(`fill_person_fields_from_documents`); S148 (Miguel Ángel: "mejorar el
pipeline de extracción de información para dejar la base de datos
correcta a través de los documentos que se cargan") los lleva también
a cada subida desde el panel: un DNI renovado actualiza su caducidad,
un IDC rellena el nº de afiliación, la fecha de alta o la de
nacimiento, etc. Solo lee `ocr_text` ya guardado y las fechas ya
registradas -- nada de Gemini ni OCR nuevo.

Reglas (las de S145): los campos vacíos se rellenan, un nº de
afiliación de 11 cifras (el de la empresa) se corrige, las caducidades
solo avanzan; lo demás (alta o nacimiento distintos, domicilio dudoso)
queda como REVISAR y nunca se pisa. S148: el código postal vacío se
toma de la población (`postal_code_service`, dataset del INE) cuando
el municipio tiene un único C.P.; si tiene varios, se deja vacío.
"""
import collections
import datetime
import logging
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType

from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_explorer.postal_code_service import (
    address_postal_code, unique_postal_code,
)

logger = logging.getLogger(__name__)

SOURCE_TYPES = (
    "CONTRATO", "COMUNICACION_CONTRATO", "CONVERSION_CONTRATO", "ALTA",
    "ALTA_IDC", "IDC", "DNI", "NIE", "CARNET_CONDUCIR",
    "RECONOCIMIENTO_MEDICO",
)
PROVINCES = {
    "A CORUNA", "ALAVA", "ARABA", "ALBACETE", "ALICANTE", "ALMERIA",
    "ASTURIAS", "AVILA", "BADAJOZ", "BALEARS", "ILLES BALEARS",
    "BARCELONA", "BIZKAIA", "VIZCAYA", "BURGOS", "CACERES", "CADIZ",
    "CANTABRIA", "CASTELLON", "CEUTA", "CIUDAD REAL", "CORDOBA", "CUENCA",
    "GIPUZKOA", "GIRONA", "GRANADA", "GUADALAJARA", "HUELVA", "HUESCA",
    "JAEN", "LA RIOJA", "LAS PALMAS", "LEON", "LLEIDA", "LUGO", "MADRID",
    "MALAGA", "MELILLA", "MURCIA", "NAVARRA", "OURENSE", "PALENCIA",
    "PONTEVEDRA", "SALAMANCA", "SANTA CRUZ DE TENERIFE", "SEGOVIA",
    "SEVILLA", "SORIA", "TARRAGONA", "TERUEL", "TOLEDO", "VALENCIA",
    "VALLADOLID", "ZAMORA", "ZARAGOZA",
}
_ADDR_STOP = re.compile(
    r"^(DNI|LUGAR DE NACIMIENTO|HIJO|IDESP|EQUIPO|NACIONALIDAD|NOMBRE|"
    r"APELLIDOS|ESP$|REINO)")
_EXPIRY_FIELDS = (
    "dni_expiry_date", "driving_license_expiry_date", "medical_exam_date")
LABELS = {
    "ss_affiliation_number": "Nº afiliación Seg. Social",
    "hire_date": "Fecha de alta",
    "birth_date": "Fecha de nacimiento",
    "address_street": "Dirección",
    "city": "Población",
    "province": "Provincia",
    "dni_expiry_date": "Caducidad DNI/NIE",
    "driving_license_expiry_date": "Caducidad permiso de conducir",
    "medical_exam_date": "Caducidad reconocimiento médico",
    "postal_code": "C.P.",
}


def _upper(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(
        c for c in value if not unicodedata.combining(c)).upper()


def _dmy(value):
    match = re.match(r"(\d{1,2})\D+(\d{1,2})\D+(\d{4})", value.strip())
    if not match:
        return None
    try:
        return datetime.date(
            int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _after(lines, ulines, label):
    """The value after `label`: same line, or the next line."""
    for index, line in enumerate(ulines):
        if line.startswith(label):
            rest = lines[index][len(label):].strip(" :")
            if rest:
                return rest
            return lines[index + 1] if index + 1 < len(lines) else None
    return None


def found_facts(entries):
    """
    What each person's documents say, field by field.
    ---
    Lo que dicen los documentos de cada persona, campo a campo.
    """
    found = collections.defaultdict(lambda: collections.defaultdict(list))
    for entry in entries:
        pid = entry.domain_object_id
        code = entry.document_type.code
        text = entry.ocr_text or ""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        ulines = [_upper(line) for line in lines]
        if code in ("IDC", "ALTA_IDC"):
            nss = _after(lines, ulines, "NSS")
            if nss and re.fullmatch(r"[\d ]{11,14}", nss):
                found[pid]["nss"].append(re.sub(r"\D", "", nss))
            alta = _dmy(_after(lines, ulines, "ALTA:") or "")
            if alta:
                company = _upper(
                    _after(lines, ulines, "RAZON SOCIAL") or "")
                found[pid]["alta"].append((alta, company, entry.pk))
            birth = _dmy(_after(lines, ulines, "NACIMIENTO") or "")
            if birth:
                found[pid]["birth"].append(birth)
        if code in ("CONTRATO", "COMUNICACION_CONTRATO",
                    "CONVERSION_CONTRATO", "ALTA"):
            for index, line in enumerate(ulines):
                if "AFILIACION A LA S.S" in line:
                    for candidate in lines[index:index + 3]:
                        match = re.search(r"\b(\d{2}\s?\d{10})\b", candidate)
                        if match:
                            found[pid]["nss"].append(
                                re.sub(r"\D", "", match.group(1)))
                            break
            if code != "ALTA":
                match = re.search(
                    r"Fecha de Inicio del Contrato:?(?:[^\n]*\n){0,12}?"
                    r"(\d{2}/\d{2}/\d{4})", text)
                if match and _dmy(match.group(1)):
                    found[pid]["start"].append(
                        (_dmy(match.group(1)), entry.pk))
        if code in ("DNI", "NIE"):
            for index, line in enumerate(ulines):
                if line != "DOMICILIO":
                    continue
                block = []
                for j in range(index + 1, min(index + 8, len(lines))):
                    if _ADDR_STOP.match(ulines[j]):
                        break
                    if (re.fullmatch(r"[0-9A-Z]{5,10}", ulines[j])
                            and re.search(r"\d", ulines[j])
                            and re.search(r"[A-Z]", ulines[j])):
                        continue
                    block.append(lines[j])
                # El domicilio del DNI va en mayúsculas: lo que lleva
                # minúsculas o es un número largo es ruido de la firma.
                block = [" ".join(
                    w for w in part.split()
                    if w == w.upper() and not re.fullmatch(r"\d{7,}", w)
                ) for part in block]
                block = [part for part in block if part]
                if len(block) >= 3:
                    found[pid]["address"].append((
                        entry.expiry_date or datetime.date.min, entry.pk,
                        " ".join(block[:-2]), block[-2], block[-1]))
                break
        dated = {
            "DNI": ("dni_expiry_date", entry.expiry_date),
            "NIE": ("dni_expiry_date", entry.expiry_date),
            "CARNET_CONDUCIR": (
                "driving_license_expiry_date", entry.expiry_date),
            "RECONOCIMIENTO_MEDICO": ("medical_exam_date", entry.expiry_date),
        }.get(code)
        if dated and dated[1]:
            found[pid][dated[0]].append((dated[1], entry.pk))
    return found


def proposals(person, found):
    """
    [(field, current, proposed, source, action)] for one person.
    ---
    Propuestas para una persona: acción "rellenar", "corregir",
    "actualizar" (se escriben) o "REVISAR" (solo se listan).
    """
    out = []

    def add(field, value, source, sure=True):
        if value in (None, ""):
            return
        current = getattr(person, field)
        if field == "ss_affiliation_number":
            digits = re.sub(r"\D", "", current or "")
            if digits == value:
                return
            if not current:
                action = "rellenar"
            elif len(digits) == 11:
                action = "corregir"
            else:
                action = "REVISAR"
        elif current in (None, ""):
            action = "rellenar" if sure else "REVISAR"
        elif field in _EXPIRY_FIELDS:
            if value <= current:
                return
            action = "actualizar"
        else:
            if re.sub(r"\W", "", _upper(str(current))) == re.sub(
                    r"\W", "", _upper(str(value))):
                return
            action = "REVISAR"
        out.append((field, current, value, source, action))

    nss = collections.Counter(n for n in found["nss"] if len(n) == 12)
    if nss:
        add("ss_affiliation_number", nss.most_common(1)[0][0],
            "IDC/contrato/alta")
    if found["alta"]:
        company = _upper(person.employer_company).replace(",", "").split()
        altas = sorted(found["alta"], reverse=True)
        own = [a for a in altas if company and company[0] in a[1]] or altas
        add("hire_date", own[0][0], "IDC id=%s" % own[0][2])
    elif found["start"]:
        start = sorted(found["start"], reverse=True)[0]
        add("hire_date", start[0], "contrato id=%s" % start[1])
    if found["birth"]:
        add("birth_date", collections.Counter(
            found["birth"]).most_common(1)[0][0], "IDC")
    if found["address"]:
        # Formato antiguo del DNI ("LUGAR DE DOMICILIO", "PROVINCIA/PAÍS"
        # leídos como texto): no se da por bueno.
        good = [a for a in found["address"]
                if _upper(a[4]).strip(" .") in PROVINCES
                and not re.search(r"LUGAR DE|PROVINCIA|LOCALIDAD|PAIS",
                                  _upper(" ".join(a[2:4])))]
        best = sorted(good or found["address"], reverse=True)[0]
        source = "DNI/NIE id=%s" % best[1]
        for field, value in zip(
                ("address_street", "city", "province"), best[2:]):
            add(field, value[:200], source, sure=bool(good))
    for field in _EXPIRY_FIELDS:
        if found[field]:
            value, pk = sorted(found[field], reverse=True)[0]
            add(field, value, "documento id=%s" % pk)
    # S148: C.P. vacío desde la población (la de la ficha o la que se
    # acaba de proponer), con el dataset del INE, solo si el municipio
    # tiene un único C.P.; con varios no se adivina (S148: el del
    # contrato resultó ser casi siempre el de la empresa, 29067).
    city = person.city or next(
        (row[2] for row in out if row[0] == "city"), "")
    street = person.address_street or next(
        (row[2] for row in out if row[0] == "address_street"), "")
    if not person.postal_code and city:
        # S148: primero el de la dirección (CartoCiudad); si no, el único
        # del municipio.
        by_address = address_postal_code(street, city)
        if by_address:
            add("postal_code", by_address, "CartoCiudad %s" % city)
        else:
            add("postal_code", unique_postal_code(city),
                "población %s" % city)
    return out


def person_entries(person_ids):
    """
    The source documents of these people.
    ---
    Documentos de origen de estas personas.
    """
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    return DocumentIndexEntry.objects.filter(
        domain_content_type=person_ct,
        domain_object_id__in=list(person_ids),
        deleted_at__isnull=True,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        document_type__code__in=SOURCE_TYPES,
    ).select_related("document_type").only(
        "pk", "domain_object_id", "ocr_text", "issue_date",
        "expiry_date", "document_type__code",
    )


def refresh_person(person):
    """
    Write the safe proposals of one person; return what was written.
    ---
    Escribe lo seguro de una persona (rellenar, corregir, actualizar)
    y devuelve [(campo, antes, ahora)]; REVISAR nunca se escribe.
    """
    try:
        found = found_facts(person_entries([person.pk]))[person.pk]
    except Exception:  # noqa: BLE001 -- la ficha nunca para un alta
        logger.exception("# [FICHA] No se pudo leer la persona %s",
                         person.pk)
        return []
    written, fields = [], []
    for field, current, value, _source, action in proposals(person, found):
        if action == "REVISAR":
            continue
        setattr(person, field, value)
        fields.append(field)
        written.append((field, current, value))
    if fields:
        person.save(update_fields=fields + ["updated_at"])
        logger.info("# [FICHA] Persona %s: datos de sus documentos: %s",
                    person.pk, written)
    return written


def queue_refresh(person, document_type_code):
    """
    After the upload is committed, refresh the file of the person.
    ---
    Al confirmar la subida, actualiza la ficha de la persona con sus
    documentos (rápido: solo texto ya leído). Nunca para la subida.
    """
    from django.db import transaction

    if document_type_code not in SOURCE_TYPES:
        return

    def _run():
        try:
            refresh_person(PersonIdentity.objects.get(pk=person.pk))
        except Exception:  # noqa: BLE001 -- nunca para la subida
            logger.exception("# [FICHA] Falló la actualización de %s",
                             person.pk)

    transaction.on_commit(_run)
