# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ai_services/apps.py
"""
App configuration for the shared AI services module.
---
Configuración de la app del módulo compartido de servicios de IA.
"""
from django.apps import AppConfig


class AiServicesConfig(AppConfig):
    """
    App configuration for ai_services. Holds shared, app-agnostic
    helpers for interacting with Google Gemini via Vertex AI (DRY
    principle — avoids each domain app duplicating client
    initialisation logic).
    ---
    Configuración de la app ai_services. Contiene helpers
    compartidos y agnósticos de dominio para interactuar con Google
    Gemini vía Vertex AI (principio DRY — evita que cada app de
    dominio duplique la lógica de inicialización del cliente).
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_services'
    verbose_name = 'Servicios de IA Compartidos'
