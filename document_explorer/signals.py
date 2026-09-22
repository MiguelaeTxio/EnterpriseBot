# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/signals.py
"""
H31 (S115). Señal post_save de PersonIdentity: intenta enlazar
automáticamente con el CompanyUser activo que comparta el mismo DNI
exacto, cada vez que se crea o actualiza una PersonIdentity -- ver
`identity_sync.sync_identity_link` para el detalle completo y el
incidente real que motivó esto.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .identity_sync import sync_identity_link
from .models import PersonIdentity


@receiver(post_save, sender=PersonIdentity)
def person_identity_saved(sender, instance, **kwargs):
    sync_identity_link(instance.dni)
