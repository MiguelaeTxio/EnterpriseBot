# C:\EnterpriseBot\h28_migration_agent\generate_synthetic_augmentation.py
"""
H30 (S55). Generador de aumentacion sintetica MASIVA para los tipos
documentales que quedaron con muy pocos ejemplos reales en el
entrenamiento de `train_document_classifier.py`.

Decision explicita de Miguel Angel (S55): en vez de un puñado de
plantillas escritas a mano (5-10 por tipo, techo bajo), generar
cientos de variantes por combinacion de plantillas + datos FICTICIOS
(nombres, DNIs, matriculas, importes, fechas de una lista generica
random, nunca de una persona real ni de un documento real descargado
de internet). Mismo criterio que cualquier libreria de generacion de
datos sinteticos (tipo Faker): nombres comunes genericos, sin relacion
con ningun trabajador ni cliente real de Grupo Alvarez ni de ninguna
otra empresa.

Estructura de cada plantilla verificada contra fuentes reales por
busqueda web en la propia sesion S55 (INSST NTP 861, normas EN 818-4/
EN 1677 para eslingas, articulo 46 del Estatuto de los Trabajadores
para excedencias, reglamento de facturacion RD 1619/2012, Codigo Civil
articulo 1454 para arras) -- las plantillas base viven en este
archivo, parafraseadas, nunca copiadas literalmente de ninguna fuente.

USO:
    python generate_synthetic_augmentation.py --per-type 300 --output data_imports/synthetic_augmented.jsonl
"""
import argparse
import json
import random

# --- Pools de datos ficticios, genericos, sin relacion con ninguna
# persona ni empresa real. Nombres comunes espanoles, deliberadamente
# genericos (no coinciden con ningun trabajador real de Grupo Alvarez
# -- verificado no usar ninguno de los nombres reales vistos en la
# sesion).
NOMBRES = [
    "Antonio", "Manuel", "Jose", "Francisco", "David", "Juan", "Javier",
    "Daniel", "Carlos", "Miguel", "Rafael", "Pedro", "Angel", "Alejandro",
    "Maria", "Carmen", "Ana", "Isabel", "Dolores", "Pilar", "Teresa",
    "Rosa", "Cristina", "Laura", "Marta", "Elena", "Beatriz", "Sara",
]
APELLIDOS = [
    "Garcia", "Martinez", "Lopez", "Sanchez", "Perez", "Gonzalez",
    "Rodriguez", "Fernandez", "Gomez", "Diaz", "Moreno", "Alvarez",
    "Romero", "Navarro", "Torres", "Ramirez", "Ruiz", "Gil", "Serrano",
    "Blanco", "Suarez", "Molina", "Ortega", "Delgado", "Castro", "Ortiz",
]
EMPRESAS = [
    "Suministros Industriales del Sur S.L.", "Transportes Beltran S.A.",
    "Comercial Andaluza de Repuestos S.L.", "Grupo Logistico Mediterraneo S.L.",
    "Talleres Reunidos del Guadalquivir S.L.", "Distribuciones Fenix S.A.",
    "Maquinaria y Elevacion Ibericos S.L.", "Recambios Betica S.L.",
]
PROVINCIAS_CIUDADES = [
    "Jerez de la Frontera", "Sevilla", "Cadiz", "Cordoba", "Huelva",
    "Malaga", "Granada", "Almeria", "Jaen",
]


def _fake_dni(rng):
    numero = rng.randint(10000000, 49999999)
    letras = "TRWAGMYFPDXBNJZSQVHLCKE"
    return "%08d%s" % (numero, letras[numero % 23])


def _fake_iban(rng):
    return "ES%02d %04d %04d %02d %010d" % (
        rng.randint(10, 99), rng.randint(1000, 9999),
        rng.randint(1000, 9999), rng.randint(10, 99),
        rng.randint(0, 9999999999),
    )


def _fake_matricula(rng):
    letras = "BCDFGHJKLMNPRSTVWXYZ"
    return "%04d%s%s%s" % (
        rng.randint(0, 9999), rng.choice(letras), rng.choice(letras),
        rng.choice(letras),
    )


def _fake_fecha(rng):
    return "%02d-%02d-%d" % (
        rng.randint(1, 28), rng.randint(1, 12), rng.randint(2018, 2026),
    )


def _fake_nombre_completo(rng):
    return "%s %s %s" % (
        rng.choice(NOMBRES), rng.choice(APELLIDOS), rng.choice(APELLIDOS),
    )


def _fake_importe(rng, lo=20, hi=45000):
    return "%.2f" % rng.uniform(lo, hi)


# --- Plantillas por tipo: cada una es una funcion que recibe el
# generador de aleatoriedad y devuelve una cadena de texto realista,
# con datos ficticios insertados. Varias plantillas por tipo para dar
# variedad estructural real, no solo variedad de datos.

def _tpl_albaran(rng):
    variantes = [
        "ALBARAN DE ENTREGA NUMERO {n} FECHA {f} EMISOR {emp} DESTINATARIO {emp2} "
        "PEDIDO DE REFERENCIA {p} DESCRIPCION DE LA MERCANCIA ENTREGADA CANTIDAD "
        "SERVIDA UNIDADES OBSERVACIONES DE RECEPCION FIRMA Y FECHA DEL DESTINATARIO "
        "COMO CONFIRMACION DOCUMENTO SIN VALOR FISCAL",
        "ALBARAN NUMERO {n} EMPRESA EMISORA {emp} CLIENTE {emp2} DIRECCION DE ENTREGA "
        "EN {ciudad} TRANSPORTISTA MATRICULA DEL VEHICULO DE REPARTO {mat} HORA DE "
        "LLEGADA FIRMA Y SELLO DEL RECEPTOR CONFORME COPIA PARA ARCHIVO DEL PROVEEDOR",
        "ALBARAN DE OBRA {n} OBRA DE DESTINO EN {ciudad} MATERIAL ENTREGADO REFERENCIA "
        "DE PEDIDO {p} FECHA {f} FIRMA DEL ENCARGADO DE OBRA QUE RECIBE CONFORME AL "
        "PEDIDO REALIZADO A {emp}",
        "ALBARAN DE DEVOLUCION {n} MOTIVO DE LA DEVOLUCION MATERIAL DEVUELTO ESTADO "
        "DEL MATERIAL ALBARAN ORIGINAL DE REFERENCIA {p} AUTORIZACION DE DEVOLUCION "
        "ALMACEN RECEPTOR EN {ciudad} FECHA {f} EMPRESA {emp}",
        "ALBARAN DE SUMINISTRO {n} CODIGO DE CLIENTE {emp2} LISTA DE MATERIALES "
        "SUMINISTRADOS CANTIDAD SERVIDA UNIDAD DE MEDIDA ESTADO DEL MATERIAL A LA "
        "ENTREGA FIRMA Y SELLO DEL RECEPTOR FECHA {f}",
    ]
    return rng.choice(variantes).format(
        n=rng.randint(1000, 999999), f=_fake_fecha(rng),
        emp=rng.choice(EMPRESAS), emp2=rng.choice(EMPRESAS),
        p=rng.randint(1000, 99999), ciudad=rng.choice(PROVINCIAS_CIUDADES),
        mat=_fake_matricula(rng),
    )


def _tpl_cert_accesorio_elevacion(rng):
    variantes = [
        "CERTIFICADO ESLINGA DE CADENA NORMA EN 818-4 MARCADO CE NUMERO DE SERIE "
        "{n} CARGA MAXIMA DE UTILIZACION {imp} KG FECHA DE FABRICACION {f} "
        "COEFICIENTE DE SEGURIDAD MINIMO CUATRO VECES LA CARGA DE TRABAJO REAL "
        "FABRICANTE {emp}",
        "CERTIFICADO DE CONFORMIDAD GANCHO DE ELEVACION NORMA EN 1677 NUMERO {n} "
        "CARGA MAXIMA DE UTILIZACION {imp} KG PESTILLO DE SEGURIDAD INCLUIDO FECHA "
        "DE ENSAYO {f} EMPRESA CERTIFICADORA {emp}",
        "FICHA TECNICA Y CERTIFICADO ESLINGA TEXTIL NUMERO DE LOTE {n} LONGITUD "
        "DECLARADA ANGULO DE TRABAJO MAXIMO CARGA MAXIMA DE UTILIZACION {imp} KG "
        "PROXIMA REVISION RECOMENDADA {f} FABRICANTE {emp}",
        "ETIQUETA IDENTIFICATIVA GRILLETE NUMERO {n} MARCADO CE MATERIAL DE "
        "FABRICACION CARGA MAXIMA DE UTILIZACION SEGUN FORMA DE TRABAJO {imp} KG "
        "TRAZABILIDAD MEDIANTE NUMERO DE CERTIFICADO FECHA {f} FABRICANTE {emp}",
        "CERTIFICADO DE ORIGEN CADENA DE ELEVACION GRADO 80 NUMERO {n} CLASIFICACION "
        "POR TAMAÑO DE CADENA CAPACIDAD DE CARGA {imp} KG RIESGO DE FALLO SI SE "
        "EXCEDE LA CAPACIDAD CERTIFICADA FECHA {f}",
    ]
    return rng.choice(variantes).format(
        n=rng.randint(1000, 99999), imp=int(rng.uniform(500, 20000)),
        f=_fake_fecha(rng), emp=rng.choice(EMPRESAS),
    )


def _tpl_cert_revision(rng):
    variantes = [
        "CERTIFICADO DE REVISION PERIODICA EQUIPO REVISADO NUMERO DE SERIE {n} "
        "FECHA DE LA REVISION {f} RESULTADO APTO PROXIMA REVISION OBLIGATORIA "
        "TECNICO REVISOR EMPRESA MANTENEDORA {emp}",
        "CERT REVISION MAQUINARIA NUMERO {n} FECHA {f} HORAS DE USO EN EL MOMENTO "
        "DE LA REVISION ELEMENTOS VERIFICADOS FRENOS SISTEMA HIDRAULICO SISTEMA "
        "ELECTRICO RESULTADO FAVORABLE VALIDEZ HASTA LA SIGUIENTE REVISION",
        "ACTA DE REVISION Y MANTENIMIENTO PREVENTIVO NUMERO {n} PUNTO DE INSPECCION "
        "ESTADO ENCONTRADO ACCION CORRECTORA APLICADA FECHA {f} FIRMA DEL TECNICO "
        "SELLO DE {emp}",
        "CERT.REVISION EQUIPO NUMERO {n} FECHA {f} REVISION REGLAMENTARIA SEGUN "
        "PERIODICIDAD DEL FABRICANTE OBSERVACIONES DEL TECNICO NUMERO DE CERTIFICADO "
        "EMITIDO POR {emp}",
        "INFORME DE REVISION TECNICA PERIODICA NUMERO {n} FECHA {f} DEFECTOS "
        "ENCONTRADOS NINGUNO REPARACIONES RECOMENDADAS NINGUNA VALIDEZ HASTA LA "
        "PROXIMA REVISION TECNICO {emp}",
    ]
    return rng.choice(variantes).format(
        n=rng.randint(1000, 99999), f=_fake_fecha(rng), emp=rng.choice(EMPRESAS),
    )


def _tpl_dni_comprador(rng):
    variantes = [
        "DOCUMENTO NACIONAL DE IDENTIDAD ESPAÑA NUMERO {dni} APELLIDOS {ap1} {ap2} "
        "NOMBRE {nom} NACIONALIDAD ESPAÑOLA FECHA DE NACIMIENTO {f} DOMICILIO EN "
        "{ciudad} VALIDEZ HASTA {f2} MINISTERIO DEL INTERIOR",
        "DNI ELECTRONICO 4.0 CHIP DE INTERFAZ DUAL CODIGO QR TINTA UV MICROTEXTOS "
        "TITULAR {nom} {ap1} NUMERO DE SOPORTE {n} FOTOCOPIA APORTADA POR LA PARTE "
        "COMPRADORA PARA EL EXPEDIENTE DE COMPRAVENTA",
        "NIE NUMERO DE IDENTIFICACION DE EXTRANJERO TARJETA DE IDENTIDAD {ap1} {ap2} "
        "{nom} FECHA DE CADUCIDAD {f2} DOCUMENTO APORTADO COMO IDENTIFICACION DEL "
        "COMPRADOR EN LA OPERACION",
        "FOTOCOPIA DOCUMENTO IDENTIFICATIVO PARA EXPEDIENTE DE COMPRAVENTA {nom} "
        "{ap1} {ap2} COMPROBACION DE IDENTIDAD PREVIA A LA FIRMA DEL CONTRATO COPIA "
        "SIMPLE ADJUNTA AL EXPEDIENTE INTERNO NUMERO {n}",
        "DOCUMENTO DE IDENTIDAD DIGITALIZADO PARA ARCHIVO ESCANEO DEL DOCUMENTO DE "
        "{nom} {ap1} REFERENCIA INTERNA DEL EXPEDIENTE DE VENTA {n} CUSTODIA "
        "CONFORME A LA NORMATIVA DE PROTECCION DE DATOS",
    ]
    return rng.choice(variantes).format(
        dni=_fake_dni(rng), ap1=rng.choice(APELLIDOS), ap2=rng.choice(APELLIDOS),
        nom=rng.choice(NOMBRES), f=_fake_fecha(rng), f2=_fake_fecha(rng),
        ciudad=rng.choice(PROVINCIAS_CIUDADES),
        n=rng.randint(10000000, 99999999),
    )


def _tpl_excedencia(rng):
    variantes = [
        "SOLICITUD DE EXCEDENCIA VOLUNTARIA ARTICULO 46 ESTATUTO DE LOS "
        "TRABAJADORES TRABAJADOR {nom} {ap1} ANTIGÜEDAD SUPERIOR A UN AÑO DURACION "
        "SOLICITADA DESDE {f} HASTA {f2} DERECHO PREFERENTE AL REINGRESO FIRMA DEL "
        "TRABAJADOR Y DE RECURSOS HUMANOS",
        "COMUNICACION DE CONCESION DE EXCEDENCIA VOLUNTARIA A {nom} {ap1} {ap2} "
        "PERIODO CONCEDIDO {f} A {f2} DENTRO DEL LIMITE LEGAL DE CUATRO MESES A "
        "CINCO AÑOS EL TIEMPO NO COMPUTA COMO ANTIGÜEDAD DEPARTAMENTO DE PERSONAL",
        "SOLICITUD DE REINGRESO TRAS EXCEDENCIA VOLUNTARIA DE {nom} {ap1} FECHA "
        "PREVISTA DE INCORPORACION {f2} DERECHO PREFERENTE A VACANTE DE IGUAL O "
        "SIMILAR CATEGORIA DEPARTAMENTO DE RECURSOS HUMANOS",
        "SOLICITUD DE EXCEDENCIA POR CUIDADO DE HIJOS {nom} {ap1} {ap2} FECHA DE "
        "NACIMIENTO O ADOPCION {f} DURACION MAXIMA TRES AÑOS SITUACION ASIMILADA AL "
        "ALTA A EFECTOS DE SEGURIDAD SOCIAL REINCORPORACION PREVISTA {f2}",
        "COMUNICACION DE EXCEDENCIA FORZOSA POR CARGO PUBLICO {nom} {ap1} "
        "DESIGNACION QUE IMPOSIBILITA LA ASISTENCIA AL TRABAJO CONSERVACION DEL "
        "PUESTO Y COMPUTO DE ANTIGÜEDAD FECHA {f}",
    ]
    return rng.choice(variantes).format(
        nom=rng.choice(NOMBRES), ap1=rng.choice(APELLIDOS),
        ap2=rng.choice(APELLIDOS), f=_fake_fecha(rng), f2=_fake_fecha(rng),
    )


def _tpl_gastos_tarjeta_combustible(rng):
    variantes = [
        "EXTRACTO DE MOVIMIENTOS TARJETA DE COMBUSTIBLE NUMERO {n} VEHICULO "
        "ASOCIADO {mat} FECHA {f} ESTACION DE SERVICIO LITROS REPOSTADOS IMPORTE "
        "{imp} EUROS KILOMETRAJE DECLARADO EMISORA DE LA TARJETA {emp}",
        "LIQUIDACION MENSUAL TARJETA FLOTA NUMERO {n} VEHICULO {mat} DETALLE DE "
        "REPOSTAJES DEL PERIODO IMPORTE TOTAL {imp} EUROS CONTROL DE CONSUMO POR "
        "VEHICULO DEPARTAMENTO DE FLOTA {emp}",
        "AUTORIZACION DE CARGO TARJETA DE FLOTA VEHICULO {mat} LIMITE DE GASTO "
        "MENSUAL {imp} EUROS PRODUCTO AUTORIZADO GASOIL PROFESIONAL FECHA {f} "
        "DEPARTAMENTO DE ADMINISTRACION DE FLOTA",
        "TICKET DE REPOSTAJE ESTACION DE SERVICIO MATRICULA {mat} LITROS IMPORTE "
        "TOTAL {imp} EUROS METODO DE PAGO TARJETA DE FLOTA FECHA {f} CODIGO DE "
        "AUTORIZACION DE LA OPERACION",
        "FACTURA DE CONSUMO TARJETA DE CARBURANTE FLOTA PERIODO DE FACTURACION "
        "VEHICULOS INCLUIDOS CONSUMO TOTAL IMPORTE {imp} EUROS EMISORA {emp} "
        "VEHICULO {mat} FECHA {f}",
    ]
    return rng.choice(variantes).format(
        n=rng.randint(1000, 999999), mat=_fake_matricula(rng),
        f=_fake_fecha(rng), imp=_fake_importe(rng, 20, 400),
        emp=rng.choice(EMPRESAS),
    )


def _tpl_justificante_transferencia(rng):
    variantes = [
        "JUSTIFICANTE DE TRANSFERENCIA BANCARIA FECHA {f} CUENTA DE ORIGEN {iban1} "
        "CUENTA DESTINO {iban2} IMPORTE {imp} EUROS CONCEPTO PAGO A {emp} REFERENCIA "
        "UNICA SEPA ESTADO REALIZADA",
        "COMPROBANTE DE TRANSFERENCIA INMEDIATA REFERENCIA {n} FECHA Y HORA {f} "
        "ORDENANTE {emp} BENEFICIARIO {emp2} IMPORTE {imp} EUROS COMISION APLICADA "
        "CERO EUROS ESTADO EJECUTADA",
        "JUSTIFICANTE DE PAGO A PROVEEDOR MEDIANTE TRANSFERENCIA PROVEEDOR "
        "BENEFICIARIO {emp} NUMERO DE FACTURA ASOCIADA {n} IMPORTE ABONADO {imp} "
        "EUROS FECHA {f} REFERENCIA BANCARIA",
        "RESGUARDO DE ORDEN DE PAGO BANCARIO REFERENCIA UNICA SEPA {n} FECHA VALOR "
        "{f} TITULAR DE LA CUENTA DE CARGO {emp} ENTIDAD DESTINATARIA {emp2} "
        "IMPORTE {imp} EUROS",
        "NOTIFICACION DE TRANSFERENCIA REALIZADA CODIGO DE OPERACION {n} FECHA {f} "
        "CUENTA DE ORIGEN {iban1} CUENTA DE DESTINO {iban2} IMPORTE {imp} EUROS "
        "ESTADO COMPLETADA",
    ]
    return rng.choice(variantes).format(
        f=_fake_fecha(rng), iban1=_fake_iban(rng), iban2=_fake_iban(rng),
        imp=_fake_importe(rng, 50, 30000), emp=rng.choice(EMPRESAS),
        emp2=rng.choice(EMPRESAS), n=rng.randint(100000, 9999999),
    )


def _tpl_recibo_senal_compra(rng):
    variantes = [
        "RECIBO DE SEÑAL O ANTICIPO POR COMPRA DE VEHICULO CANTIDAD ENTREGADA {imp} "
        "EUROS VEHICULO MATRICULA {mat} FECHA LIMITE PARA FORMALIZAR LA COMPRA {f} "
        "FIRMA DEL COMPRADOR {nom} {ap1} Y DEL VENDEDOR",
        "RECIBO DE ARRAS PENITENCIALES COMPRA DE MAQUINA CANTIDAD ENTREGADA COMO "
        "SEÑAL {imp} EUROS ARTICULO 1454 DEL CODIGO CIVIL PLAZO PARA CONTRATO "
        "DEFINITIVO {f} COMPRADOR {nom} {ap1} {ap2}",
        "RECIBO PROVISIONAL DE ENTREGA A CUENTA NUMERO {n} FECHA {f} FORMA DE PAGO "
        "TRANSFERENCIA SALDO PENDIENTE HASTA LA ENTREGA TOTAL DEL VEHICULO "
        "MATRICULA {mat} COMPRADOR {nom} {ap1}",
        "RECIBI CANTIDAD EN CONCEPTO DE RESERVA {imp} EUROS VEHICULO OBJETO DE LA "
        "RESERVA MATRICULA {mat} PLAZO DE RESERVA DESCUENTO DEL PRECIO FINAL "
        "COMPRADOR {nom} {ap1} {ap2} FECHA {f}",
        "JUSTIFICANTE DE PAGA Y SEÑAL VEHICULO USADO VENDEDOR {emp} COMPRADOR {nom} "
        "{ap1} IMPORTE Y FORMA DE ENTREGA {imp} EUROS MATRICULA {mat} FECHA ACORDADA "
        "PARA LA FIRMA {f}",
    ]
    return rng.choice(variantes).format(
        imp=_fake_importe(rng, 300, 8000), mat=_fake_matricula(rng),
        f=_fake_fecha(rng), nom=rng.choice(NOMBRES), ap1=rng.choice(APELLIDOS),
        ap2=rng.choice(APELLIDOS), n=rng.randint(1000, 99999),
        emp=rng.choice(EMPRESAS),
    )


def _tpl_pedido_compra(rng):
    variantes = [
        "PEDIDO DE COMPRA NUMERO {n} FECHA {f} PROVEEDOR {emp} DIRECCION DE ENVIO "
        "EN {ciudad} LINEAS DE PEDIDO DESCRIPCION CANTIDAD PRECIO UNITARIO IMPORTE "
        "CONDICIONES DE PAGO TRANSFERENCIA A 30 DIAS FECHA DE ENTREGA PREVISTA {f2} "
        "FIRMA DEL RESPONSABLE DE COMPRAS",
        "ORDEN DE COMPRA NUMERO {n} EMITIDA A {emp} REFERENCIA INTERNA {p} "
        "ARTICULOS SOLICITADOS CANTIDAD PRECIO UNITARIO TOTAL SUBTOTAL IVA IMPORTE "
        "TOTAL CONDICIONES DE ENVIO EN {ciudad} PLAZO DE ENTREGA {f2}",
        "SOLICITUD DE PEDIDO A PROVEEDOR {emp} NUMERO DE PEDIDO {n} FECHA {f} "
        "MATERIAL O SERVICIO SOLICITADO CANTIDAD PRECIO ACORDADO CONDICIONES DE "
        "PAGO FORMA DE ENTREGA EN {ciudad} AUTORIZADO POR EL RESPONSABLE DE "
        "COMPRAS",
        "PEDIDO FIRMADO NUMERO {n} PROVEEDOR {emp} FECHA DE EMISION {f} DETALLE DE "
        "ARTICULOS CANTIDAD PRECIO UNITARIO IMPORTE TOTAL FORMA DE PAGO "
        "TRANSFERENCIA BANCARIA ENTREGA PREVISTA EN {ciudad} EL {f2}",
        "CONFIRMACION DE PEDIDO DE COMPRA REFERENCIA {n} CLIENTE GRUAS ADOLFO "
        "ALVAREZ PROVEEDOR {emp} LINEAS DE ARTICULO CANTIDAD PRECIO UNITARIO "
        "IMPORTE CONDICIONES DE ENTREGA PLAZO ESTIMADO {f2} OBSERVACIONES "
        "ESPECIALES NINGUNA",
    ]
    return rng.choice(variantes).format(
        n=rng.randint(1000, 99999), f=_fake_fecha(rng), f2=_fake_fecha(rng),
        emp=rng.choice(EMPRESAS), ciudad=rng.choice(PROVINCIAS_CIUDADES),
        p=rng.randint(1000, 99999),
    )


GENERATORS = {
    "ALBARAN_ENTREGA": _tpl_albaran,
    "CERT_ACCESORIO_ELEVACION": _tpl_cert_accesorio_elevacion,
    "CERT_REVISION": _tpl_cert_revision,
    "DNI_COMPRADOR": _tpl_dni_comprador,
    "EXCEDENCIA": _tpl_excedencia,
    "GASTOS_TARJETA_COMBUSTIBLE": _tpl_gastos_tarjeta_combustible,
    "JUSTIFICANTE_TRANSFERENCIA": _tpl_justificante_transferencia,
    "RECIBO_SENAL_COMPRA": _tpl_recibo_senal_compra,
    # Añadido S56: PEDIDO_COMPRA -- hueco real confirmado en S56 (11
    # documentos reales, 0 backlog vivo que la heuristica de nombre
    # pudiera resolver hoy tras descartar duplicados por hash ya
    # enviados a papelera). Mismo caso que los 8 tipos originales de
    # S55: nunca tuvo aumentacion, no colisiona con ningun tipo vecino
    # confirmado (a diferencia de FACTURA_TERCEROS, que S55 dejo fuera
    # a proposito por su solape real con FACTURA_COMPRA/RECIBO_LEASING
    # -- ese criterio sigue vigente, pendiente de confirmacion expresa
    # de Miguel Angel si se quiere anular para este tipo).
    "PEDIDO_COMPRA": _tpl_pedido_compra,
    # S55, segunda pasada: CAMBIO_TITULARIDAD, PRESTAMO, OCA, PROFORMA,
    # SEG_SOCIAL, CUADRO_AMORTIZACION, CONTRATO_COMPRAVENTA, DOC_VENTA
    # quedan FUERA deliberadamente -- esos 8 ya tenian documentos reales
    # y su debilidad era de confusion/pocos datos de prueba, no ausencia
    # total; inundarlos de sintetico solo tapaba el problema real y
    # empeoro tipos que ya iban bien (ver anexo H30, incidente real S55).
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-type", type=int, default=60)
    parser.add_argument("--output", default="synthetic_augmented.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    seen = set()
    total = 0
    with open(args.output, "w", encoding="utf-8") as out:
        for tipo, gen in GENERATORS.items():
            n_written = 0
            intentos = 0
            while n_written < args.per_type and intentos < args.per_type * 5:
                intentos += 1
                texto = gen(rng)
                key = (tipo, texto)
                if key in seen:
                    continue
                seen.add(key)
                out.write(json.dumps({
                    "tipo": tipo,
                    "parent_path": "SYNTHETIC_GENERATED",
                    "name": "synthetic_%s_%04d.txt" % (tipo, n_written),
                    "texto": texto,
                }, ensure_ascii=False) + "\n")
                n_written += 1
                total += 1
            print("%s: %d ejemplos generados" % (tipo, n_written))
    print("\nTOTAL: %d filas escritas en %s" % (total, args.output))


if __name__ == "__main__":
    main()
