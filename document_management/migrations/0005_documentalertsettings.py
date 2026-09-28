# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/migrations/0005_documentalertsettings.py
# H30 (S122): interruptor del envío automático de avisos por WhatsApp.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('document_management', '0004_sync_state_s120'),
        ('ivr_config', '0042_companyuser_base'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentAlertSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('whatsapp_enabled', models.BooleanField(default=False, verbose_name='Envío automático por WhatsApp activo')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Último cambio')),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='document_alert_settings', to='ivr_config.company', verbose_name='Empresa')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='document_alert_settings_updated', to='ivr_config.companyuser', verbose_name='Último cambio por')),
            ],
            options={
                'verbose_name': 'Configuración de avisos de documentación',
                'verbose_name_plural': 'Configuraciones de avisos de documentación',
            },
        ),
    ]
