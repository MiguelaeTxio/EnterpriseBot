# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/urls_room.py
"""
H37 (S138). Routes of the platform chat rooms, mounted at /sala/.

---

H37 (S138). Rutas de las salas de chat de la plataforma, bajo /sala/
(fuera de /panel/: entran también trabajadores sin cuenta del panel).
"""
from django.urls import path

from chat import views_room

app_name = "chat_room"

urlpatterns = [
    path("", views_room.home, name="home"),
    path("sw.js", views_room.service_worker, name="sw"),
    path("manifest.json", views_room.manifest, name="manifest"),
    path("entrar/<str:token>/", views_room.enter, name="enter"),
    path("<slug:slug>/", views_room.room_page, name="room"),
    path("<slug:slug>/mensajes/", views_room.messages_feed,
         name="messages"),
    path("<slug:slug>/enviar/", views_room.send, name="send"),
    path("<slug:slug>/adjunto/<int:pk>/", views_room.attachment,
         name="attachment"),
    path("<slug:slug>/miembros/candidatos/", views_room.member_candidates,
         name="member_candidates"),
    path("<slug:slug>/miembros/anadir/", views_room.member_add,
         name="member_add"),
]
