# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0033_merge_duplicate_types_s51.py
"""
H30 (S51). Dos fusiones de tipos, mismo patron que la fusion IPO_ITC
de S49/S50 (ver 0031_merge_ipo_itc.py) -- desactivar el tipo perdedor
(is_active=False, nunca se borra, para no perder el rastro historico)
y reasignar TODOS los DocumentIndexEntry que apuntaban a el hacia el
tipo ganador, en la misma migracion.

Origen real: al muestrear 3 ejemplos reales ya clasificados de cada
uno de los 77 tipos activos (S51, para construir CONTENT_MARKERS a
partir de datos reales -- ver `sample_type_patterns.py`), dos pares
resultaron ser, en la practica, el mismo documento bajo dos codigos
distintos:

1. MANDATO / CERTIFICADO_PODERES -- las 6 muestras combinadas (3+3)
   son el mismo formulario oficial de la DGT ("DOCUMENTO DE
   REPRESENTACION DE PERSONAS JURIDICAS"), texto identico en
   estructura y proposito. Ninguna frase de contenido los distingue
   entre si.
2. BAJA_DEFINITIVA / DOC_BAJA_DEFINITIVA (desguace) -- las 6 muestras
   combinadas son el mismo formulario oficial "BAJA DE VEHICULO" /
   "DATOS BAJA DEFINITIVA" de la DGT, mismo Centro de Tratamiento
   Autorizado (CATV/desguace) mencionado en ambos casos indistintamente.

Miguel Angel, verbatim, tras ver el hallazgo: "Mandato y certificado
de poderes es una cosa, baja definitiva y dos baja definitiva es
otra [...] Lo que no vamos a tener es mandato, certificado, poderes,
poderes, no. Vamos a tener uno. Un tipo. Le ponemos un nombre y ese
va a ser el tipo, y todos se van a agarrar a ese tipo." Nombres de
los tipos ganadores confirmados explicitamente por Miguel Angel:
CERTIFICADO_PODERES y BAJA_DEFINITIVA (ambos ya existian como tipos
activos -- a diferencia de la fusion IPO_ITC, aqui NO se crea ningun
tipo nuevo, solo se retira el duplicado).

SOLICITUD_ADMINISTRATIVA se revisó en la misma sesión y se confirmó
que NO es duplicado de ninguno de los dos pares -- sus 3 muestras son
contenido genuinamente distinto entre si (declaraciones responsables
e informes libres, sin patron de formulario oficial compartido). No
se toca en esta migración.
"""
from django.db import migrations


def merge_duplicate_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")

    for winner_code, loser_code in (
        ("CERTIFICADO_PODERES", "MANDATO"),
        ("BAJA_DEFINITIVA", "DOC_BAJA_DEFINITIVA"),
    ):
        winner = DocumentTypeCatalog.objects.filter(code=winner_code).first()
        if winner is None:
            # No debería pasar -- ambos ganadores ya existían como
            # tipos activos antes de esta migración -- pero si el
            # catálogo cambió entre sesiones, mejor no romper el
            # deploy que asumir en silencio.
            continue

        loser = DocumentTypeCatalog.objects.filter(code=loser_code).first()
        if loser is None:
            continue

        DocumentIndexEntry.objects.filter(
            document_type_id=loser.id,
        ).update(document_type_id=winner.id)

        DocumentTypeCatalog.objects.filter(id=loser.id).update(
            is_active=False,
        )


def unmerge_duplicate_types(apps, schema_editor):
    # Reversion best-effort: no se puede reconstruir con certeza cual
    # entrada era MANDATO/DOC_BAJA_DEFINITIVA y cual era el tipo
    # ganador original (esa es justo la razon de la fusion) -- se deja
    # el ganador tal cual esta y solo se reactivan los tipos perdedores
    # vacios, sin reasignar filas de vuelta. Mismo criterio que
    # 0031_merge_ipo_itc.py.
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=["MANDATO", "DOC_BAJA_DEFINITIVA"],
    ).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0032_add_family_otros_documentos"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_types, unmerge_duplicate_types),
    ]
