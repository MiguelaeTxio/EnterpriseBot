# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/urls.py
"""
Routes of the new interface, under /panel/nueva-interfaz/ (S163).

---

Rutas de la nueva interfaz, bajo /panel/nueva-interfaz/ (incluidas en
enterprise_core/urls.py). Todas son suyas: ninguna lleva a vistas de la
interfaz antigua.
"""

from django.urls import path

from new_ui import state, views, views_docs, views_groups

app_name = "new_ui"

urlpatterns = [
    path("", views.NewUiView.as_view(), name="home"),
    path("listado/", views.NewUiListView.as_view(), name="list"),
    path("exportar/", views.NewUiExportView.as_view(), name="export"),
    path("tarjeta/", views.NewUiCardView.as_view(), name="card"),
    path("menu/", views.NewUiMenuView.as_view(), name="menu"),
    path("estado/<str:screen_key>/", state.StateSaveView.as_view(),
         name="state_save"),
    # Grupos de selección ("personas" o "maquinas").
    path("grupos/<str:kind>/guardar/", views_groups.GroupSaveView.as_view(),
         name="group_save"),
    path("grupos/<str:kind>/<int:group_pk>/guardar/",
         views_groups.GroupSaveView.as_view(), name="group_update"),
    path("grupos/<str:kind>/<int:group_pk>/eliminar/",
         views_groups.GroupDeleteView.as_view(), name="group_delete"),
    # Documentos y ficha.
    path("documento/<int:pk>/", views_docs.DocumentFileView.as_view(),
         name="document_file"),
    path("subir/<str:domain>/<int:subject_pk>/",
         views_docs.SubjectUploadView.as_view(), name="subject_upload"),
    path("persona/<int:pk>/guardar/", views_docs.PersonUpdateView.as_view(),
         name="person_update"),
    path("persona/<int:pk>/foto/", views_docs.PersonPhotoView.as_view(),
         name="person_photo"),
    path("persona/<int:pk>/foto/subir/",
         views_docs.PersonPhotoUploadView.as_view(),
         name="person_photo_upload"),
    path("maquina/<int:pk>/guardar/", views.NewUiMachineSaveView.as_view(),
         name="machine_save"),
    path("maquina/<int:pk>/foto/", views_docs.MachineSetAvatarView.as_view(),
         name="machine_set_avatar"),
    path("maquina/<int:pk>/tarjeta/exportar/",
         views_docs.MachineCardExportView.as_view(),
         name="machine_card_export"),
    path("maquina/<int:pk>/qr/imagen/",
         views_docs.MachineQrImageView.as_view(), name="machine_qr_image"),
    path("maquina/<int:pk>/qr/", views_docs.MachineQrActionView.as_view(),
         name="machine_qr_action"),
    # Permisos.
    path("permisos/editor/", views.PermEditorView.as_view(),
         name="perm_editor"),
    path("permisos/acciones/", views.PermBulkView.as_view(),
         name="perm_bulk"),
    path("permisos/grupos/usuarios/", views.PermGroupMembersView.as_view(),
         name="perm_members"),
]
