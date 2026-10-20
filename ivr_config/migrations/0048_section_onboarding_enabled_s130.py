# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0048_section_onboarding_enabled_s130.py
# S130: secciones que se ofrecen en el alta por WhatsApp (Informática no;
# se desmarca desde el panel o con el Comando S de la sesión).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0047_trusteddevice_s129"),
    ]

    operations = [
        migrations.AddField(
            model_name="section",
            name="onboarding_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "S130. Si está marcada, quien se da de alta por "
                    "WhatsApp puede elegir esta sección."
                ),
                verbose_name="Se ofrece en el alta por WhatsApp",
            ),
        ),
    ]
