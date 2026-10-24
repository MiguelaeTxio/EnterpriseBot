# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/signals.py
"""
Signal handlers for the chat module.

H17 -- Paso 1: the post_save signal on Section that created the old
ChatRoom instances was removed.
H37 (S138): every new assistance service is posted by the bot in the
Asistencia room, whatever door it came in through (TIREA photo, panel,
WhatsApp, phone call, budget).

---

Manejadores de signals del módulo de chat.

H17 -- Paso 1: se eliminó la signal post_save sobre Section que creaba
las antiguas ChatRoom.
H37 (S138): cada servicio de asistencia nuevo lo publica el bot en la
sala Asistencia, entre por la puerta que entre (foto de TIREA, panel,
WhatsApp, llamada, presupuesto).
"""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="budgets.WorkOrderAssistance")
def post_new_service(sender, instance, created, **kwargs):
    """
    Post a new service in the Asistencia room after the commit.

    ---

    Publica un servicio nuevo en la sala Asistencia tras el commit
    (con todos sus datos ya guardados).
    """
    if not created or kwargs.get("raw"):
        return
    from chat.room_service import post_service

    work_order_pk = instance.pk
    transaction.on_commit(lambda: post_service(work_order_pk))
