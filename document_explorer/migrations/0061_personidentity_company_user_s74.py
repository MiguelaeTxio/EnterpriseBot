# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0061_personidentity_company_user_s74.py
"""
H31 (S74). Campo company_user (OneToOne a ivr_config.CompanyUser) en
PersonIdentity + backfill real. Requisito explícito de Miguel Ángel:
todo el personal de plantilla (PersonIdentity) terminará teniendo
acceso al panel con distintos roles (supervisor, administrador,
operario de taller, mecánico...) -- eso debe quedar reflejado en el
sistema, y las notificaciones/circulares (H31) deben poder tenerlo en
cuenta: una persona no es solo un registro de RRHH/documentación,
puede ser también un usuario real del panel.

Backfill por cruce EXACTO de DNI (CompanyUser.dni == PersonIdentity.dni)
-- mismo criterio de identificador duro que el resto del proyecto
(nunca por nombre, ver PersonIdentity docstring y regla S73 de
CONTROL EPIS/EpiDelivery). Verificado contra BD de producción en esta
misma sesión (Comando S, S74): de 25 CompanyUser reales, 11 tenían
DNI relleno y los 11 cruzaron limpio contra PersonIdentity, sin
ambigüedad ni colisión. Los 14 CompanyUser sin DNI relleno quedan sin
vincular -- nunca se asigna a ciegas por nombre de usuario.
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_company_user(apps, schema_editor):
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    CompanyUser = apps.get_model("ivr_config", "CompanyUser")

    person_by_dni = {p.dni: p for p in PersonIdentity.objects.all()}
    unmatched = []

    for cu in CompanyUser.objects.exclude(dni=""):
        dni = cu.dni.strip().upper()
        person = person_by_dni.get(dni)
        if person is None:
            unmatched.append(cu.dni)
            continue
        person.company_user = cu
        person.save(update_fields=["company_user"])

    if unmatched:
        # No detiene el despliegue -- deja constancia en el log del
        # Action. CompanyUser dado de alta después de S74 con un DNI
        # que no tiene PersonIdentity correspondiente todavía (p. ej.
        # personal nuevo aún no sembrado desde documentación).
        print(
            "AVISO 0061: DNIs de CompanyUser sin PersonIdentity "
            "correspondiente (revisar a mano): " + ", ".join(unmatched)
        )


def noop_reverse(apps, schema_editor):
    """No se revierte el backfill -- company_user queda en blanco, no se pierde nada más."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0060_personidentity_company_s74"),
        ("ivr_config", "0043_companyuser_pending_onboarding"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="company_user",
            field=models.OneToOneField(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="person_identity",
                to="ivr_config.companyuser",
                verbose_name="Usuario del panel vinculado",
                help_text=(
                    "H31 (S74). Vínculo real a ivr_config.CompanyUser "
                    "-- confirma que esta persona de plantilla es "
                    "TAMBIÉN un usuario del panel (supervisor, "
                    "administrador, operario de taller, etc., ver "
                    "CompanyUser.role), no solo un registro de "
                    "RRHH/documentación. Resuelto por cruce exacto de "
                    "DNI (CompanyUser.dni == PersonIdentity.dni, mismo "
                    "criterio de identificador duro que el resto del "
                    "proyecto -- nunca por nombre). Verificado en "
                    "producción (S74): de 25 CompanyUser reales, 11 "
                    "tenían DNI relleno y los 11 cruzaron limpio, sin "
                    "ambigüedad. Nulo para personal de plantilla sin "
                    "cuenta de panel, o cuyo CompanyUser todavía no "
                    "tiene el DNI relleno."
                ),
            ),
        ),
        migrations.RunPython(backfill_company_user, noop_reverse),
    ]
