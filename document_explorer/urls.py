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
        "abrir/<int:pk>/zip/",
        views.ArchivePreviewView.as_view(),
        name="archive_preview",
    ),
    path(
        "abrir/<int:pk>/zip/entrada/",
        views.ArchiveEntryOpenView.as_view(),
        name="archive_entry_open",
    ),
    path(
        "borrar/<int:pk>/",
        views.SendToTrashView.as_view(),
        name="trash_add",
    ),
    path(
        "borrar-seleccionados/",
        views.BulkTrashView.as_view(),
        name="trash_bulk_add",
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
        "fusionar-carpetas/",
        views.MergeFoldersView.as_view(),
        name="merge_folders",
    ),
    path(
        "clasificar/",
        views.ClassifyView.as_view(),
        name="classify",
    ),
    path(
        "no-conformes/anotar/<int:pk>/",
        views.AnnotateNoConformesView.as_view(),
        name="no_conformes_annotate",
    ),
    path(
        "no-conformes/reencolar/",
        views.RequeueNoConformesView.as_view(),
        name="no_conformes_requeue",
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
    # H24 (S144): descargar los archivos seleccionados.
    path(
        "descargar/",
        views.BulkDownloadView.as_view(),
        name="bulk_download",
    ),
    path(
        "agente/registrar/",
        views.RegisterUploadedObjectView.as_view(),
        name="register_uploaded_object",
    ),
    # H30 (S123): latido del agente H28 cada 5 minutos.
    path(
        "agente/latido/",
        views.AgentHeartbeatView.as_view(),
        name="agent_heartbeat",
    ),
    # H24 (S144): descargas a la carpeta local tras un alta.
    path(
        "agente/descargas/",
        views.AgentLocalDownloadsView.as_view(),
        name="agent_local_downloads",
    ),
    path(
        "agente/descargas/<int:pk>/",
        views.AgentLocalDownloadReportView.as_view(),
        name="agent_local_download_report",
    ),
    # H24 (S146): copias de seguridad de la BD, bajadas a OneDrive.
    path(
        "agente/copias-bd/",
        views.AgentDbBackupsView.as_view(),
        name="agent_db_backups",
    ),
    path(
        "agente/copias-bd/<int:pk>/archivo/",
        views.AgentDbBackupFileView.as_view(),
        name="agent_db_backup_file",
    ),
    path(
        "agente/copias-bd/<int:pk>/",
        views.AgentDbBackupReportView.as_view(),
        name="agent_db_backup_report",
    ),
    path(
        "catalogo/",
        views.DocumentTypeCatalogListView.as_view(),
        name="type_catalog",
    ),
    path(
        "catalogo/anadir/",
        views.DocumentTypeCatalogCreateView.as_view(),
        name="type_catalog_create",
    ),
    path(
        "catalogo/<int:pk>/alternar/",
        views.DocumentTypeCatalogToggleView.as_view(),
        name="type_catalog_toggle",
    ),
    # H30 (S125): «Lo aporta el trabajador», por fila y en bloque.
    path(
        "catalogo/<int:pk>/aporta-trabajador/",
        views.DocumentTypeCatalogWorkerProvidesView.as_view(),
        name="type_catalog_worker_provides",
    ),
    path(
        "catalogo/masivo/",
        views.DocumentTypeCatalogBulkView.as_view(),
        name="type_catalog_bulk",
    ),
    path(
        "cuarentena/",
        views.QuarantineStatusView.as_view(),
        name="quarantine_status",
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
