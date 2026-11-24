# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/subjects.py
"""
Link each CAE demand to what it is in EnterpriseBot (S156).

Gemini reads the notice and names the company, worker or machine as
the platform writes them; this module links them to the real
CompanyFiscalProfile, PersonIdentity or MachineAsset by hard
identifiers first (DNI, plate, fleet code) and by name only when the
match is unique. Nothing is ever created.

---

Enlaza cada documento pedido por una plataforma CAE con lo que es en
EnterpriseBot: empresa del grupo, trabajador o centro de gasto. Primero
por identificadores (DNI, matrícula, código de flota); por nombre solo
si casa con uno y solo uno. Nunca crea nada.
"""
import re
import unicodedata

from document_explorer.models import (
    CompanyFiscalProfile,
    DocumentTypeCatalog,
    PersonIdentity,
)
from fleet.models import MachineAsset

# CIF de las 4 empresas del grupo (CompanyFiscalProfile, S113).
_COMPANY_RULES = (
    ("GRANADA", "B93261824"),
    ("GRUALDI", "B29739059"),
    ("TRANSGRUAL", "B92493022"),
    ("ALVAREZ", "B29405040"),
)
_CODE_RE = re.compile(r"\b([A-Z]{1,2})\s*-?\s*(\d{1,3})\b")


def _plain(text):
    """Upper case, no accents, single spaces.
    ---
    Mayúsculas, sin tildes y con un solo espacio.
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.upper().split())


def _compact(text):
    """Only letters and digits (plates, DNI).
    ---
    Solo letras y cifras (matrículas, DNI).
    """
    return re.sub(r"[^A-Z0-9]", "", _plain(text))


def resolve_company(*texts):
    """Group company named in any of the texts, or None.
    ---
    Empresa del grupo nombrada en alguno de los textos, o None.
    """
    for text in texts:
        plain = _plain(text)
        for word, tax_id in _COMPANY_RULES:
            if word in plain:
                return CompanyFiscalProfile.objects.filter(
                    tax_id=tax_id).first()
    return None


def resolve_person(name, reference):
    """Worker by DNI/NIE, else by a unique full-name match, or None.
    ---
    Trabajador por DNI/NIE; si no, por nombre cuando todas sus palabras
    casan con una sola persona. None si no se sabe.
    """
    dni = _compact(reference)
    if len(dni) >= 8:
        person = PersonIdentity.objects.filter(dni__iexact=dni).first()
        if person is not None:
            return person
    words = set(_plain(name).replace(",", " ").split())
    if len(words) < 2:
        return None
    found = []
    for person in PersonIdentity.objects.only(
            "pk", "given_name", "first_surname", "second_surname"):
        full = set(_plain(" ".join(filter(None, [
            person.given_name, person.first_surname,
            person.second_surname,
        ]))).split())
        if words <= full:
            found.append(person)
            if len(found) > 1:
                return None
    return found[0] if found else None


def resolve_machine(name, reference):
    """Machine by plate, else by fleet code ("B-23"), or None.
    ---
    Centro de gasto por matrícula; si no, por código de flota
    ("B-23"). None si no se sabe o casa con más de uno.
    """
    plate = _compact(reference) or _compact(name)
    if len(plate) >= 5:
        for machine in MachineAsset.objects.exclude(plate="").only(
                "pk", "plate"):
            if _compact(machine.plate) == plate:
                return machine
    match = _CODE_RE.search(_plain(name)) or _CODE_RE.search(
        _plain(reference))
    if match:
        code = "%s%s" % match.groups()
        found = [
            machine for machine in MachineAsset.objects.only("pk", "code")
            if _compact(machine.code) == code
        ]
        if len(found) == 1:
            return found[0]
    return None


def link_demand(demand, mail, type_code):
    """Fill the links of one demand (not saved).
    ---
    Rellena los enlaces de un documento pedido (sin guardarlo): tipo
    del catálogo, empresa (del propio documento o del aviso),
    trabajador o centro de gasto.
    """
    if type_code:
        demand.document_type = DocumentTypeCatalog.objects.filter(
            code=type_code, is_active=True).first()
    if demand.subject_type == demand.SUBJECT_COMPANY:
        demand.company = resolve_company(
            demand.subject_name, mail.our_company)
    else:
        demand.company = resolve_company(mail.our_company)
    if demand.subject_type == demand.SUBJECT_WORKER:
        demand.person = resolve_person(
            demand.subject_name, demand.subject_ref)
    elif demand.subject_type == demand.SUBJECT_MACHINE:
        demand.machine = resolve_machine(
            demand.subject_name, demand.subject_ref)
    return demand
