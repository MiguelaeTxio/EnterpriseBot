# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0079_seed_document_tags_machine_company_epi_s98.py
"""
H31 (S98). Segunda ronda de DocumentTag, tras la de PERSONAL (0077/
0078): puebla las asignaciones DocumentTypeCatalog.tags para los 63
tipos de dominio MACHINE, COMPANY y EPI. Revisado y aprobado por
Miguel Angel antes de aplicar (misma disciplina que la ronda
anterior).

Sin evidencia real de nombre de archivo disponible para estos
dominios (el barrido de renombrado de esta sesion fue solo PERSONAL)
-- se apoya en vocabulario administrativo/tecnico estandar mas
verificacion en linea de los acronimos no evidentes (OCA = Organismo
de Control Autorizado, IPO = Inspeccion Periodica Obligatoria, RAE =
Registro de Aparatos Elevadores).

Reutiliza etiquetas ya creadas en la ronda PERSONAL donde aplica
(CERTIFICADO, AUTORIZACION, CONTRATO, DNI, BANCO, CONVENIO, HACIENDA,
COMUNICACION, INFORME, SOLICITUD, PROVISIONAL, EPI) -- get_or_create
las respeta sin duplicar. Sin ANVERSO/REVERSO/FOTO_DOCUMENTO ni
equivalentes, mismo criterio que 0077.

Reversible con el mismo criterio que 0077/0078: solo deshace lo que
esta migracion creo/asigno.
"""
from django.db import migrations


TAG_LABELS = {'ACCESORIO_ELEVACION': 'Accesorio de elevación',
 'ADECUACION': 'Adecuación',
 'ALBARAN': 'Albarán',
 'ALQUILER': 'Alquiler',
 'AMORTIZACION': 'Amortización',
 'ARRENDAMIENTO': 'Arrendamiento',
 'AUTOLIQUIDACION': 'Autoliquidación',
 'AUTORIZACION': 'Autorización',
 'AUTORIZACION_CIRCULACION': 'Autorización de circulación',
 'AVISO_BAJA': 'Aviso de baja',
 'BAJA_DEFINITIVA': 'Baja definitiva',
 'BAJA_MAQUINA': 'Baja de máquina',
 'BAJA_TEMPORAL': 'Baja temporal',
 'BANCO': 'Banco',
 'CAMBIO_TITULARIDAD': 'Cambio de titularidad',
 'CAPACIDAD_CARGA': 'Capacidad de carga',
 'CARTA_VERDE': 'Carta verde',
 'CATALOGO_PIEZAS': 'Catálogo de piezas',
 'CERTIFICADO': 'Certificado',
 'CIRCULACION': 'Circulación',
 'CIRCULAR': 'Circular',
 'COMBUSTIBLE': 'Combustible',
 'COMPRA': 'Compra',
 'COMPRAVENTA': 'Compraventa',
 'COMUNICACION': 'Comunicación',
 'COMUNICADO_EMPRESA': 'Comunicado de empresa',
 'CONFORMIDAD': 'Conformidad',
 'CONTRATO': 'Contrato',
 'CONVENIO': 'Convenio',
 'CORRIENTE_PAGO': 'Corriente de pagos',
 'COVID': 'COVID',
 'CUOTA': 'Cuota',
 'DECLARACION_CE': 'Declaración CE de conformidad',
 'DECLARACION_EMPRESA': 'Declaración de empresa',
 'DESPLAZAMIENTO': 'Desplazamiento',
 'DGT': 'DGT',
 'DNI': 'DNI',
 'DNI_COMPRADOR': 'DNI de comprador',
 'ELECCIONES_SINDICALES': 'Elecciones sindicales',
 'ENCOMIENDA_GESTION': 'Encomienda de gestión',
 'ENTREGA_MERCANCIA': 'Entrega de mercancía',
 'EPI': 'EPI',
 'EPI_FICHA': 'Ficha técnica de EPI',
 'ESLINGAS': 'Eslingas',
 'ESTADO_ALARMA': 'Estado de alarma',
 'EXENCION_PERMISO': 'Exención de permiso',
 'FABRICANTE': 'Fabricante',
 'FACTURA': 'Factura',
 'FACTURA_COMPRA': 'Factura de compra',
 'FACTURA_VENTA': 'Factura de venta',
 'FICHA_TECNICA': 'Ficha técnica',
 'FINANCIACION': 'Financiación',
 'FORMACION_BONIFICADA': 'Formación bonificada',
 'FUNDAE': 'FUNDAE',
 'GARANTIA': 'Garantía',
 'GASTOS': 'Gastos',
 'GRUA': 'Grúa',
 'HACIENDA': 'Hacienda',
 'HISTORIAL_MAQUINA': 'Historial de la máquina',
 'HOMOLOGACION': 'Homologación',
 'IEDMT': 'IEDMT (Impuesto de Matriculación)',
 'IMPUESTO': 'Impuesto',
 'IMPUESTO_CIRCULACION': 'Impuesto de circulación',
 'IMPUESTO_MATRICULACION': 'Impuesto de matriculación',
 'INCIDENCIAS': 'Incidencias',
 'INFORME': 'Informe',
 'INFORME_DGT': 'Informe DGT',
 'INSPECCION_REGLAMENTARIA': 'Inspección reglamentaria',
 'INSPECCION_TECNICA': 'Inspección técnica de vehículos',
 'IPO': 'IPO (Inspección Periódica Obligatoria)',
 'ITC': 'ITC (Instrucción Técnica Complementaria)',
 'ITV': 'ITV',
 'IVTM': 'IVTM',
 'IZADO': 'Izado',
 'JUSTIFICANTE_BANCARIO': 'Justificante bancario',
 'LEASING': 'Leasing',
 'LIBRO_HISTORIAL': 'Libro historial',
 'LISTADO_OBRA': 'Relación de obra',
 'MANDATO': 'Mandato',
 'MANTENIMIENTO': 'Mantenimiento',
 'MANUAL_DESPIECE': 'Manual de despiece',
 'MANUAL_INSTRUCCIONES': 'Manual de instrucciones',
 'MANUAL_USO': 'Manual de uso',
 'MAQUINARIA': 'Maquinaria',
 'MARCADO_CE': 'Marcado CE',
 'MATRICULACION': 'Matriculación',
 'MULTA': 'Multa',
 'OCA': 'OCA',
 'ORGANISMO_CONTROL': 'Organismo de Control Autorizado',
 'PAGO_CORRIENTE': 'Al corriente de pago de salarios',
 'PEDIDO': 'Pedido',
 'PERMISO_CIRCULACION': 'Permiso de circulación',
 'PLANTILLA': 'Plantilla de trabajadores',
 'PODERES': 'Poderes',
 'POLIZA': 'Póliza de seguro',
 'PRESTAMO': 'Préstamo',
 'PRESUPUESTO': 'Presupuesto',
 'PROFORMA': 'Proforma',
 'PROVISIONAL': 'Provisional',
 'PROVISION_FONDOS': 'Provisión de fondos',
 'RAE': 'RAE (Registro de Aparatos Elevadores)',
 'RECIBO': 'Recibo',
 'RECIBO_SEGURO': 'Recibo del seguro',
 'REFORMA_VEHICULO': 'Reforma de vehículo',
 'REGISTRO_APARATOS_ELEVADORES': 'Registro de Aparatos Elevadores',
 'REGISTRO_VEHICULOS': 'Registro General de Vehículos',
 'REPRESENTACION': 'Representación',
 'REPRESENTANTES_TRABAJADORES': 'Representantes de los trabajadores',
 'RETENCIONES': 'Retenciones',
 'REVISION': 'Revisión',
 'SANCION': 'Sanción',
 'SEGURO': 'Seguro',
 'SEGURO_INTERNACIONAL': 'Seguro internacional',
 'SEÑAL': 'Señal / depósito',
 'SOLICITUD': 'Solicitud',
 'TABLA_CARGA': 'Tabla de carga',
 'TACOGRAFO_REVISION': 'Revisión del tacógrafo',
 'TARJETA_COMBUSTIBLE': 'Tarjeta de combustible',
 'TARJETA_TRANSPORTE': 'Tarjeta de transporte',
 'TARJETA_TRANSPORTE_CIRCULACION': 'Tarjeta de transporte',
 'TITULARIDAD': 'Titularidad',
 'TRAFICO': 'Tráfico',
 'TRANSFERENCIA': 'Transferencia bancaria',
 'VEHICULO': 'Vehículo',
 'VENTA': 'Venta'}

TYPE_TAGS = {'ACTA_ELECCIONES_SINDICALES': ['ELECCIONES_SINDICALES',
                                'REPRESENTANTES_TRABAJADORES'],
 'ALBARAN_ENTREGA': ['ALBARAN', 'ENTREGA_MERCANCIA'],
 'AUTORIZACION_PROVISIONAL_CIRCULACION': ['AUTORIZACION',
                                          'AUTORIZACION_CIRCULACION',
                                          'CIRCULACION',
                                          'PROVISIONAL'],
 'AVISO_BAJA': ['AVISO_BAJA', 'BAJA_MAQUINA', 'COMUNICACION'],
 'BAJA_DEFINITIVA': ['BAJA_MAQUINA', 'BAJA_DEFINITIVA'],
 'BAJA_TEMPORAL': ['BAJA_MAQUINA', 'BAJA_TEMPORAL'],
 'CAMBIO_TITULARIDAD': ['CAMBIO_TITULARIDAD',
                        'TITULARIDAD',
                        'SOLICITUD'],
 'CARTA_VERDE': ['CARTA_VERDE', 'SEGURO', 'SEGURO_INTERNACIONAL'],
 'CE': ['DECLARACION_CE', 'MARCADO_CE', 'CONFORMIDAD'],
 'CERTIFICADO_JUSTIFICACION_DESPLAZAMIENTO': ['DESPLAZAMIENTO',
                                              'COVID',
                                              'ESTADO_ALARMA',
                                              'CERTIFICADO'],
 'CERTIFICADO_PODERES': ['PODERES',
                         'REPRESENTACION',
                         'MANDATO',
                         'CERTIFICADO'],
 'CERT_ACCESORIO_ELEVACION': ['ACCESORIO_ELEVACION',
                              'CERTIFICADO',
                              'ESLINGAS',
                              'IZADO'],
 'CERT_EXENCION_PERMISO': ['EXENCION_PERMISO',
                           'CERTIFICADO',
                           'PERMISO_CIRCULACION'],
 'CERT_MANTENIMIENTO': ['MANTENIMIENTO', 'CERTIFICADO'],
 'CERT_NO_TARJ_TTES': ['CERTIFICADO',
                       'TARJETA_TRANSPORTE_CIRCULACION'],
 'CERT_REVISION': ['REVISION', 'CERTIFICADO'],
 'CIRCULAR_INFORMATIVA': ['CIRCULAR',
                          'COMUNICADO_EMPRESA',
                          'COMUNICACION'],
 'CONTRATO_ARRENDAMIENTO': ['ARRENDAMIENTO',
                            'ALQUILER',
                            'CONTRATO',
                            'MAQUINARIA'],
 'CONTRATO_COMPRAVENTA': ['COMPRAVENTA',
                          'CONTRATO',
                          'VENTA',
                          'COMPRA'],
 'CONVENIO_FORMACION_BONIFICADA': ['FUNDAE',
                                   'FORMACION_BONIFICADA',
                                   'ENCOMIENDA_GESTION',
                                   'CONVENIO'],
 'CUADRO_AMORTIZACION': ['AMORTIZACION', 'PRESTAMO', 'LEASING'],
 'C_ADECUACION': ['ADECUACION', 'CERTIFICADO', 'MAQUINARIA'],
 'DECLARACION_EMPRESA': ['DECLARACION_EMPRESA', 'CORRIENTE_PAGO'],
 'DECLARACION_HOMOLOGACION': ['HOMOLOGACION', 'MATRICULACION'],
 'DNI_COMPRADOR': ['DNI_COMPRADOR', 'DNI', 'COMPRA'],
 'FACTURA_COMPRA': ['FACTURA', 'FACTURA_COMPRA', 'COMPRA'],
 'FACTURA_VENTA': ['FACTURA', 'FACTURA_VENTA', 'VENTA'],
 'FICHA_TECNICA': ['FICHA_TECNICA', 'VEHICULO'],
 'FICHA_TECNICA_EPI': ['EPI_FICHA',
                       'FICHA_TECNICA',
                       'EPI',
                       'CONFORMIDAD'],
 'GARANTIA_FABRICANTE': ['GARANTIA', 'FABRICANTE'],
 'GASTOS_TARJETA_COMBUSTIBLE': ['COMBUSTIBLE',
                                'TARJETA_COMBUSTIBLE',
                                'GASTOS'],
 'IEDMT': ['IEDMT',
           'IMPUESTO',
           'IMPUESTO_MATRICULACION',
           'MATRICULACION'],
 'INFORME_INCIDENCIAS': ['INCIDENCIAS', 'INFORME'],
 'INFORME_VEHICULO_DGT': ['INFORME_DGT',
                          'DGT',
                          'REGISTRO_VEHICULOS',
                          'VEHICULO'],
 'IPO_ITC': ['IPO', 'ITC', 'INSPECCION_REGLAMENTARIA', 'GRUA'],
 'ITV': ['ITV', 'INSPECCION_TECNICA', 'VEHICULO'],
 'IVTM': ['IVTM',
          'IMPUESTO',
          'IMPUESTO_CIRCULACION',
          'AUTOLIQUIDACION'],
 'JUSTIFICANTE_TRANSFERENCIA': ['TRANSFERENCIA',
                                'JUSTIFICANTE_BANCARIO',
                                'BANCO'],
 'LEASING': ['LEASING', 'FINANCIACION', 'CONTRATO'],
 'LIBRO_HISTORIAL': ['LIBRO_HISTORIAL', 'HISTORIAL_MAQUINA'],
 'LISTADO_PERSONAL_MAQUINARIA_OBRA': ['LISTADO_OBRA',
                                      'PLANTILLA',
                                      'MAQUINARIA'],
 'MANUAL_DESPIECE': ['MANUAL_DESPIECE', 'CATALOGO_PIEZAS'],
 'MANUAL_USO': ['MANUAL_USO', 'MANUAL_INSTRUCCIONES'],
 'OCA': ['OCA', 'ORGANISMO_CONTROL', 'INSPECCION_REGLAMENTARIA'],
 'PAGO_CORRIENTE': ['PAGO_CORRIENTE',
                    'CORRIENTE_PAGO',
                    'DECLARACION_EMPRESA'],
 'PEDIDO_COMPRA': ['PEDIDO', 'COMPRA'],
 'PERMISO_CIRCULACION': ['PERMISO_CIRCULACION', 'CIRCULACION'],
 'PLANTILLA': ['PLANTILLA'],
 'POLIZA_SEGURO': ['POLIZA', 'SEGURO'],
 'PRESTAMO': ['PRESTAMO', 'BANCO', 'FINANCIACION'],
 'PROFORMA': ['PROFORMA', 'PRESUPUESTO'],
 'PROVISION_FONDOS': ['PROVISION_FONDOS', 'AUTORIZACION'],
 'RAE': ['RAE', 'REGISTRO_APARATOS_ELEVADORES', 'GRUA'],
 'RECIBO_LEASING': ['RECIBO', 'LEASING', 'CUOTA'],
 'RECIBO_SENAL_COMPRA': ['RECIBO', 'SEÑAL', 'COMPRA'],
 'REFORMA_VEHICULO': ['REFORMA_VEHICULO', 'VEHICULO', 'CERTIFICADO'],
 'RETENCIONES': ['RETENCIONES', 'CERTIFICADO', 'HACIENDA'],
 'REVISION_ESLINGAS': ['ESLINGAS', 'IZADO', 'REVISION'],
 'REV_TACOGRAFO': ['TACOGRAFO_REVISION', 'REVISION'],
 'SANCION_TRAFICO': ['SANCION', 'MULTA', 'TRAFICO'],
 'SEGURO': ['SEGURO', 'RECIBO_SEGURO', 'RECIBO'],
 'TABLA_DE_CARGA': ['TABLA_CARGA', 'CAPACIDAD_CARGA', 'GRUA'],
 'TARJETA_TRANSPORTE': ['TARJETA_TRANSPORTE', 'CIRCULACION']}


def seed_tags(apps, schema_editor):
    DocumentTag = apps.get_model("document_explorer", "DocumentTag")
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )

    tag_objs = {}
    for code, label in TAG_LABELS.items():
        tag_objs[code], _ = DocumentTag.objects.get_or_create(
            code=code, defaults={"label": label},
        )

    for type_code, tag_codes in TYPE_TAGS.items():
        try:
            doc_type = DocumentTypeCatalog.objects.get(code=type_code)
        except DocumentTypeCatalog.DoesNotExist:
            continue
        doc_type.tags.set([tag_objs[c] for c in tag_codes])


def unseed_tags(apps, schema_editor):
    DocumentTag = apps.get_model("document_explorer", "DocumentTag")
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for doc_type in DocumentTypeCatalog.objects.filter(
        code__in=list(TYPE_TAGS.keys()),
    ):
        doc_type.tags.clear()
    # Solo borra las etiquetas que ESTA migración creó de cero -- las
    # reutilizadas de la ronda PERSONAL (ya existían) se dejan intactas.
    created_here = set(TAG_LABELS.keys()) - {
        "CERTIFICADO", "AUTORIZACION", "SOLICITUD", "COMUNICACION",
        "INFORME", "CONTRATO", "DNI", "BANCO", "CONVENIO", "HACIENDA",
        "PROVISIONAL", "EPI",
    }
    DocumentTag.objects.filter(code__in=list(created_here)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0078_seed_document_tags_personal_missing_s98"),
    ]

    operations = [
        migrations.RunPython(seed_tags, unseed_tags),
    ]
