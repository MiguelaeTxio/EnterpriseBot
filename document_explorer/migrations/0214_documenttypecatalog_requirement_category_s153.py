# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0214_documenttypecatalog_requirement_category_s153.py
# S153: `DocumentTypeCatalog.requirement_category` (1 = esencial, 2 =
# resto) para el gestor de Requisitos de documentación, y clasificación
# inicial de todo el catálogo por código. Lo que no está en la lista
# queda en la categoría 2 (valor por defecto).

from django.db import migrations, models

ESSENTIAL_CODES = (
    # Máquina: lo que hay que llevar para circular y trabajar sin multa.
    "ITV",
    "OCA",
    "PERMISO_CIRCULACION",
    "AUTORIZACION_PROVISIONAL_CIRCULACION",
    "AUTORIZACION_COMPLEMENTARIA_CIRCULACION",
    "CERT_EXENCION_PERMISO",
    "FICHA_TECNICA",
    "REFORMA_VEHICULO",
    "TARJETA_TRANSPORTE",
    "CERT_NO_TARJ_TTES",
    "REV_TACOGRAFO",
    "SEGURO",
    "POLIZA_SEGURO",
    "CERTIFICADO_SEGURO",
    "CARTA_VERDE",
    "CE",
    "C_ADECUACION",
    "IPO_ITC",
    "RAE",
    "LIBRO_HISTORIAL",
    "MANUAL_USO",
    "TABLA_DE_CARGA",
    "CERT_MANTENIMIENTO",
    "CERT_REVISION",
    "CERT_ACCESORIO_ELEVACION",
    "REVISION_ESLINGAS",
    # Persona: identidad.
    "DNI",
    "NIE",
    "SEG_SOCIAL",
    # Persona: conducción.
    "CARNET_CONDUCIR",
    "AUTORIZACION_TEMPORAL_CONDUCIR",
    "CAP",
    "TARJETA_CUALIF_CONDUCTOR",
    "TACOGRAFO",
    "CERT_EXENCION_TACOGRAFO",
    "ADR",
    "CARNET_GRUISTA",
    # Persona: puesto de trabajo.
    "ALTA",
    "ALTA_IDC",
    "IDC",
    "TC2",
    "CONTRATO",
    "PRORROGA_CONTRATO",
    "MODIFICACION_CONTRATO",
    "CONVERSION_CONTRATO",
    "RECONOCIMIENTO_MEDICO",
    # Persona: PRL, formación y EPIs.
    "AUTORIZACION_USO_MAQUINARIA",
    "CAPACITACION",
    "EPIS",
    "ENTREGA_INFORMACION",
    "EVALUACION_RIESGO",
    "ENTREGA_MANUAL_COMBUSTIBLE",
    "ENTREGA_PROTOCOLO_AUXILIO_CARRETERA",
    "RECURSO_PREVENTIVO",
    "NOMBRAMIENTO_RECURSO_PREVENTIVO",
    "NOMBRAMIENTO_JEFE_MANIOBRAS",
    "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD",
    "CURSO",
    "FORMACION",
    "FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA",
    "FORMACION_CARRETILLAS_TRASPALETAS",
    "FORMACION_ELECTRICIDAD",
    "FORMACION_EXTINCION_INCENDIOS",
    "FORMACION_GRUAS_ASISTENCIA_CARRETERA",
    "FORMACION_GRUA_HIDRAULICA_ARTICULADA",
    "FORMACION_GWO_SEGURIDAD_EOLICA",
    "FORMACION_ITC_MINERA",
    "FORMACION_OPERADOR_APARATOS_ELEVACION",
    "FORMACION_OPERADOR_CAMION_AUTOCARGANTE",
    "FORMACION_OPERADOR_MINIGRUA",
    "FORMACION_PLATAFORMA_ELEVADORA",
    "FORMACION_PRIMEROS_AUXILIOS",
    "FORMACION_PRL_60H",
    "FORMACION_PRL_ART_18_19",
    "FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA",
    "FORMACION_PRL_MAQUINARIA",
    "FORMACION_SUBESTACIONES",
    "FORMACION_TRABAJOS_ALTURA",
)


def classify(apps, schema_editor):
    """
    Put the essential codes in category 1.
    ---
    Pasa a la categoría 1 los códigos esenciales.
    """
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code__in=ESSENTIAL_CODES).update(
        requirement_category=1,
    )


def unclassify(apps, schema_editor):
    """
    Nothing to undo: the column goes away with the field.
    ---
    Nada que deshacer: la columna desaparece con el campo.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0213_machinealertrule_s148"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="requirement_category",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "Categoría 1 (esencial)"),
                    (2, "Categoría 2 (resto)"),
                ],
                default=2,
                help_text=(
                    "S153. Categoría 1: documentos esenciales (los "
                    "obligatorios de un vehículo para circular y "
                    "trabajar; identidad, conducción, contrato, "
                    "formación, EPIs y PRL de una persona). Categoría "
                    "2: el resto. El gestor de Requisitos de "
                    "documentación enseña por defecto solo la "
                    "categoría 1. Un tipo nuevo nace en la 2; se cambia "
                    "desde el Catálogo de tipos."
                ),
                verbose_name="Categoría para requisitos",
            ),
        ),
        migrations.RunPython(classify, unclassify),
    ]
