# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/import_paper_partes_cruces_s149.py
"""
Load the paper work orders of José Manuel Cruces («Coco»), 23-26/11/2026.

---

S149 (Miguel Ángel, 27/11): los partes en papel de Coco (José Manuel
Cruces Heredia, Plataformas), transcritos de las 8 fotos. Mismo cargador
que import_paper_partes_s149 (parte digital por día, comparado con sus
fichajes salvo visados y correcciones a mano) con lo que se acordó ese
día:

- Sin hueco de desayuno: "la media hora [...] se la vamos a poner a la
  tarea siguiente" (las tareas de las 10:30 empiezan a las 10:00).
- 23/11, marcado «+2H 1»: como Nicolás el 24/11 («+2 1c»), dieta y sin
  parar a comer (traslado a Tiro Pichón de 13:30 a 15:00; ese día fichó
  solo entrada y salida).
- La hoja de la tarde del 26/11 pone 26/10/2026: es el 26/11 (sigue a
  la de la mañana del 26/11, que acaba a las 13:30).
- Sin centro de gasto (4216LYS, Z204): a Taller elevación con el código
  en la resolución.

Además le pone el apodo «COCO» en su ficha si no lo tiene.
"""
from work_order_processor.management.commands import (
    import_paper_partes_s149 as base,
)

CRUCES = 49
T = base.TALLER
PARTES = [
    (CRUCES, "2026-11-23", [
        (T, "08:00", "09:00", "Entrega y recepción de Z105 y Z123", "",
         None),
        (T, "09:00", "13:30",
         "Cargar espiter y traslado a Parador de Gibralfaro", "", None),
        (T, "13:30", "15:00", "Traslado a Tiro Pichón", "", None),
        ("Z204", "15:00", "16:00", "Limpieza y comprobación", "", None),
        ("Z29", "16:00", "17:00", "Limpieza/comprobación", "", None),
        ("Z109", "17:00", "18:30", "Limpieza/comprobación", "", None),
    ], [], "Marcado «+2H 1»: dieta y sin parar a comer."),
    (CRUCES, "2026-11-24", [
        ("T20", "07:00", "08:30", "Traslado desde casa a Marenostrum", "",
         None),
        ("T10", "08:30", "10:00", "Limpieza/comprobación", "", 4825),
        ("T11", "10:00", "12:00", "Limpieza/comprobación", "", 6671),
        ("Z26", "12:00", "13:30", "Limpieza/comprobación", "", 1371),
        ("Z128", "15:00", "17:00", "Comprobación/cambiar joystick",
         "Cambiar bobina de traslación. Horas 2500", None),
        ("Z128", "17:00", "17:30", "Limpieza", "Horas 2500", None),
        ("Z59", "17:30", "18:00", "Limpieza/comprobación", "Horas 0537",
         None),
        (T, "18:00", "18:30", "Recoger taller", "", None),
    ], [], "Dos hojas. Marcado «+2H». Hueco 10:00-10:30 cerrado."),
    (CRUCES, "2026-11-25", [
        ("4216LYS", "08:00", "10:00", "Ayudar a Zafra", "", None),
        ("Z126", "10:00", "12:00", "Limpieza/comprobación", "Horas 193",
         None),
        ("Z79", "12:00", "13:30", "Comprobación/arreglar giro de canasta",
         "", 3272),
        ("Z52", "15:00", "16:00", "Limpieza/comprobación", "", None),
        (T, "16:00", "17:00", "Traslado a Leroy Merlin con Manolo", "",
         None),
        ("Z77", "17:00", "18:00", "Comprobación/apretar bornes", "", None),
        (T, "18:00", "18:30", "Recoger taller", "", None),
    ], [], "Dos hojas. Marcado «+1H». Hueco 10:00-10:30 cerrado."),
    (CRUCES, "2026-11-26", [
        ("Z123", "08:00", "10:00", "Limpieza/comprobación", "", None),
        (T, "10:00", "11:00", "Traslado a Torner", "", None),
        ("Z17", "11:00", "12:30",
         "Limpieza/comprobar/poner carcasa de los mandos", "", None),
        ("Z77", "12:30", "13:30", "Limpieza/empresillar cables", "", 1545),
        (T, "15:00", "17:00",
         "Ayudar a Carlos a cortar puertas del compresor del arenero", "",
         None),
        (T, "17:00", "18:00",
         "Montar soporte y filtro de gasoil a compresor del arenero", "",
         None),
        (T, "18:00", "18:30", "Recoger taller", "", None),
    ], [], "Dos hojas (la de la tarde pone 26/10/2026). Marcado «+1H». "
           "Hueco 10:00-10:30 cerrado."),
]


class Command(base.Command):
    help = ("Carga los partes en papel de José Manuel Cruces (Coco), "
            "23-26/11/2026.")

    PARTES = PARTES
    DIETS = {(CRUCES, "2026-11-23")}
    NO_CLOCK = set()
    NO_LUNCH = {(CRUCES, "2026-11-23")}

    def _run(self):
        from document_explorer.models import PersonIdentity

        person = PersonIdentity.objects.filter(pk=CRUCES).first()
        if person is None or "MANUEL" not in (person.given_name or "").upper():
            self._log("!! La persona %d no es José Manuel Cruces: no se "
                      "carga nada." % CRUCES)
            return
        if not (person.nickname or "").strip():
            person.nickname = "COCO"
            person.save(update_fields=["nickname"])
            self._log("Apodo puesto: COCO.")
        else:
            self._log("Apodo: ya tenía «%s»." % person.nickname)
        super()._run()
