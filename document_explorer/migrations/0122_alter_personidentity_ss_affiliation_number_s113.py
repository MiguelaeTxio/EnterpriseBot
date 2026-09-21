# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0122_alter_personidentity_ss_affiliation_number_s113.py
"""
H31 (S113). `PersonIdentity.ss_affiliation_number` estaba definido
DOS VECES en el cuerpo de la clase (S100 y S54/Excel) -- Python se
queda con la segunda asignación, así que el campo real, el que de
verdad llegó a la BD (verificado con `SHOW COLUMNS`, real:
varchar(30)), siempre fue el de S54 (`max_length=30`), y la definición
de S100 (`max_length=32`) nunca estuvo en producción. Unificadas en
una sola definición en models.py -- esta migración solo actualiza
`verbose_name` (quitado el sufijo "(Excel)", ya no describe bien el
campo: Miguel Ángel confirmó en S113 que este dato sí es editable a
mano, el único campo realmente inmutable de la ficha es el DNI).

Ningún cambio real de columna -- mismo `max_length=30`, `blank=True`
de siempre.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0121_personidentity_phone_secondary_professional_category_s113"),
    ]

    operations = [
        migrations.AlterField(
            model_name="personidentity",
            name="ss_affiliation_number",
            field=models.CharField(
                blank=True, max_length=30,
                verbose_name="Número de afiliación a la Seguridad Social",
            ),
        ),
    ]
