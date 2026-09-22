# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0131_contenido_real_circulares_con_ejemplo_s114.py
"""
H31 (S114). Miguel Ángel: "todas las que ya tenemos con documento de
ejemplo" -- rellena `content_html` con el texto real de las 6
plantillas de comunicación que tenían un documento de ejemplo real
(archivo o histórico), 5 de las 6 con variables ya puestas en su
sitio (nunca insertadas "a mano" después, escritas ya donde van, tal
como se acordó en esta misma sesión):

- CIRCULAR_INFORMATIVA: texto real de "CIRCULAR INFORMATIVA PERMISO
  CONDUCIR.pdf" (Grupo Álvarez, membrete real verificado). Sin
  variables de trabajador -- es una circular dirigida a "todos los
  empleados", nunca a uno solo.
- RECURSO_PREVENTIVO: texto real de "PLANTILLA_RECURSO_PREVENTIVO.docx"
  (restaurada de papelera en la migración 0129).
- NOMBRAMIENTO_JEFE_MANIOBRAS: texto real de
  "PLANTILLA_NOMBRAMIENTO_JEFE_MANIOBRAS.docx".
- NOMBRAMIENTO_RESPONSABLE_SEGURIDAD: texto real de
  "PLANTILLA_NOMBRAMIENTO_RESPONSABLE_SEGURIDAD.docx".
- INFORMACION_MEDIDAS_PROTECCION: texto real de
  "PLANTILLA_MEDIDAS_ADICIONALES_PROTECCION.docx" -- conserva como
  texto libre (nunca variable) los huecos que dependen del incidente
  concreto (obra, deficiencia detectada, medida adoptada), que no
  salen de ninguna tabla de la base de datos.

PLAN_ACTUACION_CALOR queda FUERA a propósito: su "documento de
ejemplo" (PLAN DE ACTUACION FRENTE AL CALOR_signed (1) gomez
gomez.pdf) resultó ser, al abrirlo, un folleto oficial del Ministerio
de Sanidad ("Plan nacional de actuaciones preventivas de los efectos
del exceso de temperatura sobre la salud 2025") firmado como acuse de
recibo -- no un texto redactado por Grupo Álvarez con huecos que
rellenar. No tiene sentido convertirlo en plantilla con variables;
sigue funcionando tal cual con su `current_template` en archivo
(restaurado en la migración 0129), sin `content_html`.
"""
from django.db import migrations


_CIRCULAR_INFORMATIVA_HTML = (
    "<p>Málaga, a {{fecha}}.</p>"
    "<p><strong>A todos los empleados de la empresa:</strong></p>"
    "<p>Con la presente se comunica la obligación por parte del trabajador "
    "de informar a la empresa en el momento que ocurra alguna de las "
    "siguientes circunstancias referente a su permiso de conducción:</p>"
    "<ul>"
    "<li>Pérdida de vigencia.</li>"
    "<li>Suspensión cautelar (artículo 72 de la Ley sobre Tráfico, "
    "Circulación de Vehículos a Motor y Seguridad Vial).</li>"
    "<li>Privación del derecho a conducir vehículos a motor temporalmente "
    "en cumplimiento de sentencia penal.</li>"
    "</ul>"
    "<p>Ya que la conducción sin permiso en vigor supone un delito según "
    "establece la Ley de Seguridad Vial.</p>"
    "<p>Atentamente,</p>"
    "<p><strong>La Dirección</strong></p>"
)

_RECURSO_PREVENTIVO_HTML = (
    "<p>En Málaga, a {{fecha}}.</p>"
    "<p>Sr. D. {{trabajador.nombre_completo}}, con DNI nº {{trabajador.dni}}</p>"
    "<p>Muy señor nuestro:</p>"
    "<p>Tanto la Ley 54/03 como el RD 171/04 incorporan medidas de "
    "prevención a través de la designación -- por parte de la empresa "
    "{{empresa.razon_social}} -- de un trabajador especialmente designado "
    "a contemplar que se cumplan las diversas medidas preventivas en los "
    "centros de trabajo. La ley 54/03 contempla a un supervisor presencial "
    "suficientemente cualificado con nivel básico en prevención y asistido "
    "por un SPA debiendo permanecer en el centro de trabajo mientras "
    "persista la situación de peligro.</p>"
    "<p>Tras lo acordado con Usted verbalmente, la empresa ha decidido "
    "designarle para el desempeño de las siguientes actividades "
    "preventivas:</p>"
    "<ul>"
    "<li>Vigilar el cumplimiento de las medidas preventivas desarrolladas "
    "en el Plan de Prevención como recurso preventivo en el centro de "
    "trabajo cuando se realicen actividades o procesos reglamentariamente "
    "considerados como peligrosos o con riesgos especiales.</li>"
    "<li>Control de la correcta aplicación de los métodos de trabajo "
    "cuando los riesgos puedan agravarse o modificarse en el desarrollo "
    "de la actividad.</li>"
    "<li>A requerimiento de la Autoridad Laboral debido a las condiciones "
    "de trabajo detectadas en el centro de trabajo.</li>"
    "</ul>"
    "<p>Las atribuciones, características, garantías, deberes y funciones "
    "vienen definidas por los artículos 30 de la Ley y 13 del Reglamento, "
    "anteriormente citados.</p>"
    "<p>Para su información le comunicamos que esta designación ha sido "
    "consultada con los representantes de los trabajadores, de acuerdo "
    "con lo indicado por el artículo 33 de la mencionada Ley.</p>"
    "<p>Rogándole firme el duplicado de la presente comunicación como "
    "acuse de recibo y aceptación de la designación, aprovechamos la "
    "ocasión para saludarle atentamente.</p>"
    "<p>Acepto la designación.</p>"
    "<p>Por parte de la empresa: {{administrador.nombre_completo}}<br>"
    "Fdo.: {{administrador.nombre_completo}}</p>"
)

_NOMBRAMIENTO_JEFE_MANIOBRAS_HTML = (
    "<p>En la fecha indicada ({{fecha}}), D. {{administrador.nombre_completo}} "
    "en calidad de ADMINISTRADOR de la Empresa subcontratista de "
    "{{empresa.razon_social}}, COMUNICA que la persona designada/asignada "
    "como RESPONSABLE DE LOS TRABAJOS (JEFE DE MANIOBRAS) durante el "
    "periodo de ejecución de los trabajos asignados en la obra "
    "____________________ es D. {{trabajador.nombre_completo}} con D.N.I. "
    "nº {{trabajador.dni}}, el cual ha sido designado por D. "
    "{{administrador.nombre_completo}}.</p>"
    "<p>Atentamente.</p>"
    "<p>TRANSMITE: {{administrador.nombre_completo}} -- Posición: "
    "ADMINISTRADOR -- FECHA: {{fecha}}<br>"
    "RECIBE: {{trabajador.nombre_completo}} -- FECHA: {{fecha}}</p>"
)

_NOMBRAMIENTO_RESPONSABLE_SEGURIDAD_HTML = (
    "<p>En la fecha indicada ({{fecha}}), D. {{administrador.nombre_completo}} "
    "en calidad de ADMINISTRADOR de la Empresa subcontratista de "
    "{{empresa.razon_social}}, COMUNICA que la persona designada/asignada "
    "como INTERLOCUTOR EN MATERIA DE SEGURIDAD durante el periodo de "
    "ejecución de los trabajos en la obra ____________________ es D. "
    "{{trabajador.nombre_completo}} con D.N.I. nº {{trabajador.dni}}, el "
    "cual ha sido designado por D. {{administrador.nombre_completo}}.</p>"
    "<p>Atentamente.</p>"
    "<p>TRANSMITE: {{administrador.nombre_completo}} -- Posición: "
    "ADMINISTRADOR -- FECHA: {{fecha}}<br>"
    "RECIBE: {{trabajador.nombre_completo}} -- FECHA: {{fecha}}</p>"
)

_INFORMACION_MEDIDAS_PROTECCION_HTML = (
    "<p>En Málaga, a {{fecha}}.</p>"
    "<p>Nombre: {{trabajador.nombre_completo}}</p>"
    "<p>Identificación de la obra: ____________________</p>"
    "<p>El trabajador {{trabajador.nombre_completo}}, perteneciente a la "
    "empresa {{empresa.razon_social}} reconoce haber sido Informado por su "
    "empresa de las medidas de seguridad, adicionales, que ha de tomar "
    "ante la carencia de sistema de protección detectado en las "
    "instalaciones de la empresa ____________________ en "
    "____________________,</p>"
    "<p>ADVIRTIENDO QUE:</p>"
    "<p>[Descripción de la deficiencia/carencia de protección detectada "
    "en obra]</p>"
    "<p>MEDIDA PREVENTIVA:</p>"
    "<p>[Medida de protección colectiva adoptada]</p>"
    "<p>Con respecto a la protección individual el trabajador:</p>"
    "<p>[Medida de protección individual adoptada -- 1]</p>"
    "<p>[Medida de protección individual adoptada -- 2, quitar esta línea "
    "si no aplica]</p>"
    "<p>En prueba de conformidad firma:</p>"
    "<p>NOMBRE Y APELLIDOS: {{trabajador.nombre_completo}} -- DNI: "
    "{{trabajador.dni}}</p>"
)

_CONTENT_BY_CODE = {
    "CIRCULAR_INFORMATIVA": _CIRCULAR_INFORMATIVA_HTML,
    "RECURSO_PREVENTIVO": _RECURSO_PREVENTIVO_HTML,
    "NOMBRAMIENTO_JEFE_MANIOBRAS": _NOMBRAMIENTO_JEFE_MANIOBRAS_HTML,
    "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD": _NOMBRAMIENTO_RESPONSABLE_SEGURIDAD_HTML,
    "INFORMACION_MEDIDAS_PROTECCION": _INFORMACION_MEDIDAS_PROTECCION_HTML,
}


def seed_content(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code, html in _CONTENT_BY_CODE.items():
        DocumentTypeCatalog.objects.filter(code=code).update(content_html=html)


def unseed_content(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=_CONTENT_BY_CODE.keys(),
    ).update(content_html="")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0130_companyfiscalprofile_administrator_s114"),
    ]

    operations = [
        migrations.RunPython(
            seed_content, unseed_content,
        ),
    ]
