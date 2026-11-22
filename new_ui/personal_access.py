# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/personal_access.py
"""
S163: copia de panel/personal_access.py para la nueva interfaz.
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
from django.utils import timezone

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


def unlinked_account(person):
    """
    An existing panel account of the worker not linked to the file.
    ---
    S147 (Miguel Ángel, caso de Rocío Macías: usuario
    Rocio_administracion, Supervisor, sin enlazar con su ficha): una
    cuenta del panel que ya existe y es de este trabajador pero no está
    unida a su ficha -- por DNI o, si la cuenta no lo tiene, por nombre
    y primer apellido (sin tildes). Así no se le crea un usuario
    duplicado ni se le cambia el rol: se enlaza. None si no hay una
    sola clara.
    """
    if person.company_user_id:
        return None
    free = CompanyUser.objects.filter(
        person_identity__isnull=True, pending_onboarding=False,
    ).select_related("user")
    if person.dni:
        by_dni = [cu for cu in free.filter(dni__iexact=person.dni)]
        if len(by_dni) == 1:
            return by_dni[0]
    given = _plain(person.given_name)
    first = _plain(person.first_surname)
    if not given or not first:
        return None
    by_name = [
        cu for cu in free.filter(dni="") | free.filter(dni__isnull=True)
        if _plain(cu.user.first_name) == given
        and _plain(cu.user.last_name).startswith(first)
    ]
    return by_name[0] if len(by_name) == 1 else None


def link_account(person, account):
    """
    Links an existing account to the worker file, role untouched.
    ---
    Enlaza una cuenta que ya existe con la ficha del trabajador (S147):
    no toca su rol, su base ni su contraseña; si la cuenta no tenía DNI,
    se le pone el de la ficha.
    """
    with transaction.atomic():
        person.company_user = account
        person.save(update_fields=["company_user"])
        if not account.dni and person.dni:
            account.dni = person.dni
            account.save(update_fields=["dni"])
    return account


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
            "unlinked": unlinked_account(person),
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
    company = by.company
    pending = pending_account(person)
    # S147: un pre-registro con un rol que no es de trabajador
    # (supervisor, administración...) lo conserva: role vacío = el suyo.
    if not role and pending is not None and pending.role:
        role = pending.role
    elif role not in dict(CompanyUser.ROLE_CHOICES):
        # S149: los mismos roles que al crear un usuario.
        raise AccessError("rol en el panel no válido")
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


# ---------------------------------------------------------------------------
# H24 (S144): estado del alta en el fichaje y reenvío.
# ---------------------------------------------------------------------------

ONBOARDING_CIRCULAR = "ALTA_FICHAJE"
# S149 (19/11): la misma alta para quien ya tiene usuario del panel (sin
# la contraseña del DNI: entra con la suya).
ONBOARDING_CIRCULAR_PANEL = "ALTA_FICHAJE_PANEL"
ONBOARDING_NO_USER = "no_user"
ONBOARDING_NO_PHONE = "no_phone"
ONBOARDING_NOT_SENT = "not_sent"
ONBOARDING_SENT = "sent"
ONBOARDING_ENTERED = "entered"
ONBOARDING_CLOCKS = "clocks"
# Orden del listado y del filtro: del que más falta al que ya ficha.
ONBOARDING_CHOICES = (
    (ONBOARDING_NO_USER, "Sin usuario"),
    (ONBOARDING_NO_PHONE, "Sin teléfono 1"),
    (ONBOARDING_NOT_SENT, "Usuario creado, alta sin enviar"),
    (ONBOARDING_SENT, "Alta enviada (sin entrar)"),
    (ONBOARDING_ENTERED, "Ha entrado, sin fichar"),
    (ONBOARDING_CLOCKS, "Ya ficha"),
)
ONBOARDING_CODES = tuple(code for code, _label in ONBOARDING_CHOICES)
_ONBOARDING_BADGES = {
    ONBOARDING_NO_USER: "secondary",
    ONBOARDING_NO_PHONE: "danger",
    ONBOARDING_NOT_SENT: "warning",
    ONBOARDING_SENT: "info",
    ONBOARDING_ENTERED: "primary",
    ONBOARDING_CLOCKS: "success",
}


class OnboardingState:
    """
    Where one worker is in the clock-in onboarding.
    ---
    En qué punto del alta en el fichaje está un trabajador (S144):
    `code` (uno de ONBOARDING_CODES), `label` con la fecha cuando la
    hay ("Alta enviada el 03/11 (sin entrar)", "Ya ficha desde el
    03/11/2026"), `rank` para ordenar y `badge` para la plantilla.
    """

    def __init__(self, code, when=None):
        self.code = code
        self.when = when
        self.rank = ONBOARDING_CODES.index(code)
        self.badge = _ONBOARDING_BADGES[code]
        if code == ONBOARDING_SENT and when:
            self.label = "Alta enviada el %s (sin entrar)" % (
                when.strftime("%d/%m"))
        elif code == ONBOARDING_CLOCKS and when:
            self.label = "Ya ficha desde el %s" % when.strftime("%d/%m/%Y")
        else:
            self.label = dict(ONBOARDING_CHOICES)[code]


def onboarding_states(people):
    """
    {person pk: OnboardingState} for a list of PersonIdentity.
    ---
    El estado del alta en el fichaje de cada persona, con tres consultas
    para toda la lista:
    - "Ya ficha": tiene algún fichaje (por su ficha o por su usuario);
      la fecha es la del primero. Manda sobre todo lo demás.
    - "Sin usuario": sin cuenta del panel activa (o solo pre-registro).
    - "Ha entrado, sin fichar": su usuario ha entrado alguna vez
      (`User.last_login`).
    - "Sin teléfono 1": no tiene teléfono de empresa válido, así que el
      alta no le puede llegar por WhatsApp.
    - "Alta enviada": hay un envío por WhatsApp de la circular
      ALTA_FICHAJE (DocumentAcknowledgment); fecha del último.
    - Si no, "Usuario creado, alta sin enviar".
    """
    from django.db.models import Max, Min

    from document_explorer.models import DocumentAcknowledgment
    from document_explorer.person_phone_service import mobile_of
    from hr_calendar.models import ClockEvent

    people = list(people)
    pks = [p.pk for p in people]
    account_ids = [p.company_user_id for p in people if p.company_user_id]
    first_by_person = dict(
        ClockEvent.objects.filter(person_id__in=pks).order_by()
        .values("person_id").annotate(first=Min("pressed_at"))
        .values_list("person_id", "first"))
    first_by_account = dict(
        ClockEvent.objects.filter(company_user_id__in=account_ids)
        .order_by().values("company_user_id")
        .annotate(first=Min("pressed_at"))
        .values_list("company_user_id", "first"))
    sent_by_person = dict(
        DocumentAcknowledgment.objects.filter(
            person_id__in=pks,
            document_type__code__in=(ONBOARDING_CIRCULAR,
                                     ONBOARDING_CIRCULAR_PANEL),
            channel=DocumentAcknowledgment.CHANNEL_WHATSAPP,
        ).order_by().values("person_id").annotate(last=Max("created_at"))
        .values_list("person_id", "last"))
    accounts = {
        account.pk: account for account in CompanyUser.objects.filter(
            pk__in=account_ids).select_related("user")
    }
    states = {}
    for person in people:
        account = accounts.get(person.company_user_id)
        firsts = [when for when in (
            first_by_person.get(person.pk),
            first_by_account.get(person.company_user_id),
        ) if when]
        if firsts:
            states[person.pk] = OnboardingState(
                ONBOARDING_CLOCKS, timezone.localtime(min(firsts)))
        elif (account is None or account.pending_onboarding
              or not account.is_active):
            states[person.pk] = OnboardingState(ONBOARDING_NO_USER)
        elif account.user.last_login:
            states[person.pk] = OnboardingState(ONBOARDING_ENTERED)
        elif not mobile_of(person):
            states[person.pk] = OnboardingState(ONBOARDING_NO_PHONE)
        elif person.pk in sent_by_person:
            states[person.pk] = OnboardingState(
                ONBOARDING_SENT, timezone.localtime(sent_by_person[person.pk]))
        else:
            states[person.pk] = OnboardingState(ONBOARDING_NOT_SENT)
    return states


def onboarding_filter(raw):
    """
    The onboarding codes of the "Alta en el fichaje" filter, or None.
    ---
    Los estados marcados en el filtro (parámetro `onboarding`, códigos
    separados por comas). Sin el parámetro o vacío (todas las casillas
    marcadas), None: no se filtra. "none" (ninguna marcada), ningún
    estado: semántica literal de las casillas (directriz 4.24).
    """
    if not raw:
        return None
    codes = [code for code in raw.split(",") if code in ONBOARDING_CODES]
    return None if set(codes) == set(ONBOARDING_CODES) else codes


def filter_by_onboarding(people, codes):
    """
    The people whose onboarding state is in `codes` (None = everyone).
    ---
    Las personas cuyo estado del alta está entre `codes`.
    """
    people = list(people)
    if codes is None:
        return people
    states = onboarding_states(people)
    return [p for p in people if states[p.pk].code in codes]


def resend_onboarding(person, keep_password=False):
    """
    Send the clock-in circular again and reset the access. (ok, reason).
    ---
    Reenvía el alta en el fichaje a un trabajador (S144): vuelve a
    enviar por WhatsApp la circular ALTA_FICHAJE (queda anotado el envío
    como DocumentAcknowledgment, igual que el envío normal) y, solo si
    el WhatsApp sale, vuelve a poner la contraseña en las cuatro
    últimas cifras del DNI y quita sus dispositivos de confianza (por si
    ha cambiado de móvil). Si no se puede enviar, no se cambia nada.
    Devuelve (True, "") o (False, motivo).

    S149 (Miguel Ángel, 18/11, Jerónimo ya tiene acceso): con
    `keep_password` se envía la circular ALTA_FICHAJE_PANEL (entra con
    su contraseña) y no se tocan ni su contraseña ni sus dispositivos
    de confianza.
    """
    from document_explorer.models import (
        DocumentAcknowledgment,
        DocumentTypeCatalog,
    )
    from document_explorer.person_phone_service import mobile_of
    from whatsapp.services import send_circular_notification_whatsapp

    if not has_account(person):
        return False, "sin usuario (primero, Acceso al fichaje)"
    account = person.company_user
    if not account.is_active:
        return False, "su usuario está desactivado"
    password = password_of(person)
    if not password and not keep_password:
        return False, "no tiene DNI con cifras para la contraseña"
    if not mobile_of(person):
        return False, "sin teléfono 1 (de empresa)"
    code = ONBOARDING_CIRCULAR_PANEL if keep_password else ONBOARDING_CIRCULAR
    circular = DocumentTypeCatalog.objects.filter(
        code=code, is_active=True).first()
    if circular is None:
        return False, "no existe la circular %s" % code
    ack = DocumentAcknowledgment.objects.create(
        person=person,
        document_type=circular,
        delivery_date=timezone.localdate(),
        extraction_method=DocumentAcknowledgment.METHOD_MANUAL,
        channel=DocumentAcknowledgment.CHANNEL_WHATSAPP,
    )
    if not send_circular_notification_whatsapp(ack):
        ack.delete()
        return False, "no se ha podido enviar el WhatsApp"
    if keep_password:
        return True, ""
    with transaction.atomic():
        user = account.user
        user.set_password(password)
        user.save(update_fields=["password"])
        account.trusted_devices.all().delete()
    return True, ""
