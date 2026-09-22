# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/identity_sync.py
"""
H31 (S115). Fallo real reportado por Miguel Ángel: el enlace
PersonIdentity.company_user (cruce por DNI, H31/S74) era un backfill
de una sola vez -- funcionaba para las 25 personas que existían en
S74, pero cualquier CompanyUser o PersonIdentity dado de alta después
podía quedar sin enlazar para siempre, sin ningún mecanismo que lo
detectara. Confirmado con una consulta real de solo lectura (S115):
de 11 CompanyUser activos con DNI, 9 estaban bien enlazados y 2 no
(el propio Miguel Ángel, pk=35/pi=250, y Estevao Veloso, pk=42/
pi=221) -- ambos con el DNI ya coincidiendo exacto en ambas tablas,
solo faltaba escribir el FK.

Esta función es el punto único de sincronización, llamada desde dos
signals (`document_explorer.signals` en el post_save de
PersonIdentity, `ivr_config.signals` en el post_save de CompanyUser)
para que el enlace se mantenga vivo en ambas direcciones sin
depender de que alguien recuerde volver a ejecutar un backfill.

Usa `.update()` (no `.save()`) para escribir el enlace -- evita
reentrancia del propio post_save de PersonIdentity al llamarse desde
el signal de CompanyUser (y viceversa si en el futuro PersonIdentity
tuviera su propio post_save distinto de este).

Nunca desvincula un enlace ya existente si deja de coincidir el DNI
-- ese caso (cambio real de DNI) no se ha dado nunca en producción y
se trata aparte, a mano, si llega a ocurrir -- esta función solo
crea enlaces nuevos por coincidencia exacta, nunca borra los que ya
había.
"""
import logging

logger = logging.getLogger(__name__)


def sync_identity_link(dni: str) -> None:
    """
    Ensures PersonIdentity.company_user is set whenever an active
    CompanyUser and a PersonIdentity share the exact same DNI.
    Idempotent and safe to call on every save of either model.

    ---

    Asegura que PersonIdentity.company_user quede establecido siempre
    que un CompanyUser activo y una PersonIdentity compartan el mismo
    DNI exacto. Idempotente y seguro de llamar en cada guardado de
    cualquiera de los dos modelos.
    """
    dni = (dni or "").strip()
    if not dni:
        return

    from document_explorer.models import PersonIdentity
    from ivr_config.models import CompanyUser

    person = PersonIdentity.objects.filter(dni=dni).first()
    if person is None:
        return

    company_user = CompanyUser.objects.filter(dni=dni, is_active=True).first()
    if company_user is None:
        return

    if person.company_user_id != company_user.id:
        PersonIdentity.objects.filter(pk=person.pk).update(company_user=company_user)
        logger.info(
            "# [IDENTITY SYNC] PersonIdentity pk=%s enlazada a "
            "CompanyUser pk=%s por coincidencia de DNI (%s).",
            person.pk, company_user.pk, dni,
        )
