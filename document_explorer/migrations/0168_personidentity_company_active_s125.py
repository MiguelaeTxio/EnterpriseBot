# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0168_personidentity_company_active_s125.py
# H30 (S125): PersonIdentity.company vacío en 11 trabajadores ACTIVOS
# dados de alta después de la 0060 (Miguel Ángel, Farraces...). Sin ese
# vínculo el WhatsApp no los reconoce (adjuntos, "Leer aquí", envíos
# resuelven por Company). Se rellena con la única Company real de la
# plataforma, igual que la 0060 (slug grupo-alvarez). Solo activos:
# los históricos no se tocan.

from django.db import migrations

COMPANY_SLUG = "grupo-alvarez"


def fill_company_of_active_people(apps, schema_editor):
    Company = apps.get_model("ivr_config", "Company")
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    company = Company.objects.filter(slug=COMPANY_SLUG).first()
    if company is None:
        print("AVISO 0168: no existe la Company '%s' -- nada que hacer."
              % COMPANY_SLUG)
        return
    updated = PersonIdentity.objects.filter(
        company__isnull=True, is_active_employee=True,
    ).update(company=company)
    print("0168: %d trabajador(es) activo(s) vinculados a '%s'."
          % (updated, company.name))


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0167_worker_submission_status_s125'),
        ('ivr_config', '0044_companyuser_email_signature_html'),
    ]

    operations = [
        migrations.RunPython(
            fill_company_of_active_people, migrations.RunPython.noop,
        ),
    ]
