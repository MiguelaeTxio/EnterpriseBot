# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/apps.py
"""
Django application configuration for the chat module.
Registers the app under the label 'chat' and sets the default auto field.
---
Configuración de la aplicación Django para el módulo de chat.
Registra la app bajo el label 'chat' y establece el campo auto por defecto.
"""

from django.apps import AppConfig


class ChatConfig(AppConfig):
    """
    AppConfig for the chat Django application.
    Handles real-time IRC-style section chat rooms and the WhatsApp
    breakdown ticket agent for EnterpriseBot.
    ---
    AppConfig para la aplicación Django chat.
    Gestiona las salas de chat IRC por sección en tiempo cuasi-real y el
    agente de tickets de averías vía WhatsApp para EnterpriseBot.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "chat"
    verbose_name = "Chat de Secciones"

    def ready(self):
        # Connects the post_save signal on Section to automatically
        # create a ChatRoom of type SECTION on new Section creation.
        # ---
        # Conecta la signal post_save sobre Section para crear
        # automaticamente una ChatRoom de tipo SECTION al crear una
        # nueva Section.
        import chat.signals  # noqa: F401
