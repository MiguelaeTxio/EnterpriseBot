# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0060_personidentity_company_s74.py
"""
H31 (S74). Campo company (FK a ivr_config.Company) en PersonIdentity
+ backfill real. Necesario para poder enviar confirmaciones WhatsApp
de entrega de EPI (whatsapp.services), que resuelve
WhatsAppTemplate/WhatsAppSession por Company -- employer_company
(texto libre del Excel) no sirve para eso directamente.

Backfill determinista sobre los valores reales de employer_company
confirmados contra BD de producción en esta misma sesión (Comando S,
S74): una única Company real existe en toda la plataforma
('Grupo Álvarez', slug grupo-alvarez), y las 6 variantes de texto no
vacías observadas son distintas razones sociales del mismo grupo
-- normalizadas aquí a esa Company. Las 161 personas con
employer_company='' (aún sin cruzar contra el Excel real) quedan con
company=NULL, igual que cualquier variante de texto futura no
cubierta por el mapa -- nunca se asigna a ciegas.
"""
from django.db import migrations, models
import django.db.models.deletion


COMPANY_SLUG_BY_EMPLOYER_TEXT = {
    "GRUAS ADOLFO ALVAREZ SL": "grupo-alvarez",
    "TRANSGRUAL SL": "grupo-alvarez",
    "TRANSGRUAL S.L.": "grupo-alvarez",
    "GRUALDI S.L": "grupo-alvarez",
    "ASIST.GRUAS GRANADA": "grupo-alvarez",
    "TRANSGRUAL Y ASITENCIA": "grupo-alvarez",
}


def backfill_company(apps, schema_editor):
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    Company = apps.get_model("ivr_config", "Company")

    companies_by_slug = {c.slug: c for c in Company.objects.all()}
    unmatched_texts = set()

    for person in PersonIdentity.objects.exclude(employer_company=""):
        slug = COMPANY_SLUG_BY_EMPLOYER_TEXT.get(person.employer_company)
        if slug is None:
            unmatched_texts.add(person.employer_company)
            continue
        company = companies_by_slug.get(slug)
        if company is None:
            unmatched_texts.add(person.employer_company)
            continue
        person.company = company
        person.save(update_fields=["company"])

    if unmatched_texts:
        # No detiene el despliegue -- deja constancia en el log del
        # Action. Variante de employer_company aparecida después de
        # S74 y no cubierta todavía por el mapa de esta migración.
        print(
            "AVISO 0060: valores employer_company sin Company asignada "
            "(revisar a mano): " + ", ".join(sorted(unmatched_texts))
        )


def noop_reverse(apps, schema_editor):
    """No se revierte el backfill -- company queda en blanco, no se pierde nada más."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0059_documenttypecatalog_content_html_s74"),
        ("ivr_config", "0043_companyuser_pending_onboarding"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="company",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="personnel",
                to="ivr_config.company",
                verbose_name="Empresa (mensajería/IVR)",
                help_text=(
                    "H31 (S74). Vínculo real a ivr_config.Company -- "
                    "distinto de employer_company (texto libre tal cual "
                    "viene del Excel de plantilla, con variantes como "
                    "'GRUAS ADOLFO ALVAREZ SL' / 'TRANSGRUAL SL' / "
                    "'TRANSGRUAL S.L.' para el mismo grupo). Este campo "
                    "es el que usan las funciones de envío WhatsApp "
                    "(whatsapp.services) para resolver "
                    "WhatsAppTemplate/WhatsAppSession, que están "
                    "indexados por Company, no por employer_company. "
                    "Backfileado por normalización de las variantes "
                    "reales conocidas a fecha de la migración 0060 -- "
                    "ver ese archivo para el mapa exacto. Nulo cuando "
                    "employer_company está vacío (persona aún sin "
                    "cruzar contra el Excel) o cuando aparece una "
                    "variante de texto nueva no cubierta todavía."
                ),
            ),
        ),
        migrations.RunPython(backfill_company, noop_reverse),
    ]
