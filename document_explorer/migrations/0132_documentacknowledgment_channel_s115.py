# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0132_documentacknowledgment_channel_s115.py
"""
H31 (S115). Añade dos campos a `DocumentAcknowledgment` necesarios
para el nuevo flujo de envío de circulares por WhatsApp (plantilla
circular_notification):

1. `channel` (EMAIL/WHATSAPP, default EMAIL) -- distingue el canal
   real de entrega. Todo el histórico existente se preserva como
   EMAIL (comportamiento previo, sin cambio observable) -- el valor
   WHATSAPP solo lo escribirá en adelante el nuevo flujo de envío
   por WhatsApp. Campo separado de `extraction_method` a propósito:
   ese describe cómo se determinó el tipo documental (manual/
   heurística/OCR/Gemini), no por qué canal se entregó -- reutilizarlo
   habría sido el mismo tipo de error de campo mal empleado ya
   corregido en S109 (present_type_codes/present_current_type_codes).
2. `whatsapp_read_at` (nulo por defecto) -- se rellena cuando la
   persona confirma lectura vía el botón "Leer aquí" en el webhook,
   sobre el envío WhatsApp más reciente sin confirmar de esa persona.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0131_contenido_real_circulares_con_ejemplo_s114"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentacknowledgment",
            name="channel",
            field=models.CharField(
                choices=[("EMAIL", "Correo (.eml)"), ("WHATSAPP", "WhatsApp")],
                default="EMAIL",
                max_length=10,
                verbose_name="Canal de envío",
            ),
        ),
        migrations.AddField(
            model_name="documentacknowledgment",
            name="whatsapp_read_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Leída por WhatsApp (fecha/hora)",
            ),
        ),
    ]
