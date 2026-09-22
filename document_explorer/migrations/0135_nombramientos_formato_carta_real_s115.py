# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0135_nombramientos_formato_carta_real_s115.py
"""
H31 (S115). Reescribe el formato de las dos plantillas de
nombramiento (NOMBRAMIENTO_RESPONSABLE_SEGURIDAD,
NOMBRAMIENTO_JEFE_MANIOBRAS) -- de "notificación" (COMUNICA...
TRANSMITE/RECIBE) a carta formal de designación, con la MISMA
estructura que el nombramiento real de Grupo Álvarez que Miguel
Ángel mostró como referencia (título recuadrado, fila FECHA/EMPRESA,
"Sr. D./DNI.-", salutación "Muy Sr. nuestro:", cuerpo con cita legal,
bloque de firmas empresa/trabajador/representante).

Miguel Ángel, verbatim: "no estoy viendo un documento, estoy viendo
una notificación [...] cuando le doy a ver la notificación, quiero
ver el documento que va a recibir la empresa a la que le envíe yo
ese documento en el dossier."

NOMBRAMIENTO_RESPONSABLE_SEGURIDAD: la cita legal (artículos 30.1,
32 Bis.1, 32 Bis.2, 33 y 32 Bis.3 de la Ley de Prevención de Riesgos
Laborales) se copia LITERAL del documento real de referencia
("NOMBRAMIENTO DE ENCARGADO DE SEGURIDAD", Grupo Álvarez, mismo rol)
-- no inventada.

NOMBRAMIENTO_JEFE_MANIOBRAS: mismo formato de carta, pero SIN cita de
artículos legales -- no hay documento real de referencia verificado
para este rol concreto (jefe de maniobras no es una figura definida
en la Ley de PRL como "encargado/interlocutor de seguridad"), así
que el cuerpo se queda descriptivo, sin inventar una base legal.
Pendiente de que Miguel Ángel confirme o aporte una si existe.

Reversible: la reversa restaura el texto de notificación anterior
(S114, migración 0131) tal cual.
"""
from django.db import migrations

_RESPONSABLE_SEGURIDAD_CARTA = (
    '<div style="border:2px solid #000;padding:8px;text-align:center;'
    'font-weight:bold;font-size:14pt;margin-bottom:12px;">'
    "NOMBRAMIENTO DE INTERLOCUTOR EN MATERIA DE SEGURIDAD</div>"
    '<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">'
    '<tr><td style="border:1px solid #000;padding:4px;width:50%;">'
    "<strong>FECHA:</strong> {{fecha}}</td>"
    '<td style="border:1px solid #000;padding:4px;">'
    "<strong>EMPRESA:</strong> {{empresa.razon_social}}</td></tr></table>"
    "<p><strong>Sr. D.:</strong> {{trabajador.nombre_completo}} &nbsp;&nbsp; "
    "<strong>DNI.-</strong> {{trabajador.dni}}</p>"
    "<p>En Málaga, a {{fecha}}.</p>"
    "<p>Muy Sr. nuestro:</p>"
    "<p>Por la presente le comunicamos que la empresa ha decidido, al amparo "
    "de lo indicado en los artículos 30.1, 32 Bis.1 y 32 Bis.2 de la Ley de "
    "Prevención de Riesgos Laborales, y previa consulta de los trabajadores, "
    "según lo dispuesto en el artículo 33 de dicha Ley, designarle para "
    "ocuparse de la actividad de prevención de riesgos profesionales en el "
    "ámbito de la empresa, nombrándole \"interlocutor en materia de "
    "seguridad\" de la misma en la obra {{obra.nombre}}, de la empresa "
    "{{obra.cliente}}.</p>"
    "<p>Las características, capacidad, atribuciones y funciones vienen "
    "desarrolladas en los artículos 30 y 32 Bis.3 de la Ley de Prevención "
    "de Riesgos Laborales.</p>"
    "<p>Rogándole firme el duplicado de esta carta, como acuse de recibo y "
    "aceptación de la designación, le saludamos muy atentamente.</p>"
    '<table style="width:100%;margin-top:40px;"><tr>'
    '<td style="width:33%;text-align:center;">Por la empresa:<br><br><br>'
    "Fdo.: {{administrador.nombre_completo}}</td>"
    '<td style="width:33%;text-align:center;">Por el trabajador:<br><br><br>'
    "Fdo.: {{trabajador.nombre_completo}}</td>"
    '<td style="width:34%;text-align:center;">Representante de los '
    "trabajadores:<br><br><br>Fdo.: ___________________</td>"
    "</tr></table>"
)

_JEFE_MANIOBRAS_CARTA = (
    '<div style="border:2px solid #000;padding:8px;text-align:center;'
    'font-weight:bold;font-size:14pt;margin-bottom:12px;">'
    "NOMBRAMIENTO DE RESPONSABLE DE LOS TRABAJOS (JEFE DE MANIOBRAS)</div>"
    '<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">'
    '<tr><td style="border:1px solid #000;padding:4px;width:50%;">'
    "<strong>FECHA:</strong> {{fecha}}</td>"
    '<td style="border:1px solid #000;padding:4px;">'
    "<strong>EMPRESA:</strong> {{empresa.razon_social}}</td></tr></table>"
    "<p><strong>Sr. D.:</strong> {{trabajador.nombre_completo}} &nbsp;&nbsp; "
    "<strong>DNI.-</strong> {{trabajador.dni}}</p>"
    "<p>En Málaga, a {{fecha}}.</p>"
    "<p>Muy Sr. nuestro:</p>"
    "<p>Por la presente le comunicamos que la empresa ha decidido "
    'designarle como "responsable de los trabajos (jefe de maniobras)" '
    "durante el periodo de ejecución de los trabajos asignados en la obra "
    "{{obra.nombre}}, de la empresa {{obra.cliente}}.</p>"
    "<p>Rogándole firme el duplicado de esta carta, como acuse de recibo y "
    "aceptación de la designación, le saludamos muy atentamente.</p>"
    '<table style="width:100%;margin-top:40px;"><tr>'
    '<td style="width:33%;text-align:center;">Por la empresa:<br><br><br>'
    "Fdo.: {{administrador.nombre_completo}}</td>"
    '<td style="width:33%;text-align:center;">Por el trabajador:<br><br><br>'
    "Fdo.: {{trabajador.nombre_completo}}</td>"
    '<td style="width:34%;text-align:center;">Representante de los '
    "trabajadores:<br><br><br>Fdo.: ___________________</td>"
    "</tr></table>"
)

_OLD_RESPONSABLE_SEGURIDAD = (
    "<p>En la fecha indicada ({{fecha}}), D. {{administrador.nombre_completo}} "
    "en calidad de ADMINISTRADOR de la Empresa subcontratista de "
    "{{empresa.razon_social}}, COMUNICA que la persona designada/asignada "
    "como INTERLOCUTOR EN MATERIA DE SEGURIDAD durante el periodo de "
    "ejecución de los trabajos en la obra {{obra.nombre}} es D. "
    "{{trabajador.nombre_completo}} con D.N.I. nº {{trabajador.dni}}, el "
    "cual ha sido designado por D. {{administrador.nombre_completo}}.</p>"
    "<p>Atentamente.</p>"
    "<p>TRANSMITE: {{administrador.nombre_completo}} -- Posición: "
    "ADMINISTRADOR -- FECHA: {{fecha}}<br>"
    "RECIBE: {{trabajador.nombre_completo}} -- FECHA: {{fecha}}</p>"
)

_OLD_JEFE_MANIOBRAS = (
    "<p>En la fecha indicada ({{fecha}}), D. {{administrador.nombre_completo}} "
    "en calidad de ADMINISTRADOR de la Empresa subcontratista de "
    "{{empresa.razon_social}}, COMUNICA que la persona designada/asignada "
    "como RESPONSABLE DE LOS TRABAJOS (JEFE DE MANIOBRAS) durante el "
    "periodo de ejecución de los trabajos asignados en la obra "
    "{{obra.nombre}} es D. {{trabajador.nombre_completo}} con D.N.I. "
    "nº {{trabajador.dni}}, el cual ha sido designado por D. "
    "{{administrador.nombre_completo}}.</p>"
    "<p>Atentamente.</p>"
    "<p>TRANSMITE: {{administrador.nombre_completo}} -- Posición: "
    "ADMINISTRADOR -- FECHA: {{fecha}}<br>"
    "RECIBE: {{trabajador.nombre_completo}} -- FECHA: {{fecha}}</p>"
)


def to_carta(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    dt = DocumentTypeCatalog.objects.filter(code="NOMBRAMIENTO_RESPONSABLE_SEGURIDAD").first()
    if dt is not None:
        dt.content_html = _RESPONSABLE_SEGURIDAD_CARTA
        dt.save(update_fields=["content_html"])
    dt = DocumentTypeCatalog.objects.filter(code="NOMBRAMIENTO_JEFE_MANIOBRAS").first()
    if dt is not None:
        dt.content_html = _JEFE_MANIOBRAS_CARTA
        dt.save(update_fields=["content_html"])


def to_notificacion(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    dt = DocumentTypeCatalog.objects.filter(code="NOMBRAMIENTO_RESPONSABLE_SEGURIDAD").first()
    if dt is not None:
        dt.content_html = _OLD_RESPONSABLE_SEGURIDAD
        dt.save(update_fields=["content_html"])
    dt = DocumentTypeCatalog.objects.filter(code="NOMBRAMIENTO_JEFE_MANIOBRAS").first()
    if dt is not None:
        dt.content_html = _OLD_JEFE_MANIOBRAS
        dt.save(update_fields=["content_html"])


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0134_circulares_obra_variable_s115"),
    ]

    operations = [
        migrations.RunPython(to_carta, to_notificacion),
    ]
