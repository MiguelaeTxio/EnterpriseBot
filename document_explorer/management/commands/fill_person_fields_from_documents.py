# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fill_person_fields_from_documents.py
"""
H24 (S145). Fill the personnel file of active workers from the text
already read from their own documents.

---

H24 (S145). Rellena la ficha del personal activo con lo que dicen sus
propios documentos. Miguel Ángel: "no aparece con fecha de alta, no
sale su dirección [...] Tenemos una gran cantidad de datos que no
tenemos en base de datos, pero que vienen en los documentos. De hecho,
el alta mismo de la empresa viene en su contrato".

Solo lee `ocr_text` ya guardado (nada de Gemini ni OCR nuevo) y las
fechas ya registradas de los documentos de la persona:

- Nº de afiliación: el NSS de 12 cifras que más se repite entre IDC,
  contrato, comunicación de contrato y alta.
- Fecha de alta: el "ALTA" del IDC más reciente de su empresa (si no,
  el más reciente); sin IDC, el inicio del último contrato.
- Fecha de nacimiento: la del IDC.
- Domicilio, población y provincia: el bloque DOMICILIO del DNI/NIE más
  reciente; solo si la provincia es una provincia real.
- Caducidad del DNI/NIE, del permiso de conducir y del reconocimiento
  médico: la más reciente de sus documentos ya fechados.

Qué escribe con `--apply` (DRY-RUN POR DEFECTO):
- Campos vacíos: los rellena.
- Nº de afiliación con 11 cifras (el código de cuenta de cotización de
  la empresa, no el del trabajador): lo corrige.
- Caducidades con un documento más reciente: las actualiza.
Lo demás (fecha de alta o de nacimiento distinta de la de la ficha,
domicilio dudoso) solo se lista como REVISAR, nunca se pisa.

Sin datos personales en el código (com-actions-relay §0): todo sale de
la BD en el servidor. Log propio en `--log-file`, pantalla y archivo.
"""
import collections
import datetime
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry, PersonIdentity

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


def _found(entries):
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


def _proposals(person, found):
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
    return out


class Command(BaseCommand):
    help = "S145: rellena la ficha del personal activo con sus documentos."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)
        parser.add_argument(
            "--skip", nargs="*", default=[],
            help="id:campo que no se escriben (revisados a mano y "
                 "descartados), p. ej. 190:address_street")

    def handle(self, *args, **options):
        log_file = open(options["log_file"], "a", encoding="utf-8")

        def _log(text):
            line = "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), text)
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        def _plain(text):
            print(text, flush=True)
            log_file.write(text + "\n")

        apply = options["apply"]
        skip = set(options["skip"])
        _log("Ficha del personal activo desde sus documentos (S145) -- %s"
             % ("APLICANDO" if apply
                else "SIMULACIÓN (sin --apply no se escribe)"))
        people = list(PersonIdentity.objects.filter(
            is_active_employee=True).order_by(
                "first_surname", "second_surname", "given_name"))
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        entries = DocumentIndexEntry.objects.filter(
            domain_content_type=person_ct,
            domain_object_id__in=[p.pk for p in people],
            deleted_at__isnull=True,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code__in=SOURCE_TYPES,
        ).select_related("document_type").only(
            "pk", "domain_object_id", "ocr_text", "issue_date",
            "expiry_date", "document_type__code",
        )
        found = _found(entries)
        _log("%d personas activas, %d documentos leídos" % (
            len(people), len(entries)))
        totals = collections.Counter()
        for number, person in enumerate(people, 1):
            props = _proposals(person, found[person.pk])
            if not props:
                continue
            name = "%s %s, %s" % (
                person.first_surname, person.second_surname,
                person.given_name)
            _log("%d/%d %s (id=%d)" % (number, len(people), name, person.pk))
            to_write = []
            for field, current, value, source, action in props:
                if "%d:%s" % (person.pk, field) in skip:
                    action = "DESCARTADO"
                totals[action] += 1
                _plain("    %-10s %s: %s -> %s  [%s]" % (
                    action, LABELS[field], current or "(vacío)", value,
                    source))
                if action not in ("REVISAR", "DESCARTADO"):
                    setattr(person, field, value)
                    to_write.append(field)
            if apply and to_write:
                person.save(update_fields=to_write)
        log_file.write("\n")
        _plain("RESUMEN")
        for action in ("rellenar", "corregir", "actualizar", "REVISAR",
                       "DESCARTADO"):
            _plain("%s: %d" % (action, totals[action]))
        _plain("Escrito en la BD: %s" % ("sí" if apply else "no"))
        log_file.close()
