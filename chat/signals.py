# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/signals.py
"""
Signal handlers for the chat module.
Automatically creates a ChatRoom of type SECTION whenever a new Section
is saved to the database for the first time (created=True).
This complements the idempotent init_chat_rooms management command, which
handles bulk initialisation. The signal handles the incremental case:
one new section → one new room, immediately and transparently.
---
Manejadores de signals para el módulo de chat.
Crea automáticamente una ChatRoom de tipo SECTION cada vez que se guarda
una nueva Section en la base de datos por primera vez (created=True).
Complementa al comando de gestión idempotente init_chat_rooms, que gestiona
la inicialización masiva. La signal gestiona el caso incremental:
una nueva sección → una sala nueva, de forma inmediata y transparente.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from ivr_config.models import Section

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Section)
def create_chat_room_for_section(sender, instance, created, **kwargs):
    """
    Creates a ChatRoom of type SECTION for the newly created Section.
    Uses get_or_create to remain idempotent — safe to call even if a room
    already exists for the section (e.g. after init_chat_rooms).
    Does nothing if called on an update (created=False).
    ---
    Crea una ChatRoom de tipo SECTION para la Section recién creada.
    Usa get_or_create para mantenerse idempotente — seguro aunque ya exista
    una sala para la sección (p.ej. tras ejecutar init_chat_rooms).
    No hace nada si se invoca en una actualización (created=False).
    """
    if not created:
        return

    # Import here to avoid circular imports at module load time.
    # Importacion aqui para evitar importaciones circulares en la carga del modulo.
    from chat.models import ChatRoom

    room, was_created = ChatRoom.objects.get_or_create(
        company=instance.company,
        section=instance,
        room_type=ChatRoom.ROOM_TYPE_SECTION,
        defaults={"name": instance.name, "is_active": True},
    )

    if was_created:
        logger.info(
            "# [signal] ChatRoom creada automaticamente para nueva seccion: "
            "'%s' (company=%s, room_pk=%s)",
            instance.name,
            instance.company_id,
            room.pk,
        )
    else:
        logger.debug(
            "# [signal] ChatRoom ya existia para seccion '%s' — sin cambios.",
            instance.name,
        )
