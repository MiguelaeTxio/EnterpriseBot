# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/urls.py
"""
URLs of the crane albaranes (H11, S162).

---

URLs de los albaranes de grúas (H11, S162): la página Grúas del panel
(/panel/gruas/) y el lado del gruista dentro del fichaje
(/fichaje/albaranes/), que entra con la llave del dispositivo de
confianza o con la llave del propio albarán (enlace del WhatsApp).
"""
from django.urls import path

from crane_albaranes import views_panel as panel
from crane_albaranes import views_worker as worker

app_name = "crane_albaranes"

urlpatterns = [
    path("panel/gruas/", panel.CranesHubView.as_view(), name="hub"),
    path("panel/gruas/albaranes/", panel.AlbaranTabView.as_view(),
         name="albaran_tab"),
    path("panel/gruas/albaranes/resultados/",
         panel.AlbaranResultsView.as_view(), name="albaran_results"),
    path("panel/gruas/albaranes/nuevo/", panel.AlbaranCreateView.as_view(),
         name="albaran_create"),
    path("panel/gruas/albaranes/acciones/", panel.AlbaranMassView.as_view(),
         name="albaran_mass"),
    path("panel/gruas/albaranes/exportar/",
         panel.AlbaranExportView.as_view(), name="albaran_export"),
    path("panel/gruas/albaranes/<int:pk>/",
         panel.AlbaranDetailView.as_view(), name="albaran_detail"),
    path("panel/gruas/albaranes/<int:pk>/pdf/",
         panel.AlbaranPdfView.as_view(), name="albaran_pdf"),
    path("panel/gruas/planning/plantilla/",
         panel.PlanningTemplateView.as_view(), name="planning_template"),
    path("panel/gruas/planning/cargar/", panel.PlanningUploadView.as_view(),
         name="planning_upload"),
    path("panel/gruas/obras/", panel.WorksiteTabView.as_view(),
         name="worksite_tab"),
    path("panel/gruas/obras/resultados/",
         panel.WorksiteResultsView.as_view(), name="worksite_results"),
    path("panel/gruas/obras/guardar/", panel.WorksiteSaveView.as_view(),
         name="worksite_save"),
    path("panel/gruas/obras/acciones/", panel.WorksiteMassView.as_view(),
         name="worksite_mass"),
    path("panel/gruas/obras/exportar/", panel.WorksiteExportView.as_view(),
         name="worksite_export"),
    path("panel/gruas/clientes/", panel.ClientTabView.as_view(),
         name="client_tab"),
    path("panel/gruas/clientes/resultados/",
         panel.ClientResultsView.as_view(), name="client_results"),
    path("panel/gruas/clientes/guardar/", panel.ClientSaveView.as_view(),
         name="client_save"),
    path("panel/gruas/clientes/acciones/", panel.ClientMassView.as_view(),
         name="client_mass"),
    path("panel/gruas/clientes/exportar/", panel.ClientExportView.as_view(),
         name="client_export"),
    # El gruista, dentro del fichaje.
    path("fichaje/albaranes/", worker.worker_list, name="worker_list"),
    path("fichaje/albaranes/nuevo/", worker.worker_new, name="worker_new"),
    path("fichaje/albaranes/<str:token>/", worker.worker_albaran,
         name="worker_albaran"),
    path("fichaje/albaranes/<str:token>/guardar/", worker.worker_save,
         name="worker_save"),
    path("fichaje/albaranes/<str:token>/horas/", worker.worker_clock,
         name="worker_clock"),
    path("fichaje/albaranes/<str:token>/firmar/", worker.worker_sign,
         name="worker_sign"),
    path("fichaje/albaranes/<str:token>/pdf/", worker.worker_pdf,
         name="worker_pdf"),
]
