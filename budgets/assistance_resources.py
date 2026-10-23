# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/assistance_resources.py
"""
H37 (S132). Resources of the assistance service: drivers and machines.

---

H37 (S132). Recursos del servicio de asistencia: conductores y
máquinas. Decisiones de Miguel Ángel en S132 (anexo V37, sección 5):

- Conductores: los trabajadores de la sección Asistencia, que entran
  ahí al darse de alta por WhatsApp (*"Conforme se vayan dando de alta
  trabajadores irán entrando en la sección"*). Se toman los
  `CompanyUser` activos con rol de trabajador (`WORKER_ROLES`) cuyo
  `Contact` pertenece a esa sección. En S133 entraron también los
  administradores, solo para las pruebas (`8f0629a`); en S134 se
  quitan (hoja de ruta S134, punto 4.2).
- Máquinas: las de la familia ASISTENCIA de la flota.

El teléfono del conductor vive en su `Contact` (`phone_number`); el
campo `CompanyUser.phone` está vacío en producción (consulta S132).
"""
from document_explorer.person_phone_service import whatsapp_address
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser

ASSISTANCE_SECTION_NAME = "Asistencia"
ASSISTANCE_MACHINE_FAMILY = "ASISTENCIA"


def assistance_drivers(company):
    """
    Active drivers of the assistance section of a company.

    ---

    Conductores activos de la sección Asistencia de la empresa. Los
    administradores ya no entran (S134, punto 4.2: se añadieron en
    S133 solo para las pruebas).
    """
    return CompanyUser.objects.filter(
        role__in=CompanyUser.WORKER_ROLES,
        contact_profile__sections__company=company,
        contact_profile__sections__name__iexact=ASSISTANCE_SECTION_NAME,
        company=company,
        is_active=True,
    ).select_related("user").distinct().order_by(
        "user__first_name", "user__last_name", "user__username",
    )


def assistance_machines(company):
    """
    Active machines of the ASISTENCIA fleet family, by internal code.

    ---

    Máquinas activas de la familia ASISTENCIA, por su código interno
    (B30, A39, X02...).
    """
    return MachineAsset.objects.filter(
        company=company,
        is_active=True,
        family__iexact=ASSISTANCE_MACHINE_FAMILY,
    ).order_by("code")


def operator_phone(company_user):
    """
    WhatsApp number (E.164) of a panel user, or None.

    ---

    Número de WhatsApp (E.164) de un usuario del panel: el de su
    `CompanyUser.phone` si lo tiene, si no el de su `Contact`. None si
    no hay ningún móvil válido.
    """
    phone = whatsapp_address(company_user.phone)
    if phone:
        return phone
    for raw in company_user.contact_profile.values_list(
        "phone_number", flat=True,
    ):
        phone = whatsapp_address(raw)
        if phone:
            return phone
    return None
