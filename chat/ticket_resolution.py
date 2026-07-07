# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/ticket_resolution.py
"""
BreakdownTicket resolution for spare-parts anchoring (H10 Paso 4-bis).

Movido aquí desde chat/services.py el 2026-07-07 -- ese archivo tiene,
desde antes de esta sesión, un import roto a nivel de módulo
(`from chat.models import ChatRoom, ChatMessage`, línea 60) porque
ambos modelos se eliminaron en H17 (ver docstring de chat/models.py:
"H17 — Paso 1: ChatRoom, ChatMessage and BreakdownConversationTurn
removed"). chat/services.py sigue usando ChatRoom/ChatMessage
extensamente en dispatch_inbound_message() y funciones relacionadas
-- código huérfano, muy probablemente sin ejecutarse en producción
desde H17 (WhatsApp parece enrutar por otro camino ahora, ver
conversation_log en BreakdownTicket) -- pero nadie lo había vuelto a
IMPORTAR de verdad hasta que este código (get_or_create_ticket_for_machine)
se llamó por primera vez desde workorder_spare_parts, lo que ejecuta
todo el módulo de arriba abajo y dispara el ImportError.

Corrección elegida: sacar esta sección entera (sin cambios de lógica)
a un módulo propio, en vez de arreglar chat/services.py -- ese archivo
necesita una revisión propia y más profunda del despachador de
WhatsApp, fuera de alcance de este fix puntual. Señalado a Miguel
Ángel para decidir aparte qué hacer con chat/services.py.

Diseño cerrado en S006 -- ver ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md,
sección "Paso 4-bis". Implementa los puntos 1 y 2 de los 12 del
diseño: resolución de ticket por centro de gasto (máquina) y el mutex
get_or_create con select_for_update(). Revisado en S007 (PAUSED cuenta
como candidato abierto, confirmación obligatoria con 1+ candidatos).

---

Moved here from chat/services.py on 2026-07-07 -- that file has had,
since before this session, a broken module-level import
(`from chat.models import ChatRoom, ChatMessage`, line 60) because
both models were removed in H17 (see chat/models.py docstring: "H17 —
Paso 1: ChatRoom, ChatMessage and BreakdownConversationTurn removed").
chat/services.py still uses ChatRoom/ChatMessage extensively in
dispatch_inbound_message() and related functions -- orphaned code,
very likely not actually executed in production since H17 (WhatsApp
seems to route through a different path now, see conversation_log on
BreakdownTicket) -- but nobody had actually IMPORTED it again until
this code (get_or_create_ticket_for_machine) was called for the first
time from workorder_spare_parts, which executes the whole module
top-to-bottom and triggers the ImportError.

Fix chosen: pull this whole section out (no logic changes) into its
own module, instead of fixing chat/services.py -- that file needs its
own, deeper review of the WhatsApp dispatcher, out of scope for this
point fix. Flagged to Miguel Ángel to decide separately what to do
with chat/services.py.

Design closed in S006 -- see ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md,
"Paso 4-bis" section. Implements points 1 and 2 of the 12-point
design: cost-centre (machine) ticket resolution and the
select_for_update() get_or_create mutex. Revised in S007 (PAUSED
counts as an open candidate, confirmation mandatory with 1+
candidates).
"""
import datetime
import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ivr_config.models import Contact

logger = logging.getLogger(__name__)


REOPEN_WINDOW_HOURS = 72


@dataclass(frozen=True)
class TicketResolution:
    """
    Immutable, read-only result of evaluating the breakdown-ticket-per-
    machine resolution rules (Paso 4-bis, punto 1, revisado en S007 a
    petición de Miguel Ángel) for a given fleet.MachineAsset. Never
    creates, attaches, reopens or modifies anything — used by the
    caller (work-order form view or confirm_delivery_note()) to decide
    what to tell the mechanic before calling
    get_or_create_ticket_for_machine().

    action:
      'CREATE'  — no OPEN/IN_PROGRESS/PAUSED ticket for this machine,
                  and nothing closed within REOPEN_WINDOW_HOURS. No
                  choice possible — the caller must simply NOTIFY the
                  mechanic a new ticket will be generated (no question,
                  per Miguel Ángel: "no hay elección cuando no haya").
      'ASK_REOPEN' — no OPEN/IN_PROGRESS/PAUSED ticket, but `ticket`
                  was closed within REOPEN_WINDOW_HOURS. Caller must
                  ask ("¿es la misma avería?") before calling
                  get_or_create_ticket_for_machine(reopen=True/False).
      'CHOOSE'  — one or more OPEN/IN_PROGRESS/PAUSED tickets exist
                  for this machine (`candidates` holds them, length
                  1+). Revised behaviour (S007): even with a single
                  candidate there is no silent auto-attach anymore —
                  the caller must always ask the mechanic to confirm
                  ("¿esta tarea es del ticket [X]?") with an explicit
                  "es una avería nueva" option alongside the
                  candidate(s), before calling
                  get_or_create_ticket_for_machine(chosen_ticket_pk=...)
                  or (..., create_new=True).

    ---

    Resultado inmutable y de solo lectura de evaluar las reglas de
    resolución de ticket de avería por máquina (Paso 4-bis, punto 1,
    revisado en S007 a petición de Miguel Ángel) para un
    fleet.MachineAsset dado. Nunca crea, engancha, reabre ni modifica
    nada — lo usa quien llama (vista de formulario de parte o
    confirm_delivery_note()) para decidir qué decirle al mecánico
    antes de llamar a get_or_create_ticket_for_machine().

    action:
      'CREATE'  — no hay ningún ticket OPEN/IN_PROGRESS/PAUSED para
                  esta máquina, ni nada cerrado dentro de
                  REOPEN_WINDOW_HOURS. Sin elección posible — el
                  llamante solo debe AVISAR al mecánico de que se va a
                  generar un ticket nuevo (sin pregunta, según Miguel
                  Ángel: "no hay elección cuando no haya").
      'ASK_REOPEN' — no hay ticket OPEN/IN_PROGRESS/PAUSED, pero
                  `ticket` se cerró dentro de REOPEN_WINDOW_HOURS. El
                  llamante debe preguntar ("¿es la misma avería?")
                  antes de llamar a
                  get_or_create_ticket_for_machine(reopen=True/False).
      'CHOOSE'  — hay uno o más tickets OPEN/IN_PROGRESS/PAUSED para
                  esta máquina (`candidates` los contiene, longitud
                  1+). Comportamiento revisado (S007): incluso con un
                  único candidato ya no hay enganche silencioso — el
                  llamante siempre debe preguntar al mecánico
                  ("¿esta tarea es del ticket [X]?") con una opción
                  explícita "es una avería nueva" junto al/los
                  candidato(s), antes de llamar a
                  get_or_create_ticket_for_machine(chosen_ticket_pk=...)
                  o (..., create_new=True).
    """

    action: str
    ticket: Optional[object] = None
    candidates: tuple = ()


def resolve_ticket_for_machine(machine) -> "TicketResolution":
    """
    Read-only evaluation of Paso 4-bis punto 1 (revisado en S007) for
    `machine` (fleet.MachineAsset). Never locks, never writes — safe
    to call as many times as needed while rendering a form or a
    confirmation screen. The definitive, race-free evaluation happens
    again inside get_or_create_ticket_for_machine(), under the mutex.

    PAUSED counts as an open candidate (S007, confirmado por Miguel
    Ángel): un ticket se pausa cuando el mecánico se reasigna a una
    avería de otra máquina con más prioridad, y sigue siendo un
    candidato real a retomar en esta máquina — no un estado terminal
    como CLOSED.
    ---
    Evaluación de solo lectura del punto 1 de Paso 4-bis (revisado en
    S007) para `machine` (fleet.MachineAsset). Nunca bloquea, nunca
    escribe — se puede llamar tantas veces como haga falta al
    renderizar un formulario o una pantalla de confirmación. La
    evaluación definitiva y libre de condiciones de carrera vuelve a
    ocurrir dentro de get_or_create_ticket_for_machine(), bajo el
    mutex.

    PAUSED cuenta como candidato abierto (S007, confirmado por Miguel
    Ángel): un ticket se pausa cuando el mecánico se reasigna a una
    avería de otra máquina con más prioridad, y sigue siendo un
    candidato real a retomar en esta máquina — no es un estado
    terminal como CLOSED.
    """
    from chat.models import BreakdownTicket

    open_candidates = list(
        BreakdownTicket.objects.filter(
            machine=machine,
            status__in=[
                BreakdownTicket.STATUS_OPEN,
                BreakdownTicket.STATUS_IN_PROGRESS,
                BreakdownTicket.STATUS_PAUSED,
            ],
        ).order_by("-created_at")
    )

    if open_candidates:
        return TicketResolution(action="CHOOSE", candidates=tuple(open_candidates))

    # 0 candidatos abiertos/pausados -- mirar cerrados dentro de la
    # ventana de reapertura. Si hubiera más de uno cerrado dentro de la
    # ventana se ofrece el más reciente -- el diseño de S006 no
    # contempla varios candidatos cerrados simultáneos; asunción
    # declarada, no bloqueante, a confirmar con Miguel Ángel si llega a
    # darse en la práctica.
    # ---
    # 0 open/paused candidates -- look at those closed within the
    # reopening window. If more than one were closed within the
    # window, the most recent is offered -- the S006 design does not
    # contemplate several simultaneous closed candidates; declared,
    # non-blocking assumption, to confirm with Miguel Ángel if it
    # happens in practice.
    cutoff = timezone.now() - datetime.timedelta(hours=REOPEN_WINDOW_HOURS)
    recently_closed = (
        BreakdownTicket.objects.filter(
            machine=machine,
            status=BreakdownTicket.STATUS_CLOSED,
            resolved_at__gte=cutoff,
        )
        .order_by("-resolved_at")
        .first()
    )
    if recently_closed is not None:
        return TicketResolution(action="ASK_REOPEN", ticket=recently_closed)

    return TicketResolution(action="CREATE")


def _resolve_ticket_contact(company_user):
    """
    Resolves (or lazily creates) the Contact used to satisfy the
    mandatory BreakdownTicket.contact FK when a ticket is pregenerated
    without a real external reporter (Paso 4-bis, bloque CREATE).

    Resolution order:
      1. Any Contact already linked to this company_user (its
         `company_user` FK) — deliberately NOT filtered by
         `is_internal`, because CompanyUserCreateView
         (panel/views_auth.py) sets `is_internal=is_ivr_active` on
         creation, so a linked Contact may exist with
         `is_internal=False` and would be missed by the
         is_internal=True filter used elsewhere (whatsapp/tasks.py,
         chat/views.py) for a different purpose (WhatsApp-capable
         contacts). Here we only need a valid Contact belonging to
         this company_user, whatever its is_internal flag.
      2. If none exists at all — CompanyUserCreateView only
         links/creates a Contact when a phone_number or a section was
         given at creation time (panel/views_auth.py:214-261), so some
         CompanyUsers may have none — create one on the fly following
         the exact same no-phone pattern already used there
         (phone_number='', is_internal=True, company_user=company_user).

    Never raises for a missing Contact — self-heals instead, so
    get_or_create_ticket_for_machine() never fails on this account.
    ---

    Resuelve (o crea de forma perezosa) el Contact usado para
    satisfacer el FK obligatorio BreakdownTicket.contact cuando se
    pregenera un ticket sin un reportante externo real (Paso 4-bis,
    bloque CREATE).

    Orden de resolución:
      1. Cualquier Contact ya vinculado a este company_user (su FK
         `company_user`) — deliberadamente SIN filtrar por
         `is_internal`, porque CompanyUserCreateView
         (panel/views_auth.py) fija `is_internal=is_ivr_active` al
         crear, así que puede existir un Contact vinculado con
         `is_internal=False` que el filtro is_internal=True usado en
         otros sitios (whatsapp/tasks.py, chat/views.py) para otro
         propósito (contactos con capacidad de WhatsApp) no
         encontraría. Aquí solo hace falta un Contact válido de este
         company_user, sea cual sea su is_internal.
      2. Si no existe ninguno — CompanyUserCreateView solo
         vincula/crea un Contact cuando se dio phone_number o sección
         al crear el usuario (panel/views_auth.py:214-261), así que
         algunos CompanyUser pueden no tener ninguno — se crea uno al
         vuelo siguiendo el mismo patrón sin teléfono ya usado allí
         (phone_number='', is_internal=True, company_user=company_user).

    Nunca lanza excepción por falta de Contact — se autorrepara, para
    que get_or_create_ticket_for_machine() nunca falle por este motivo.
    """
    contact = Contact.objects.filter(
        company=company_user.company,
        company_user=company_user,
    ).first()
    if contact is not None:
        return contact

    display_name = (
        company_user.user.get_full_name().strip()
        or company_user.user.username
    )
    contact = Contact.objects.create(
        company=company_user.company,
        phone_number="",
        name=display_name,
        is_internal=True,
        company_user=company_user,
    )
    logger.info(
        "# [H10-BIS] Contact interno pk=%s creado sobre la marcha para "
        "company_user pk=%s (no tenía ninguno vinculado todavía).",
        contact.pk, company_user.pk,
    )
    return contact


def get_or_create_ticket_for_machine(
    machine,
    company_user,
    reopen: Optional[bool] = None,
    chosen_ticket_pk: Optional[int] = None,
    create_new: bool = False,
):
    """
    Atomic, mutex-protected resolution of Paso 4-bis puntos 1-2
    (revisado en S007). Must be called from within the same DB
    transaction as the task save that needs the ticket (punto 11 del
    diseño — transacción única por tarea); Django reuses the caller's
    transaction if one is already open instead of nesting a new one.

    Re-evaluates the resolution rules AFTER acquiring the mutex (a
    select_for_update() lock on the MachineAsset row), never before —
    the read-only preview from resolve_ticket_for_machine() can be
    stale by the time the mechanic answers a question, so it is
    recomputed here to close the race between two concurrent requests
    for the same machine (punto 2 del diseño: cubre tanto la vía parte
    como la vía albarán, y el caso de "ayuda" entre operarios).

    Parameters:
      machine          -- fleet.MachineAsset, the cost centre.
      company_user     -- ivr_config.CompanyUser performing the action.
                           Used to resolve (or lazily create, via
                           _resolve_ticket_contact()) the mandatory
                           BreakdownTicket.contact field when a new
                           ticket must be created.
      reopen           -- required (True/False) only when the
                           re-evaluated state is ASK_REOPEN. Ignored
                           otherwise. False means "no es la misma
                           avería" -- falls through to CREATE, same as
                           create_new=True would for CHOOSE.
      chosen_ticket_pk -- when the re-evaluated state is CHOOSE, pass
                          this to attach to that specific candidate
                          (mechanic confirmed "sí, es este ticket").
                          Mutually exclusive with create_new.
      create_new       -- when the re-evaluated state is CHOOSE, pass
                          True to force a brand new ticket even though
                          candidate(s) exist (mechanic confirmed "es
                          una avería nueva"). Mutually exclusive with
                          chosen_ticket_pk.

    Returns the resolved chat.models.BreakdownTicket (existing,
    reopened, or newly created). Never fails for lack of a Contact —
    _resolve_ticket_contact() self-heals by creating one if needed.

    Raises ValueError if the caller's answer doesn't match what the
    re-evaluation actually needs (e.g. state is CHOOSE but neither
    chosen_ticket_pk nor create_new was given, or both were) — this is
    treated as a caller bug (stale UI state), never silently guessed.

    ---

    Resolución atómica y protegida por mutex de los puntos 1-2 del
    diseño de Paso 4-bis (revisado en S007). Debe llamarse dentro de
    la misma transacción de BD que el guardado de la tarea que
    necesita el ticket (punto 11 del diseño — transacción única por
    tarea); Django reutiliza la transacción de quien llama si ya hay
    una abierta, en vez de anidar una nueva.

    Reevalúa las reglas DESPUÉS de adquirir el mutex (bloqueo
    select_for_update() sobre la fila de MachineAsset), nunca antes —
    la vista previa de solo lectura de resolve_ticket_for_machine()
    puede haber quedado obsoleta para cuando el mecánico responde una
    pregunta, así que se recalcula aquí para cerrar la carrera entre
    dos peticiones concurrentes sobre la misma máquina (punto 2 del
    diseño: cubre tanto la vía parte como la vía albarán, y el caso de
    "ayuda" entre operarios).
    """
    from chat.models import BreakdownTicket
    from fleet.models import MachineAsset

    with transaction.atomic():
        # Mutex -- punto 2 del diseño. select_for_update() sobre la
        # fila de MachineAsset cubre tanto la vía parte como la vía
        # albarán, y el caso de "ayuda" entre operarios sobre la misma
        # máquina, sin condiciones de carrera.
        MachineAsset.objects.select_for_update().get(pk=machine.pk)

        resolution = resolve_ticket_for_machine(machine)

        if resolution.action == "CHOOSE":
            if bool(chosen_ticket_pk) == bool(create_new):
                raise ValueError(
                    "get_or_create_ticket_for_machine(): hay %d ticket(s) "
                    "abierto(s)/pausado(s) para la máquina pk=%s -- el "
                    "llamante debe pasar exactamente uno de "
                    "chosen_ticket_pk o create_new=True (nunca ambos, "
                    "nunca ninguno) tras preguntar al mecánico." % (
                        len(resolution.candidates), machine.pk,
                    )
                )
            if create_new:
                pass  # cae al bloque CREATE de abajo, igual que ASK_REOPEN con reopen=False.
            else:
                chosen = next(
                    (t for t in resolution.candidates if t.pk == chosen_ticket_pk),
                    None,
                )
                if chosen is None:
                    raise ValueError(
                        "get_or_create_ticket_for_machine(): chosen_ticket_pk=%s "
                        "no está entre los candidatos actuales (abiertos/"
                        "pausados) para la máquina pk=%s -- posible carrera "
                        "o estado de UI obsoleto." % (chosen_ticket_pk, machine.pk)
                    )
                return chosen

        elif resolution.action == "ASK_REOPEN":
            if reopen is None:
                raise ValueError(
                    "get_or_create_ticket_for_machine(): hay un ticket "
                    "cerrado hace menos de %sh para la máquina pk=%s y no "
                    "se indicó reopen -- el llamante debe preguntar al "
                    "mecánico antes de invocar esta función." % (
                        REOPEN_WINDOW_HOURS, machine.pk,
                    )
                )
            if reopen:
                ticket = resolution.ticket
                ticket.status = BreakdownTicket.STATUS_IN_PROGRESS
                ticket.resolved_at = None
                ticket.resolved_by = None
                ticket.save(update_fields=["status", "resolved_at", "resolved_by"])
                logger.info(
                    "# [H10-BIS] Ticket pk=%s reabierto para máquina pk=%s "
                    "(estaba cerrado hace menos de %sh).",
                    ticket.pk, machine.pk, REOPEN_WINDOW_HOURS,
                )
                return ticket
            # reopen=False -- el mecánico confirma que no es la misma
            # avería -- cae al bloque CREATE de abajo.

        # resolution.action == 'CREATE', o 'CHOOSE' con create_new=True,
        # o 'ASK_REOPEN' con reopen=False.
        contact = _resolve_ticket_contact(company_user)

        ticket = BreakdownTicket.objects.create(
            company=company_user.company,
            contact=contact,
            machine=machine,
            machine_raw=machine.code,
            origin=BreakdownTicket.ORIGIN_AUTO,
            status=BreakdownTicket.STATUS_OPEN,
        )
        logger.info(
            "# [H10-BIS] Ticket pk=%s pregenerado para máquina pk=%s "
            "(resolución: %s).",
            ticket.pk, machine.pk, resolution.action,
        )
        return ticket

