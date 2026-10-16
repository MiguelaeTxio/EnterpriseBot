# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/ownership_service.py
"""
H30 (S127). Whose document is this file? -- exact identity matching.

---

H30 (S127). ¿De quién es este archivo? Cotejo EXACTO de identidad
sobre el texto completo (OCR de Cloud Vision / texto incrustado), sin
Gemini. Sustituye a la pregunta "is_this_person" que se le hacía a
Gemini en la auditoría, que no era fiable: fallaba cuando a la ficha le
faltaba el segundo apellido y daba por "de otra persona" archivos que
eran del dueño (contrato de Gutiérrez Santiago). Miguel Ángel: "si no
es fiable, tenemos que hacer que lo sea".

Pruebas que cuentan, página a página:
- NÚMERO: el DNI/NIE completo de una persona del registro, con su letra
  de control (también dentro de la zona legible por máquina, IDESP...).
  Es la prueba fuerte.
- NOMBRE COMPLETO: primer apellido + segundo apellido + nombre de pila,
  juntos y en un orden de documento ("GARCIA LOPEZ, JOSE", "JOSE GARCIA
  LOPEZ"). Sin segundo apellido en la ficha, apellido + nombre completo.
  Nunca vale un apellido suelto ni dos palabras sueltas por la página.

Asimetría deliberada: para dar un archivo por "de otra persona" se pide
la prueba fuerte de ESA persona; para darlo por del dueño basta un
rastro (su número, su nombre completo o su primer apellido junto a su
nombre de pila en la misma página). Ante la duda, el archivo se queda
donde está.

Firmantes: quien aparece en archivos de muchos dueños distintos (la
gerencia que firma contratos y entregas, administración...) no es
prueba de pertenencia -- se calcula sobre el propio corpus
(`signatories`), y la familia de gerencia se excluye siempre.
"""
import re
import unicodedata
from collections import defaultdict

from document_explorer import naming_service
from document_explorer.cloud_vision_service import FULL_OCR_MARKER
from document_explorer.document_audit_service import _pages_of
from document_explorer.models import PersonIdentity

OWNER, OTHER, SEVERAL, NOBODY, NO_TEXT = (
    "DEL DUEÑO", "DE OTRA PERSONA", "VARIAS PERSONAS", "SIN PRUEBAS",
    "SIN OCR COMPLETO",
)
# Una persona que aparece en archivos de al menos tantos dueños
# distintos es firmante/administración, no dueña.
SIGNATORY_MIN_OWNERS = 5


def plain(text):
    """
    Upper case, no accents, single spaces.

    ---

    Mayúsculas, sin acentos, espacios simples (comas y puntos se
    conservan para los patrones de nombre).
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.upper())


def compact(text):
    """Only letters and digits (for document numbers)."""
    return re.sub(r"[^0-9A-Z]", "", plain(text))


def _words(value):
    return [w for w in re.split(r"[^A-Z0-9]+", plain(value)) if w]


class Person:
    """
    Matching data of one PersonIdentity.

    ---

    Datos de cotejo de una persona: número completo y patrones de
    nombre completo.
    """

    def __init__(self, identity):
        self.pk = identity.pk
        self.identity = identity
        self.active = identity.is_active_employee is True
        self.gerencia = naming_service.is_gerencia(
            identity.first_surname, identity.second_surname,
        )
        number = compact(identity.dni)
        self.number = (
            number if len(number) >= 9 and number[-1].isalpha() else ""
        )
        surname1 = _words(identity.first_surname)
        surname2 = _words(identity.second_surname)
        given = _words(identity.given_name)
        self.surname1 = surname1
        self.given = given
        # Separadores de documento: espacios, comas, puntos, dos puntos y
        # los "<" de la zona legible por máquina (GUTIERREZ<MATEO<<...).
        sep = r"[\s,.:<]+"
        # Entre apellidos y nombre caben hasta tres rótulos cortos
        # ("NOMBRE", "2." de las tarjetas, "D/DNA"...).
        filler = r"(?:[A-Z0-9/]{1,12}%s){0,3}" % sep
        surnames = sep.join(map(re.escape, surname1 + surname2))
        if surname2:
            names = sep.join(map(re.escape, given[:1]))
        else:
            names = sep.join(map(re.escape, given))
        self.full_name_re = None
        if surname1 and given:
            self.full_name_re = re.compile(
                r"\b(?:%s%s%s%s|%s%s%s%s)\b" % (
                    surnames, sep, filler, names,
                    names, sep, filler, surnames,
                ),
            )
        # Rastro del dueño: primer apellido y primer nombre como palabras.
        self.trace_res = [
            re.compile(r"\b%s\b" % re.escape(word))
            for word in (surname1[:1] + given[:1])
        ]

    def strong_on(self, page_compact):
        return bool(self.number) and self.number in page_compact

    def full_name_on(self, page_plain):
        return bool(self.full_name_re) and bool(
            self.full_name_re.search(page_plain)
        )

    def trace_on(self, page_plain):
        return bool(self.trace_res) and all(
            regex.search(page_plain) for regex in self.trace_res
        )

    def label(self):
        identity = self.identity
        return "%s %s, %s (pk=%s, %s)" % (
            identity.first_surname, identity.second_surname or "",
            identity.given_name, identity.pk,
            "activo" if self.active else "no activo",
        )


def roster():
    """All people, ready to match."""
    return [Person(identity) for identity in PersonIdentity.objects.all()]


def people_in(entry, people):
    """
    Who appears in a file, page by page.

    ---

    Quién aparece en el archivo: `{pk: [(página, "nº"|"nombre")]}`, o
    None si el archivo no tiene OCR completo.
    """
    text = entry.ocr_text or ""
    if not text.startswith(FULL_OCR_MARKER):
        return None
    found = defaultdict(list)
    for page, page_text in _pages_of(text):
        page_plain = plain(page_text)
        page_compact = re.sub(r"[^0-9A-Z]", "", page_plain)
        for person in people:
            if person.strong_on(page_compact):
                found[person.pk].append((page, "nº"))
            elif person.full_name_on(page_plain):
                found[person.pk].append((page, "nombre"))
    return dict(found)


def owner_traces(entry, owner):
    """Pages where the owner leaves any trace (number, name, surname+name)."""
    text = entry.ocr_text or ""
    pages = []
    for page, page_text in _pages_of(text):
        page_plain = plain(page_text)
        page_compact = re.sub(r"[^0-9A-Z]", "", page_plain)
        if (owner.strong_on(page_compact) or owner.full_name_on(page_plain)
                or owner.trace_on(page_plain)):
            pages.append(page)
    return pages


def signatories(appearances):
    """
    People who show up in the files of many different owners.

    ---

    `appearances`: {pk de persona: conjunto de dueños en cuyos archivos
    aparece}. Devuelve los pk de firmantes.
    """
    return {
        pk for pk, owners in appearances.items()
        if len(owners - {pk}) >= SIGNATORY_MIN_OWNERS
    }


def verdict(entry, owner, found, by_pk, signers):
    """
    OWNER / OTHER / SEVERAL / NOBODY / NO_TEXT and the evidence.

    ---

    Veredicto de un archivo de la ficha de `owner`. Devuelve
    `(veredicto, otra_persona|None, pruebas)`.
    """
    if found is None:
        return NO_TEXT, None, ""
    if owner.pk in found or owner_traces(entry, owner):
        return OWNER, None, ""
    others = {
        pk: hits for pk, hits in found.items()
        if pk not in signers and pk != owner.pk
        and not by_pk[pk].gerencia
    }
    strong = {
        pk: hits for pk, hits in others.items()
        if any(kind == "nº" for _, kind in hits)
    }
    candidates = strong or others
    if not candidates:
        return NOBODY, None, ""
    if len(candidates) > 1:
        return SEVERAL, None, "; ".join(
            "%s en pág. %s" % (by_pk[pk].label(),
                               ",".join(str(p) for p, _ in hits[:5]))
            for pk, hits in candidates.items()
        )
    (pk, hits), = candidates.items()
    evidence = ", ".join("pág.%s por %s" % hit for hit in hits[:6])
    return OTHER, by_pk[pk], evidence
