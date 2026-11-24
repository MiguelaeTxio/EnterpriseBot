# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/apps.py
"""
App configuration for cae_mail.

---

H31 (S156). Avisos de las plataformas CAE de los clientes (egestiona,
SerCAE, Quioo, Nidus, Jeveal, Twind, e-coordina...) que Yolanda recibe
en documentacion@ y reenvía como adjunto a administracion@; el agente
de correos del PC de Miguel Ángel los sube al cubo
(CORREOS DOCUMENTACION/NUEVOS) y esta app los lee y saca lo que pide
cada plataforma. App propia para que sus migraciones no choquen con
las de las sesiones en paralelo.
"""
from django.apps import AppConfig


class CaeMailConfig(AppConfig):
    """
    App configuration for cae_mail.

    ---

    Configuración de la app cae_mail.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "cae_mail"
    verbose_name = "Avisos de plataformas CAE"
