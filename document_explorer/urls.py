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
        views.MoveFileView.as_view(),
        name="move",
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
