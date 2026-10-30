# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/person_phone_service.py
"""
H30 (S125). Phone number <-> worker (PersonIdentity) resolution, shared
by every place that needs it: the WhatsApp webhook (circular "Leer
aqui" button, incoming attachments), document requests and the Docuten
export.

---

H30 (S125). Resolución teléfono <-> trabajador (PersonIdentity),
compartida por todo lo que la necesita: el webhook de WhatsApp (botón
"Leer aquí" de circulares, adjuntos entrantes), las solicitudes de
documentación y la exportación a Docuten.

Origen: la ficha guarda el móvil de 9 dígitos (65 de 76 activos,
consulta real S125) y Twilio entrega el remitente como `+34XXXXXXXXX`;
la comparación literal que usaba el "Leer aquí" no casaba nunca con un
trabajador. Aquí se compara siempre por los 9 dígitos normalizados, en
`phone` y en `phone_secondary`.
"""
import re

from document_explorer.models import PersonIdentity

SPAIN_PREFIX = "+34"


def normalize_mobile(raw):
    """
    Return the 9-digit Spanish number, or None if it is not one.

    ---

    Devuelve el número de 9 dígitos (sin espacios ni prefijo
    +34/0034), o None si no lo es. Lo que no encaja se deja fuera,
    nunca se adivina (S124).
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("34"):
        digits = digits[2:]
    elif len(digits) == 13 and digits.startswith("0034"):
        digits = digits[4:]
    return digits if len(digits) == 9 else None


def whatsapp_address(raw):
    """
    Return the E.164 number used by Twilio (+34XXXXXXXXX), or None.

    ---

    Devuelve el número en formato E.164 que usa Twilio
    (+34XXXXXXXXX), o None si la ficha no tiene un móvil válido.
    """
    digits = normalize_mobile(raw)
    return SPAIN_PREFIX + digits if digits else None


def mobile_of(person):
    """
    The company mobile of a person (`phone` only), or None.

    ---

    El móvil de empresa de la persona, en formato E.164, o None. S141
    (Miguel Ángel): el número 1 (`phone`) es el teléfono de empresa y el
    número 2 (`phone_secondary`) el particular; los mensajes se envían
    únicamente al número 1. Al particular nunca se envía nada (Juan
    Carlos Rodríguez pidió no recibir mensajes en su teléfono
    particular). Para reconocer quién escribe se siguen mirando los dos
    números (resolve_person_by_phone).
    """
    return whatsapp_address(person.phone)


def resolve_person_by_phone(company, raw_phone):
    """
    Return the PersonIdentity owning this phone, or None.

    Matches the normalized 9 digits against `phone` and
    `phone_secondary`. If several people share it, active employees
    win; if it is still ambiguous, None (never a guess).

    ---

    Devuelve la PersonIdentity dueña de este teléfono, o None.
    Compara los 9 dígitos normalizados con `phone` y `phone_secondary`.
    Si varias personas lo comparten, ganan los trabajadores activos;
    si sigue siendo ambiguo, None (nunca se adivina).
    """
    digits = normalize_mobile(raw_phone)
    if not digits:
        return None
    # Normalizado en Python sobre las fichas con teléfono (unos cientos):
    # un filtro de BD no casa "699 11 22 33" con "699112233".
    people = PersonIdentity.objects.filter(company=company).exclude(
        phone="", phone_secondary="",
    )
    candidates = [
        person for person in people
        if digits in (
            normalize_mobile(person.phone),
            normalize_mobile(person.phone_secondary),
        )
    ]
    if len(candidates) > 1:
        candidates = [p for p in candidates if p.is_active_employee]
    return candidates[0] if len(candidates) == 1 else None


def has_panel_access(person):
    """
    Whether the worker has been onboarded with panel access.

    ---

    Si el trabajador está dado de alta con acceso al panel (cuenta
    vinculada, activa, con el alta terminada y usuario activo). Miguel
    Ángel (S125, corregido S126): sin acceso al panel no se archiva lo
    que entregue por WhatsApp por iniciativa propia; lo que se le pide
    (solo hace falta móvil válido) sí se procesa.
    """
    account = getattr(person, "company_user", None)
    return bool(
        account is not None
        and account.is_active
        and not account.pending_onboarding
        and account.user_id
        and account.user.is_active
    )
