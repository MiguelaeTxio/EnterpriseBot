# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0074_documenttypecatalog_dating_scope_s96.py
"""
H31 (S96). Persiste como campo real la distincion que antes solo
vivia en la cabeza de Miguel Angel y se perdia de sesion a sesion:
de varios documentos del mismo tipo de una misma persona, unos tipos
solo necesitan la fecha del vigente (DNI, tarjetas de cualificacion
-- el resto queda historico sin mas) y otros necesitan la fecha de
TODAS sus instancias porque cada una es un hecho legal propio
(reconocimiento medico, TC2, partes de baja medica...).

Clasificacion cerrada en sesion con Miguel Angel (S96), contrastada
contra normativa real donde aplicaba:
- RECONOCIMIENTO_MEDICO: LPRL art. 22 (vigilancia de la salud
  periodica, cada reconocimiento es un acto medico independiente).
- CAP / TARJETA_CUALIF_CONDUCTOR: RD 284/2021 (la tarjeta CAP tiene
  vigencia de 5 anos y cada renovacion sustituye a la anterior; ya
  investigado ademas en H30 S78 -- desde ese RD no se emite CAP como
  documento independiente).
- CSS: no es una hoja de estilos -- es el Certificado de estar al
  corriente con la Seguridad Social (Certificado de Situacion de
  Cotizacion, TGSS), validez legal de 6 meses, usado sobre todo para
  situacion de autonomo (confirmado por el propio mapeo heuristico
  real del codigo, "AUTOMOMOS" -> "CSS", errata de "AUTONOMOS").

Default TODAS aplicado a los 57 tipos con tracks_expiry=True (y al
resto del catalogo, donde el campo es irrelevante); solo se
reclasifican explicitamente a SOLO_VIGENTE los 13 tipos identificados
como "un unico vigente en cada momento, el resto es historico".
"""
from django.db import migrations, models


DATING_SCOPE_CURRENT_ONLY_CODES = [
    "TACOGRAFO",
    "TARJETA_CUALIF_CONDUCTOR",
    "CARNET_CONDUCIR",
    "CARNET_GRUISTA",
    "DNI",
    "NIE",
    "CERT_EXENCION_TACOGRAFO",
    "CERTIFICADO_BANCARIO",
    "CLAUSULA_PROTECCION_DATOS",
    "AUTORIZACION_MEDIOS_COMUNICACION",
    "INFORME_VIDA_LABORAL",
    "CERTIF_DISCAPACIDAD",
    "CERT_LIMITACIONES",
]


def set_current_only_scope(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=DATING_SCOPE_CURRENT_ONLY_CODES,
    ).update(dating_scope="SOLO_VIGENTE")


def revert_current_only_scope(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=DATING_SCOPE_CURRENT_ONLY_CODES,
    ).update(dating_scope="TODAS")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0073_corregir_domain_certificado_poderes_s95"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="dating_scope",
            field=models.CharField(
                choices=[
                    (
                        "SOLO_VIGENTE",
                        "Solo el vigente (el resto queda histórico, su fecha no importa)",
                    ),
                    (
                        "TODAS",
                        "Todas las instancias (cada una es un hecho legal propio)",
                    ),
                ],
                default="TODAS",
                max_length=16,
                verbose_name="Alcance de fechado",
            ),
        ),
        migrations.RunPython(set_current_only_scope, revert_current_only_scope),
    ]
