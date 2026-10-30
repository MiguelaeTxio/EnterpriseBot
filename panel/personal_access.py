# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/personal_access.py
"""
Panel access for workers, created from the Personal tab (H24, S141).

Miguel Ángel (S141): the WhatsApp self-onboarding is too much hassle
for the workers; the supervisor creates the accounts from the panel.
Same format as the WhatsApp onboarding: username nombre.apellido
(given name without spaces, first surname, no accents) and, as the
password, the last four digits of the DNI. When two people would get
the same username (father and son, for instance) the proposal uses
both surnames, and the supervisor sees the existing usernames with
their full names and decides the right one. Then the clock-in circular
(link and instructions) is sent to them.

---

Acceso al panel de los trabajadores, creado desde la pestaña Personal
(H24, S141). Ver docstring en inglés: usuario nombre.apellido,
contraseña las cuatro últimas cifras del DNI, el supervisor decide el
usuario cuando se repite.
"""
import re
import unicodedata

from django.contrib.auth.models import User
from django.db import transaction

from ivr_config.models import CompanyUser, Contact, SectionContact

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,150}$")


class AccessError(ValueError):
    """
    The account cannot be created; the message is for the supervisor.
    ---
    No se puede crear la cuenta; el mensaje es para el supervisor.
    """


def _plain(value):
    text = "".join(
        c for c in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(c) != "Mn"
    ).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def username_options(person):
    """
    (nombre.apellido, nombre.apellido.apellido2) for a worker.
    ---
    Los dos nombres de usuario posibles de un trabajador, con el mismo
    formato que el alta por WhatsApp (p. ej. joseantonio.zafra).
    """
    given = _plain(person.given_name)
    first = _plain(person.first_surname)
    second = _plain(person.second_surname)
    short = "%s.%s" % (given, first) if first else given
    long_ = "%s.%s" % (short, second) if second else ""
    return short, long_


def password_of(person):
    """
    The initial password: the last four digits of the DNI, or "".
    ---
    La contraseña inicial: las cuatro últimas cifras del DNI, o "".
    """
    digits = re.sub(r"[^0-9]", "", person.dni or "")
    return digits[-4:] if len(digits) >= 4 else ""


def pending_account(person):
    """
    A pre-registered account (pending_onboarding) of the worker, or None.
    ---
    La cuenta pre-registrada (pendiente de alta) del trabajador, o
    None: la suya enlazada o la de su mismo DNI.
    """
    account = person.company_user
    if account is not None and account.pending_onboarding:
        return account
    if account is None and person.dni:
        return CompanyUser.objects.filter(
            dni__iexact=person.dni, pending_onboarding=True,
        ).select_related("user").first()
    return None


def has_account(person):
    account = person.company_user
    return account is not None and not account.pending_onboarding


def propose(people):
    """
    [{person, username, conflicts, ...}] for the access modal.
    ---
    Para cada trabajador, el usuario propuesto y los usuarios que ya
    existen y se le parecen (con su nombre completo), para que el
    supervisor decida. Si nombre.apellido ya existe (o lo lleva otro de
    la misma tanda), se propone con los dos apellidos.
    """
    rows, batch = [], set()
    for person in people:
        short, long_ = username_options(person)
        pending = pending_account(person)
        own_user_id = pending.user_id if pending else None
        similar = list(User.objects.filter(
            username__istartswith=short,
        ).exclude(pk=own_user_id).order_by("username")[:10]) if short else []
        taken = {u.username.lower() for u in similar} | batch
        proposal = short
        if not short or short in taken:
            proposal = long_ if long_ and long_ not in taken else ""
        if proposal:
            batch.add(proposal)
        rows.append({
            "person": person,
            "username": proposal,
            "conflict": proposal != short,
            "similar": [
                {"username": u.username,
                 "name": ("%s %s" % (u.first_name, u.last_name)).strip()}
                for u in similar
            ],
            "has_account": has_account(person),
            "pending": pending is not None,
            "password_ok": bool(password_of(person)),
        })
    return rows


def create_access(person, username, section, base, role, by):
    """
    Create (or complete) the panel account of one worker.
    ---
    Crea la cuenta del panel de un trabajador (o completa su
    pre-registro): usuario elegido, contraseña las cuatro últimas cifras
    del DNI, rol, base, contacto en su sección de la centralita con su
    teléfono de empresa (número 1), y la enlaza con su ficha. Devuelve
    el CompanyUser. Lanza AccessError si no se puede.
    """
    from document_explorer.person_phone_service import mobile_of

    username = (username or "").strip().lower()
    if has_account(person):
        raise AccessError("ya tiene usuario (%s)" % (
            person.company_user.user.username))
    if not USERNAME_RE.match(username):
        raise AccessError("usuario no válido (solo minúsculas, números, "
                          "punto o guion; mínimo 3)")
    password = password_of(person)
    if not password:
        raise AccessError("no tiene DNI con cifras para la contraseña")
    if role not in CompanyUser.WORKER_ROLES:
        raise AccessError("puesto no válido")
    company = by.company
    pending = pending_account(person)
    clash = User.objects.filter(username__iexact=username)
    if pending is not None:
        clash = clash.exclude(pk=pending.user_id)
    if clash.exists():
        raise AccessError("el usuario %s ya existe" % username)
    surnames = ("%s %s" % (person.first_surname,
                           person.second_surname)).strip()
    with transaction.atomic():
        if pending is not None:
            user = pending.user
            user.username = username
            user.first_name = person.given_name.title()[:150]
            user.last_name = surnames.title()[:150]
            user.is_active = True
            user.set_password(password)
            user.save()
            account = pending
        else:
            user = User.objects.create_user(
                username=username, password=password,
                first_name=person.given_name.title()[:150],
                last_name=surnames.title()[:150],
            )
            account = CompanyUser(company=company, user=user)
        account.role = role
        account.base = base
        account.is_active = True
        account.must_change_password = False
        account.pending_onboarding = False
        account.dni = person.dni
        account.save()
        if person.company_user_id != account.pk:
            person.company_user = account
            person.save(update_fields=["company_user"])
        phone = mobile_of(person) or ""
        contact = None
        if phone:
            contact = Contact.objects.filter(
                company=company, phone_number=phone,
            ).first()
        if contact is None:
            contact = Contact.objects.create(
                company=company, phone_number=phone,
                name=("%s %s" % (person.given_name, surnames)).strip(),
                is_internal=True, company_user=account,
            )
        else:
            contact.company_user = account
            contact.is_internal = True
            contact.save(update_fields=["company_user", "is_internal"])
        if section is not None:
            SectionContact.objects.get_or_create(
                section=section, contact=contact,
                defaults={"priority": 99},
            )
    return account
