# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/urls.py
"""
URL routing for the document explorer (H29).

Mounted under /panel/explorador/ following the convention of the other
panel-mounted apps (budgets, chat, analytics, history...).

---

Enrutado del explorador documental (H29).

Montado bajo /panel/explorador/ siguiendo la convención del resto de
apps colgadas del panel (budgets, chat, analytics, history...).
"""
from django.urls import path

from document_explorer import views

app_name = "document_explorer"

urlpatterns = [
    path("", views.ExplorerView.as_view(), name="explorer"),
    path(
        "listado/",
        views.FolderListingView.as_view(),
        name="listing",
    ),
    path(
        "abrir/<int:pk>/",
        views.OpenDocumentView.as_view(),
        name="open",
    ),
    path(
        "borrar/<int:pk>/",
        views.SendToTrashView.as_view(),
        name="trash_add",
    ),
    path(
        "mover/navegar/",
        views.MoveBrowseView.as_view(),
        name="move_browse",
    ),
    path(
        "mover/crear-carpeta/",
        views.MoveCreateFolderView.as_view(),
        name="move_create_folder",
    ),
    path(
        "mover/",
        views.MoveView.as_view(),
        name="move",
    ),
    path(
        "clasificar/",
        views.ClassifyView.as_view(),
        name="classify",
    ),
    path(
        "duplicados/",
        views.DuplicatesView.as_view(),
        name="duplicates",
    ),
    path(
        "duplicados/papelera/",
        views.SendDuplicatesToTrashView.as_view(),
        name="duplicates_trash",
    ),
    path(
        "duplicados/resolver/",
        views.ResolveDuplicatesView.as_view(),
        name="duplicates_resolve",
    ),
    path(
        "agente/registrar/",
        views.RegisterUploadedObjectView.as_view(),
        name="register_uploaded_object",
    ),
    path(
        "operaciones/",
        views.DataOperationLogListView.as_view(),
        name="operation_log_list",
    ),
    path(
        "operaciones/<int:pk>/",
        views.DataOperationLogDetailView.as_view(),
        name="operation_log_detail",
    ),
    path("papelera/", views.TrashView.as_view(), name="trash"),
    path(
        "papelera/restaurar/<int:pk>/",
        views.RestoreFromTrashView.as_view(),
        name="trash_restore",
    ),
    path(
        "papelera/vaciar/<int:pk>/",
        views.PurgeTrashView.as_view(),
        name="trash_purge",
    ),
]
