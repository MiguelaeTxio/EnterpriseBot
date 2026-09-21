# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0130_companyfiscalprofile_administrator_s114.py
"""
H31 (S114). Primer paso hacia documentos programáticos con variables
(circulares/autorizaciones generadas ad-hoc a partir de empresa +
administrador + trabajador, no solo texto fijo) -- Miguel Ángel: "las
plantillas deben ser programáticas [...] elegida la plantilla el
documento se genera con variables basadas en la base de datos, si por
ejemplo se quiere dar poderes a un trabajador, elegimos la empresa, el
administrador y el trabajador".

Añade `CompanyFiscalProfile.administrator` (FK a PersonIdentity) y lo
rellena para las 4 empresas reales -- NUNCA asumido de memoria.
Miguel Ángel supuso inicialmente "uno de los hermanos Álvarez Díaz
[...] Adolfo en todas excepto Asistencia y Grúas Granada que es José
Luis", pero él mismo se corrigió en el acto: "espera, lo suyo es leer
contratos de trabajadores de cada una de las empresas e informar
desde ahí". Confirmado contra un contrato real (modelo de contrato
indefinido del SEPE, campo "EN CONCEPTO") de un trabajador de cada
una de las 4 empresas, descargado y leído en esta misma sesión:

- Grúas Adolfo Álvarez SL (CIF B29405040) -- contrato de Arrabali
  Guzmán, Juan Francisco (firmado 15-06-2026): Alvarez Diaz Adolfo,
  DNI 24902678A, "GERENTE".
- Transgrual SL (CIF B92493022) -- contrato de Grana Alvarez, Paloma
  (firmado 09-06-2026): Alvarez Diaz Adolfo, DNI 24902678A,
  "ADMINISTRADOR".
- Grualdi SL (CIF B29739059) -- contrato de Vargas Subires, Ana M
  (12-3-18): Alvarez Diaz Jose Luis, DNI 25687533Y, "ADMINISTRADOR"
  -- la suposición inicial de Miguel Ángel (Adolfo) era incorrecta
  para esta empresa en concreto.
- Asistencia y Grúas Granada SL (CIF B93261824) -- contrato de Muñoz
  Cara, Miguel Ángel (20260915): Alvarez Diaz Jose Luis, DNI
  25687533Y, "ADMINISTD. MANC" (administrador mancomunado) --
  confirma la parte de la suposición inicial que sí era correcta.

Ambos DNI (24902678A, 25687533Y) coinciden exactamente con
PersonIdentity ya existentes en el catálogo de Personal
(ALVAREZ DIAZ, ADOLFO / ALVAREZ DIAZ, JOSE LUIS).
"""
from django.db import migrations, models
import django.db.models.deletion


_ADMINISTRATOR_BY_TAX_ID = {
    "B29405040": "24902678A",  # Grúas Adolfo Álvarez SL -> Adolfo
    "B92493022": "24902678A",  # Transgrual SL -> Adolfo
    "B29739059": "25687533Y",  # Grualdi SL -> José Luis
    "B93261824": "25687533Y",  # Asistencia y Grúas Granada SL -> José Luis
}


def seed_administrators(apps, schema_editor):
    CompanyFiscalProfile = apps.get_model("document_explorer", "CompanyFiscalProfile")
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")

    for tax_id, dni in _ADMINISTRATOR_BY_TAX_ID.items():
        person = PersonIdentity.objects.filter(dni=dni).first()
        if person is None:
            continue
        CompanyFiscalProfile.objects.filter(tax_id=tax_id).update(
            administrator=person,
        )


def unseed_administrators(apps, schema_editor):
    CompanyFiscalProfile = apps.get_model("document_explorer", "CompanyFiscalProfile")
    CompanyFiscalProfile.objects.filter(
        tax_id__in=_ADMINISTRATOR_BY_TAX_ID.keys(),
    ).update(administrator=None)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0129_restaura_plantillas_papelera_s114"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyfiscalprofile",
            name="administrator",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="administered_companies",
                to="document_explorer.personidentity",
                verbose_name="Administrador/representante legal",
            ),
        ),
        migrations.RunPython(
            seed_administrators, unseed_administrators,
        ),
    ]
