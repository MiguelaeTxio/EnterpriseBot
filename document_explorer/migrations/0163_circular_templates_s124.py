# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0163_circular_templates_s124.py
# H30 (S124): texto de las dos circulares con firma que tenían documentos
# reales en el cubo pero nunca se importaron a plantilla. Transcrito de
# los documentos reales más recientes (ENTREGA_INFORMACION #42678, firmado
# por Docuten el 18/08/2026; NOMBRAMIENTO_RECURSO_PREVENTIVO #36978), con
# variables en lugar de los datos del trabajador. Solo rellena si el
# texto sigue vacío: nunca pisa lo que se haya escrito a mano.

from django.db import migrations

_TITLE = (
    '<div style="border:2px solid #000;padding:8px;text-align:center;'
    'font-weight:bold;font-size:14pt;margin-bottom:12px;">%s</div>'
)
_CELL = 'border:1px solid #000;padding:4px;'
_SIGNATURES = (
    '<table style="width:100%;margin-top:40px;"><tr>'
    '<td style="width:50%;text-align:center;">Firma recibí del trabajador:'
    '<br><br><br>Fdo.: {{trabajador.nombre_completo}}</td>'
    '<td style="width:50%;text-align:center;">Por la empresa (firma y '
    'sello):<br><br><br>Fdo.: {{administrador.nombre_completo}}</td>'
    '</tr></table>'
    '<p>A fecha {{fecha}}</p>'
)

ENTREGA_INFORMACION = (
    _TITLE % 'ENTREGA DE INFORMACIÓN EN PREVENCIÓN DE RIESGOS LABORALES'
    + '<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">'
    '<tr><td colspan="2" style="' + _CELL + 'text-align:center;">'
    '<strong>DATOS DEL TRABAJADOR</strong></td></tr>'
    '<tr><td style="' + _CELL + 'width:60%;">D. '
    '{{trabajador.nombre_completo}}</td>'
    '<td style="' + _CELL + '">D.N.I. {{trabajador.dni}}</td></tr>'
    '<tr><td colspan="2" style="' + _CELL + '">PUESTO: '
    '<strong>{{trabajador.puesto}}</strong></td></tr></table>'
    '<p>Por la presente, y a tenor de lo establecido en el artículo 18.1 '
    'de la Ley 31/1995, de 8 de noviembre, de Prevención de Riesgos '
    'Laborales, la empresa hace entrega al trabajador de la información '
    'en materia preventiva en relación con los trabajos que tiene '
    'encomendados como trabajador de la empresa '
    '<strong>{{empresa.razon_social}}</strong> de copia de evaluación de '
    'riesgos del lugar y puesto de trabajo así como de los equipos de '
    'trabajo, que en su caso, vaya a utilizar, las medidas preventivas de '
    'los mismos, los esquemas operacionales para actuación en caso de '
    'emergencia e información de primeros auxilios.</p>'
    '<p>Esta empresa ha adoptado las medidas de protección que deberán ser '
    'tenidas en cuenta y aplicadas sin excusa alguna por usted.</p>'
    + _SIGNATURES
)

NOMBRAMIENTO_RECURSO_PREVENTIVO = (
    _TITLE % 'ENTREGA INFORMACIÓN FUNCIONES RECURSO PREVENTIVO'
    + '<p>TRABAJADOR: <strong>{{trabajador.nombre_completo}}</strong><br>'
    'DNI: <strong>{{trabajador.dni}}</strong></p>'
    '<p>A la fecha se le informa al siguiente trabajador de las siguientes '
    'funciones que tiene como recurso preventivo en obra.</p>'
    '<p><u>Funciones del Recurso Preventivo</u><br>'
    'Recogidas en el apartado 4 del artículo 22 bis del RSP</p>'
    '<p>a) Vigilar el cumplimiento de las actividades preventivas en '
    'relación con los riesgos derivados de la situación que determine su '
    'necesidad para conseguir un adecuado control de dichos riesgos.</p>'
    '<p>Esta vigilancia incluirá:</p>'
    '<ul><li>Comprobar la eficacia de las actividades preventivas '
    'previstas en la planificación.</li>'
    '<li>La adecuación de tales actividades a los riesgos que pretenden '
    'prevenirse o la aparición de riesgos no previstos y derivados de la '
    'situación que determina la necesidad de la presencia de recursos '
    'preventivos.</li></ul>'
    '<p>b) Si, como resultado de la vigilancia, se observase un deficiente '
    'cumplimiento de las actividades preventivas, las personas a las que '
    'se asigne la presencia:</p>'
    '<ul><li>Harán las indicaciones necesarias para el correcto e '
    'inmediato cumplimiento de las actividades preventivas.</li>'
    '<li>Deberán poner tales circunstancias en conocimiento del empresario '
    'para que éste adopte las medidas necesarias para corregir las '
    'deficiencias observadas si éstas no hubieran sido aún subsanadas.'
    '</li></ul>'
    + _SIGNATURES
)

TEMPLATES = {
    "ENTREGA_INFORMACION": ENTREGA_INFORMACION,
    "NOMBRAMIENTO_RECURSO_PREVENTIVO": NOMBRAMIENTO_RECURSO_PREVENTIVO,
}


def fill_templates(apps, schema_editor):
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code, html in TEMPLATES.items():
        catalog.objects.filter(code=code, content_html="").update(
            content_html=html,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0162_requires_signature_s124'),
    ]

    operations = [
        migrations.RunPython(fill_templates, migrations.RunPython.noop),
    ]
