# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0053_seed_epi_item_catalog_s71_s72.py
"""
H30 (S71/S72). Poblacion del catalogo cerrado EpiItemCatalog (0 filas
en produccion, verificado en S71) a partir exclusivamente de los 30
documentos reales de entrega subidos por Miguel Angel en S71 (control
de EPIs, dossiers desglosados, arneses con marca/modelo/norma,
botiquines, alta visibilidad, industria quimica, detector de tension).
Ningun item inventado -- lista confirmada por Miguel Angel en S72
("Familias si").

31 items reales (la propia sesion los describia como "~25", la cifra
exacta tras enumerarlos uno a uno es 31). El documento
ENTREGA DE EPIS INDUSTRIA 15-4-19 MARCELINO MACIAS.docx se modela
como 5 EpiDelivery independientes (ya confirmado) -- de ahi que sus 5
componentes (mascara media, filtro, retenedor, bolsa, prefiltro)
aparezcan como items separados del catalogo, no como un item
compuesto.

DECISION S72 (declarada, no bloqueante, facil de corregir despues):
la norma UNE-EN conocida de ENTREGA_EPIS_GRUISTA_2026.docx se aplica
solo al item generico de cada familia (GUANTES_PROTECCION,
ZAPATOS_SEGURIDAD, GAFAS_ANTIPARTICULAS, CHALECO_REFLECTANTE,
CASCO_SEGURIDAD, PROTECCION_AUDITIVA, ARNES_SEGURIDAD,
ELEMENTO_AMARRE) -- el formulario no distingue variante para guantes,
asi que no se propaga a GUANTES_MECANICA/GUANTES_QUIMICA/
GUANTES_MECANICA_QUIMICA. Coste de reposicion solo conocido para
ARNES_SEGURIDAD (55.40 EUR) y DETECTOR_TENSION (317.05 EUR), ambos de
documentos reales con ese dato explicito.

ENTREGA_EPIS_GRUISTA_2026.docx (S72): convive con las plantillas
actuales, no las reemplaza -- exclusivo del puesto de gruista
("Gruista es gruista", Miguel Angel, S72).
"""
from decimal import Decimal

from django.db import migrations

# (family, code, label, requires_periodic_review, replacement_cost, une_en_standard)
CATALOG_ITEMS = [
    ("Ropa de trabajo", "ROPA_TRABAJO", "Ropa de trabajo", False, None, None),
    ("Protección de cabeza", "CASCO_SEGURIDAD", "Casco de seguridad", False, None, "UNE-EN 397"),
    ("Alta visibilidad", "CHALECO_REFLECTANTE", "Chaleco reflectante", False, None, "UNE-EN 471"),
    ("Alta visibilidad", "POLO_ALTA_VISIBILIDAD", "Polo alta visibilidad", False, None, None),
    ("Alta visibilidad", "CHAQUETA_ALTA_VISIBILIDAD", "Chaqueta alta visibilidad", False, None, None),
    ("Alta visibilidad", "MONO_ALTA_VISIBILIDAD", "Mono de trabajo alta visibilidad", False, None, None),
    ("Alta visibilidad", "BUZO_ALTA_VISIBILIDAD", "Buzo de trabajo alta visibilidad (clase 3)", False, None, None),
    ("Alta visibilidad", "PANTALON_ALTA_VISIBILIDAD", "Pantalón alta visibilidad (clase 2, PW3 HI-VIS HOLSTER T501)", False, None, None),
    ("Alta visibilidad", "TRAJE_AGUA", "Traje de agua", False, None, None),
    ("Alta visibilidad", "POLAR", "Polar", False, None, None),
    ("Guantes", "GUANTES_PROTECCION", "Guantes de protección", False, None, "UNE-EN 388"),
    ("Guantes", "GUANTES_MECANICA", "Guantes de acción mecánica", False, None, None),
    ("Guantes", "GUANTES_QUIMICA", "Guantes de acción química", False, None, None),
    ("Guantes", "GUANTES_MECANICA_QUIMICA", "Guantes de acción mecánica y química", False, None, None),
    ("Calzado", "ZAPATOS_SEGURIDAD", "Zapatos de seguridad", False, None, "UNE-EN 344/345"),
    ("Auditiva", "PROTECCION_AUDITIVA", "Protección auditiva", False, None, "UNE-EN 352"),
    ("Ocular", "GAFAS_ANTIPARTICULAS", "Gafas antipartículas / de protección", False, None, "UNE-EN 166"),
    ("Facial", "MASCARA_SOLDAR", "Máscara de soldar", False, None, None),
    ("Facial", "CARETA_PROTECCION", "Careta de protección", False, None, None),
    ("Respiratoria", "MASCARILLA_FILTRO_ANTIPARTICULAS", "Mascarilla con filtro antipartículas", False, None, None),
    ("Respiratoria", "MASCARILLA_BUCONASAL", "Mascarilla buconasal (para polvos y gases)", False, None, None),
    ("Respiratoria", "MASCARA_MEDIA_RESPIRADOR", "Máscara media (respirador)", False, None, None),
    ("Respiratoria", "FILTRO_VAPORES_GASES_ACIDOS", "Filtro vapores orgánicos y gases ácidos", False, None, None),
    ("Respiratoria", "RETENEDOR_FILTROS", "Retenedor de filtros", False, None, None),
    ("Respiratoria", "BOLSA_PORTARRESPIRADOR", "Bolsa portarespirador", False, None, None),
    ("Respiratoria", "PREFILTRO_P3", "Prefiltro P3 / mascarilla 6200", False, None, None),
    ("Anticaídas", "ARNES_SEGURIDAD", "Arnés de seguridad", True, Decimal("55.40"), "UNE-EN 361"),
    ("Anticaídas", "ELEMENTO_AMARRE", "Elemento de amarre", True, None, "UNE-EN 354"),
    ("Anticaídas", "CINTURON_DOS_AMARRES", "Cinturón de seguridad con dos elementos de amarre", True, None, None),
    ("Térmica/eléctrica", "ROPA_IGNIFUGA_ARCO", "Ropa ignífuga contra arco eléctrico", False, None, None),
    ("Eléctrica", "DETECTOR_TENSION", "Detector personal de tensión", False, Decimal("317.05"), None),
]


def seed_catalog(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    for family, code, label, requires_review, cost, une_en in CATALOG_ITEMS:
        EpiItemCatalog.objects.get_or_create(
            code=code,
            defaults={
                "family": family,
                "label": label,
                "requires_periodic_review": requires_review,
                "replacement_cost": cost,
                "une_en_standard": une_en,
                "is_active": True,
            },
        )


def unseed_catalog(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    codes = [item[1] for item in CATALOG_ITEMS]
    EpiItemCatalog.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0052_epiitemcatalog_replacement_cost_une_en_s72"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
