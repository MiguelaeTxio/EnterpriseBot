# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/apps.py
"""
Django application configuration for the whatsapp channel app.
Registers the app under the label 'whatsapp' within the EnterpriseBot project.
This app handles all WhatsApp inbound/outbound messaging logic, presence webhook
responses, Celery tasks and the WhatsApp-specific data models.
---
Configuración de la aplicación Django para la app del canal WhatsApp.
Registra la app bajo la etiqueta 'whatsapp' dentro del proyecto EnterpriseBot.
Esta app gestiona toda la lógica de mensajería WhatsApp entrante/saliente,
respuestas del webhook de presencia, tareas Celery y los modelos de datos
específicos de WhatsApp.
"""

from django.apps import AppConfig


class WhatsappConfig(AppConfig):
    """
    AppConfig for the whatsapp Django application.
    Sets the default auto field type and registers the app label used
    throughout the project for reverse relations and migrations.
    ---
    AppConfig para la aplicación Django whatsapp.
    Establece el tipo de campo auto por defecto y registra la etiqueta de app
    usada en todo el proyecto para relaciones inversas y migraciones.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "whatsapp"
    verbose_name = "Canal WhatsApp"
