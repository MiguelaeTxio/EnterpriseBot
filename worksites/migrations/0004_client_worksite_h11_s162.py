# H11 (S162, sesión invasora): Cliente y obra ampliada para los
# albaranes de trabajo de las grúas.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worksites', '0003_sync_state_s120'),
    ]

    operations = [
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Cliente')),
                ('tax_id', models.CharField(blank=True, default='', max_length=20, verbose_name='N.I.F.')),
                ('address', models.CharField(blank=True, default='', max_length=300, verbose_name='Domicilio')),
                ('locality', models.CharField(blank=True, default='', max_length=120, verbose_name='Localidad')),
                ('province', models.CharField(blank=True, default='', max_length=80, verbose_name='Provincia')),
                ('phone', models.CharField(blank=True, default='', max_length=40, verbose_name='Teléfono')),
                ('email', models.CharField(blank=True, default='', help_text='Uno o varios correos separados por comas. La obra puede tener los suyos propios.', max_length=254, verbose_name='Correo para los albaranes')),
                ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                ('notes', models.TextField(blank=True, default='', verbose_name='Notas')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de alta')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Última modificación')),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='worksite',
            name='client',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='worksites', to='worksites.client', verbose_name='Cliente'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='project_number',
            field=models.CharField(blank=True, default='', max_length=60, verbose_name='Nº de proyecto'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='order_number',
            field=models.CharField(blank=True, default='', help_text='El que se pone en sus albaranes si el planning no trae otro.', max_length=60, verbose_name='Nº de pedido'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='locality',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Localidad'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='province',
            field=models.CharField(blank=True, default='', max_length=80, verbose_name='Provincia'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='Latitud'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='Longitud'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='contact_name',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Persona de contacto'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='contact_phone',
            field=models.CharField(blank=True, default='', max_length=40, verbose_name='Teléfono de contacto'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='min_hours',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Mínimo de horas que se factura por servicio.', max_digits=4, null=True, verbose_name='Horas mínimas'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='delivery_channel',
            field=models.CharField(choices=[('EMAIL', 'Por correo'), ('WHATSAPP', 'Por WhatsApp'), ('BOTH', 'Por correo y WhatsApp'), ('NONE', 'No se envía')], default='EMAIL', max_length=10, verbose_name='Entrega del albarán firmado'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='delivery_email',
            field=models.CharField(blank=True, default='', help_text='Uno o varios correos separados por comas; vacío, el del cliente.', max_length=254, verbose_name='Correo de la obra'),
        ),
        migrations.AddField(
            model_name='worksite',
            name='delivery_whatsapp',
            field=models.CharField(blank=True, default='', help_text='Móvil al que se envía el albarán firmado por WhatsApp; vacío, el teléfono de contacto.', max_length=40, verbose_name='WhatsApp de la obra'),
        ),
    ]
