# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0058_epiitemcatalog_standard_expiry_years_s73.py
"""
H30 (S73). Campo nuevo `standard_expiry_years` en EpiItemCatalog --
vida útil estándar en años, usada para calcular la fecha de caducidad
de un EPI a partir de su fecha de entrega.

Motivado por el diseño del extractor de `CONTROL EPIS`: varios
documentos históricos marcan un ítem como CADUCADO sin que exista
todavía una `EpiDelivery` previa registrada para esa persona/ítem --
para esos casos, la fecha de entrega implícita se calcula como
`fecha_del_documento - standard_expiry_years` (decisión explícita de
Miguel Ángel, S73).

Cifra real: no existe una caducidad legal fija (normativa EN
361/EN 365 deja la vida útil máxima a criterio del fabricante,
habitualmente 5-10 años desde fabricación -- verificado por búsqueda
web en la misma sesión). Miguel Ángel fija el criterio único de la
plataforma en 5 años, aplicado a los tres ítems con
`requires_periodic_review=True` (arnés de seguridad, cinturón de dos
elementos de amarre, elemento de amarre).

Este campo es de uso interno del extractor histórico -- cuando se
construya la interfaz de entrega para el supervisor (pendiente,
explícitamente fuera de alcance de esta sesión), la fecha de
caducidad real debe poder modificarse a mano por quien hace la
entrega (Miguel Ángel, S73).
"""
from django.db import migrations, models

_ITEMS_CON_REVISION_5_ANOS = [
    "ARNES_SEGURIDAD", "CINTURON_DOS_AMARRES", "ELEMENTO_AMARRE",
]


def seed_standard_expiry(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.filter(
        code__in=_ITEMS_CON_REVISION_5_ANOS,
    ).update(standard_expiry_years=5)


def unseed_standard_expiry(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.filter(
        code__in=_ITEMS_CON_REVISION_5_ANOS,
    ).update(standard_expiry_years=None)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0057_seed_camiseta_alta_visibilidad_s73"),
    ]

    operations = [
        migrations.AddField(
            model_name="epiitemcatalog",
            name="standard_expiry_years",
            field=models.PositiveSmallIntegerField(
                null=True,
                blank=True,
                verbose_name="Vida útil estándar (años)",
                help_text=(
                    "Años desde la entrega tras los cuales el EPI se "
                    "considera caducado por defecto (norma "
                    "EN 361/EN 365, sin fecha legal fija -- criterio "
                    "de plataforma fijado por Miguel Ángel en 5 años, "
                    "S73). Nulo para EPIs sin revisión periódica."
                ),
            ),
        ),
        migrations.RunPython(seed_standard_expiry, unseed_standard_expiry),
    ]
