# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/apply_manual_machine_resolutions.py
"""
H30 (S119), roadmap item 1 -- real closure: apply the manual
resolution of the 43 documents no rule could date.
---
H30 (S119), punto 1 -- cierre real. Tras las reglas (punto 1 original)
y la lectura completa (`read_full_machine_undated`) quedaban 72, y
después 43 sin ninguna fecha. Esos 43 se han resuelto uno a uno,
viendo cada documento (`gcs_image`/`gcs_unrar` del relevo) y, en los
casos ambiguos, con la lectura de Miguel Ángel -- nunca por regla.

Esta lista es exhaustiva y está fijada en el propio código: no admite
`--ids`. Dos tablas:
- FECHAS: 29 documentos con fecha real (issue y/o expiry), por id.
- ACCIONES: 14 documentos con tipo incorrecto -- 12 pasan a un tipo
  nuevo (con fecha en 3 de ellos: la garantía cuenta desde la entrega
  o la factura de la máquina, no desde la fecha del formulario, que
  está en blanco) y 2 van a la papelera (borrador sin firmar
  duplicado; garantía del comprador anterior de una máquina de
  segunda mano, no nuestra).

DRY-RUN por defecto. Log propio (pantalla y archivo a la vez).
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog

# id: (issue_date, expiry_date, motivo)
FECHAS = {
    3918: (date(2011, 12, 14), None,
           "ultima inspeccion; mes del valedera tapado por el sello"),
    17266: (date(2010, 4, 16), date(2010, 10, 16), "visto"),
    10648: (date(2007, 8, 21), None, "Hauptuntersuchung aleman"),
    3847: (None, date(2014, 10, 29), "leido por Miguel Angel"),
    3880: (date(2012, 10, 29), date(2013, 10, 29),
           "tarjeta P14 anterior a la del id=3847"),
    4835: (date(2013, 6, 25), date(2014, 6, 25), "matricula 1532 DVF"),
    5074: (date(2012, 11, 13), date(2013, 11, 13),
           "hoja adicional, unica inspeccion, 7965DVL"),
    5233: (date(2011, 7, 18), date(2012, 7, 18), "leido por Miguel Angel"),
    5268: (date(2012, 7, 18), date(2013, 7, 18),
           "misma tarjeta 8965 FCK que id=5233, inspeccion siguiente"),
    5383: (date(2012, 8, 10), date(2013, 8, 10), "8992 FCK"),
    5655: (date(2013, 9, 11), date(2014, 3, 11),
           "4205 FLW; ultima de 9 inspecciones 2009-2013"),
    8876: (date(2013, 4, 2), date(2013, 10, 2),
           "8746 DPY; ultima tras dos desfavorables en 2012"),
    9599: (date(2011, 4, 7), date(2013, 4, 7), "E-6593-BDC"),
    9731: (date(2011, 11, 16), date(2012, 5, 16),
           "escaneo anterior de la misma tarjeta A50 que id=9713"),
    15167: (date(2013, 2, 8), date(2013, 8, 8),
            "6184 BBC; desfavorable y favorable el mismo dia"),
    9713: (date(2013, 11, 11), date(2014, 5, 11),
           "dia confirmado por Miguel Angel (semestral)"),
    15254: (date(2013, 7, 30), date(2014, 1, 30),
            "G03; tras desfavorable del 23/07/2013"),
    15276: (date(2012, 1, 16), date(2012, 7, 16),
            "G03 tarjeta anterior; escrito en vertical, patron semestral"),
    16184: (date(2013, 4, 22), date(2013, 10, 22),
            "G-06 R-0410-BBF; tras desfavorable del mismo dia"),
    15168: (date(2013, 8, 16), date(2014, 8, 16), "leido por Miguel Angel"),
    16334: (date(2013, 4, 11), date(2013, 10, 11), "R11"),
    16341: (date(2013, 10, 29), date(2014, 4, 29),
            "R11, escaneo posterior de la misma tarjeta que id=16334"),
    16450: (date(2012, 8, 28), date(2013, 2, 28),
            "MA-02305-R; tras desfavorable del 23/08/2012"),
    16402: (date(2012, 8, 7), date(2013, 2, 7), "leido por Miguel Angel"),
    11102: (date(2006, 4, 24), None,
            "autoliquidacion IVTM Malaga, Liebherr LTM1055-3-1, "
            "3er trimestre 2006, sello Unicaja 24/04/2006"),
    17275: (date(2007, 12, 18), date(2008, 12, 17),
            "recibo Seguros Mercurio R-8935-BBN, periodo 18/12/07 a "
            "17/12/08, cargo 24/12/2007"),
    10251: (date(2026, 1, 27), date(2027, 1, 27),
            "recibo AXA E9848BHG, periodo 20260127-20270127, cargo "
            "28/01/2026"),
    5312: (date(2009, 1, 13), None,
           "certificado COVEI instalacion/revision del limitador, "
           "IVECO 8965-FCK; rev. tacografo 04/11/2008"),
    8787: (date(2015, 1, 1), date(2016, 1, 1),
           "poliza Allianz 034038401 + recibo Unicaja de GRUALDI S.L. "
           "(empresa del grupo, GLA), periodo anual"),
}

# id: (accion, tipo_nuevo|None, issue_date|None, expiry_date|None, motivo)
ACCIONES = {
    14995: ("papelera", None, None, None,
            "Anexo III RD 1428/2003, normativa general, no es "
            "documento de la maquina"),
    4482: ("tipo", "CERTIFICADO_PODERES", date(2021, 3, 8), None,
           "autorizacion de representacion ITV Thader, firmada "
           "08/03/2021"),
    4483: ("papelera", None, None, None,
           "borrador sin firmar duplicado del id=4482"),
    6362: ("tipo", "LEASING", None, None,
           "poliza de leasing BBVA 0182-4100-0501-1762086, camion MAN"),
    18954: ("tipo", "LEASING", None, None,
            "poliza de leasing BBVA 0182-4100-0501-1762085, Mercedes "
            "Vito 7486LKF"),
    10955: ("tipo", "LEASING", date(2025, 7, 7), None,
            "volante de formalizacion leasing Cajamar "
            "3058/0746/63/1650075443, sello notario 07/07/2025"),
    13159: ("tipo", "CONDICIONES_GENERALES_SEGURO", None, None,
            "cuadernillo Generali Maquinaria, condiciones generales"),
    15783: ("tipo", "CONDICIONES_GENERALES_SEGURO", None, None,
            "condiciones generales Europ Assistance Libre Eleccion"),
    10946: ("tipo", "IMAGEN", None, None,
            "captura de la partida 12 de la poliza (Z-110, Z-111, JLG "
            "600AJ, 2 Hoeflon C6E)"),
    7542: ("fecha", None, date(2019, 8, 2), None,
           "inicio de garantia = fecha del contrato de leasing "
           "Santander 207173 (Genie GTH3007)"),
    13113: ("papelera", None, None, None,
            "garantia Socage del primer duenio (Alquiber Quality), "
            "maquina comprada usada a Garcicar, no es nuestra garantia"),
    13422: ("fecha", None, date(2024, 10, 10), None,
            "inicio de garantia = fecha del albaran de entrega "
            "Transmec De Bortoli (JLG X15J Plus)"),
    13535: ("fecha", None, date(2025, 10, 21), None,
            "inicio de garantia = fecha de la factura JLG 690832 "
            "(JLG 600AJ)"),
    7626: ("tipo", "FICHA_TECNICA", date(2020, 2, 21), None,
           "ficha tecnica UniCarriers T-11 E-2158-BHG, inspecciones "
           "tecnicas en blanco"),
}


class Command(BaseCommand):
    help = (
        "H30 (S119) -- punto 1, cierre real: aplica la resolucion "
        "manual (vista documento a documento) de los 43 caducables "
        "que ninguna regla pudo fechar. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._handle.write(message + "\n")
        self._handle.flush()
        print(message, flush=True)

    def handle(self, *args, **options):
        self._handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._handle.close()

    def _run(self, apply_changes):
        self._log(
            "PUNTO 1 -- CIERRE MANUAL -- MODO: %s -- %d fechas + %d "
            "acciones (%d documentos)" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)",
                len(FECHAS), len(ACCIONES), len(FECHAS) + len(ACCIONES),
            )
        )
        type_cache = {}
        missing_ids = []
        trashed = 0
        dated = 0
        retyped = 0

        def _resolve_type(code):
            if code not in type_cache:
                type_cache[code] = DocumentTypeCatalog.objects.get(
                    code=code,
                )
            return type_cache[code]

        for pk, (issue, expiry, motivo) in FECHAS.items():
            try:
                entry = DocumentIndexEntry.objects.get(pk=pk)
            except DocumentIndexEntry.DoesNotExist:
                missing_ids.append(pk)
                continue
            self._log("  id=%d FECHA issue=%s expiry=%s -- %s" % (
                pk, issue, expiry, motivo,
            ))
            if apply_changes:
                entry.issue_date = issue
                entry.expiry_date = expiry
                entry.save(update_fields=["issue_date", "expiry_date"])
            dated += 1

        for pk, (accion, code, issue, expiry, motivo) in ACCIONES.items():
            try:
                entry = DocumentIndexEntry.objects.get(pk=pk)
            except DocumentIndexEntry.DoesNotExist:
                missing_ids.append(pk)
                continue
            if accion == "papelera":
                self._log("  id=%d PAPELERA -- %s" % (pk, motivo))
                if apply_changes:
                    entry.deleted_at = timezone.now()
                    entry.save(update_fields=["deleted_at"])
                trashed += 1
                continue
            if accion == "tipo":
                document_type = _resolve_type(code)
                self._log(
                    "  id=%d TIPO -> %s issue=%s expiry=%s -- %s" % (
                        pk, code, issue, expiry, motivo,
                    )
                )
                if apply_changes:
                    entry.document_type = document_type
                    entry.issue_date = issue
                    entry.expiry_date = expiry
                    entry.save(update_fields=[
                        "document_type", "issue_date", "expiry_date",
                    ])
                retyped += 1
                continue
            # accion == "fecha": mismo tipo, solo la fecha de garantia.
            self._log("  id=%d FECHA (garantia) issue=%s -- %s" % (
                pk, issue, motivo,
            ))
            if apply_changes:
                entry.issue_date = issue
                entry.expiry_date = expiry
                entry.save(update_fields=["issue_date", "expiry_date"])
            dated += 1

        self._log("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log("    fechados: %d" % dated)
        self._log("    retipados: %d" % retyped)
        self._log("    papelera: %d" % trashed)
        if missing_ids:
            self._log(
                "    ATENCION -- ids no encontrados en BD: %s"
                % missing_ids
            )
