# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/assistance_search.py
"""
Search of the assistance albaranes by any of their data.

Every stored datum of the order, the albarán, its incidence, its
signature, its helpers and its history becomes a phrase "value label"
("7 horas espera", "accidente", "9237LGN matrícula"...). A row matches
when every searched word is in it and every searched number sits in a
phrase whose label has the label words said next to it, so "7 horas de
espera" finds the services with 7 waiting hours and not the ones with
7 rescue hours.

---

Búsqueda de albaranes de asistencia por cualquiera de sus datos.

H37-S134, punto 4.1 (6.3.H, Miguel Ángel, S133): *"¿Qué se guarda?
Todos los datos del albarán. ¿Por dónde se busca? Por todos los datos
del albarán."* Los campos que nombró son ejemplos, nunca una lista
cerrada: aquí entran todos los campos guardados de la orden, del
albarán, de su incidencia, de su firma, de sus ayudantes y de su
historial, sin lista a mano, para que un campo nuevo entre solo.
"""
import datetime
import re
import unicodedata
from decimal import Decimal

from django.db import models
from django.utils import timezone

from budgets.models import (
    WorkOrderAssistance,
    WorkOrderAssistanceIncidence,
    WorkOrderAssistanceUnit,
)

# Fields that are never searched: internal or binary.
# Campos que nunca se buscan: internos o binarios.
SKIPPED_FIELDS = {
    "id", "company", "phase1_data", "phase2_data", "signature_data",
    "notify_message_sid", "synced_at", "updated_at",
}
STOP_WORDS = {
    "de", "del", "la", "el", "los", "las", "en", "y", "con", "por",
    "a", "al", "un", "una", "que", "se", "o",
}
NUMBER_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


def normalize(text):
    """
    Lowercase text without accents and with single spaces.

    ---

    Texto en minúsculas, sin tildes y con un solo espacio.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _number(token):
    """
    Canonical form of a number ("7,50" -> "7.5", "7.0" -> "7").

    ---

    Forma canónica de un número, para comparar "7", "7,0" y "7.00".
    """
    value = Decimal(token.replace(",", "."))
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _tokens(text):
    """
    Words of a normalized text, numbers in canonical form.

    ---

    Palabras de un texto normalizado, con los números en forma canónica.
    """
    tokens = []
    for raw in re.split(r"[\s;()\[\]\"']+", text):
        raw = raw.strip(".,:")
        if not raw:
            continue
        tokens.append(_number(raw) if NUMBER_RE.match(raw) else raw)
    return tokens


def _value_texts(instance, field):
    """
    Texts of the value of a field, or [] if it is empty.

    ---

    Textos con los que se puede buscar el valor de un campo: la opción
    legible, el nombre de la persona, el número sin ceros, la fecha en
    dd/mm/aaaa; [] si está vacío. Un sí/no verdadero es su etiqueta
    ("accidente", "nocturno"); falso no se busca.
    """
    value = getattr(instance, field.name, None)
    if value in (None, "") or value is False:
        return []
    if value is True:
        return [""]
    if field.choices:
        return [str(getattr(instance, "get_%s_display" % field.name)())]
    if isinstance(field, models.ForeignKey):
        user = getattr(value, "user", None)
        if user is not None:
            return [user.get_full_name() or user.username]
        return [str(value)]
    if isinstance(value, datetime.datetime):
        local = timezone.localtime(value) if timezone.is_aware(
            value
        ) else value
        return [local.strftime("%d/%m/%Y %H:%M")]
    if isinstance(value, datetime.date):
        return [value.strftime("%d/%m/%Y")]
    if isinstance(value, datetime.time):
        return [value.strftime("%H:%M")]
    if isinstance(value, (Decimal, int, float)):
        return [_number(str(value))]
    return [str(value)]


def instance_phrases(instance):
    """
    Phrases (label, text) of every stored datum of an instance.

    ---

    Frases (etiqueta, texto) de cada dato guardado de una instancia.
    """
    phrases = []
    for field in instance._meta.concrete_fields:
        if field.name in SKIPPED_FIELDS or isinstance(
            field, (models.JSONField, models.FileField),
        ):
            continue
        label = normalize(field.verbose_name)
        for text in _value_texts(instance, field):
            phrases.append((label, normalize("%s %s" % (text, label))))
    return phrases


def _label_words():
    """
    Words of the labels of every searched model.

    ---

    Palabras de las etiquetas de todos los modelos que se buscan.
    """
    from budgets.models import (
        WorkOrderAssistanceSignature,
        WorkOrderAssistanceUnitEvent,
    )

    words = set()
    for model in (
        WorkOrderAssistance, WorkOrderAssistanceUnit,
        WorkOrderAssistanceIncidence, WorkOrderAssistanceSignature,
        WorkOrderAssistanceUnitEvent,
    ):
        for field in model._meta.concrete_fields:
            words.update(_tokens(normalize(field.verbose_name)))
    return {
        word for word in words - STOP_WORDS if not NUMBER_RE.match(word)
    }


LABEL_WORDS = None


def row_phrases(work_order, unit=None):
    """
    Phrases of an order and, if there is one, of its albarán.

    ---

    Frases de la orden y, si lo hay, de su albarán: el albarán, su
    incidencia, su firma, sus ayudantes y su historial (motivos,
    notas de asignación forzada...).
    """
    phrases = instance_phrases(work_order)
    if unit is None:
        return phrases
    phrases += instance_phrases(unit)
    incidence = getattr(unit, "incidence", None)
    if incidence is not None:
        phrases += instance_phrases(incidence)
    signature = getattr(unit, "signature", None)
    if signature is not None:
        phrases += instance_phrases(signature)
    for helper in unit.helpers.all():
        name = helper.user.get_full_name() or helper.user.username
        phrases.append(("ayudante", normalize("%s ayudante" % name)))
    for event in unit.events.all():
        phrases += instance_phrases(event)
    return phrases


class Query:
    """
    A parsed search text.

    ---

    Un texto de búsqueda interpretado: sus palabras y, para cada
    número, las palabras de etiqueta que se dijeron a su lado.
    """

    def __init__(self, text):
        global LABEL_WORDS
        if LABEL_WORDS is None:
            LABEL_WORDS = _label_words()
        self.text = normalize(text)
        tokens = [t for t in _tokens(self.text) if t not in STOP_WORDS]
        self.words = [t for t in tokens if not NUMBER_RE.match(t)]
        self.numbers = []
        for index, token in enumerate(tokens):
            if NUMBER_RE.match(token):
                self.numbers.append((token, self._label_run(
                    tokens, index, -1,
                ) + self._label_run(tokens, index, 1)))

    @staticmethod
    def _label_run(tokens, index, step):
        """
        Label words said right before (step -1) or after (step 1) a
        number, up to the first word that is not of a label.

        ---

        Palabras de etiqueta dichas justo antes o después de un número,
        hasta la primera que no es de ninguna etiqueta ("espera de 7
        horas" -> espera y horas; "Zafra 7 horas" -> horas).
        """
        run = []
        index += step
        while 0 <= index < len(tokens) and tokens[index] in LABEL_WORDS:
            run.append(tokens[index])
            index += step
        return run

    def __bool__(self):
        return bool(self.words or self.numbers)

    def matches(self, phrases):
        """
        Whether the phrases of a row satisfy the search.

        ---

        Si las frases de una fila cumplen la búsqueda: cada palabra
        está en alguna frase y cada número está, como número entero,
        en una frase cuya etiqueta tiene las palabras dichas a su lado.
        """
        texts = [text for _label, text in phrases]
        haystack = " | ".join(texts)
        if self.text and self.text in haystack:
            return True
        if any(word not in haystack for word in self.words):
            return False
        for number, near in self.numbers:
            if not any(
                number in _tokens(text)
                and all(word in label for word in near)
                for label, text in phrases
            ):
                return False
        return True
