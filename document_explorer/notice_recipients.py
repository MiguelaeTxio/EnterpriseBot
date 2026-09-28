# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/notice_recipients.py
"""
H30 (S122). Which documentation supervisors receive each notice.

---

H30 (S122). Qué supervisores de documentación reciben cada aviso,
según el ámbito que cada uno define (`NoticeRecipientScope`). Miguel
Ángel: "los avisos deben de definirse a nivel global, pero también de
forma específica [...] vamos a centrar los avisos de forma
subjetiva".

Regla: un aviso llega a un supervisor si su sujeto cumple CUALQUIERA
de los criterios del dominio (personal: todo, empresa, grupo de
reparto o persona; centros de gasto: todo, familia, empresa o
máquina) y no está excluido por requisito ni por tipo de documento.
Sin ficha, o con la ficha vacía, no recibe nada. Solo cuentan los
usuarios activos con rol de supervisor de documentación.
"""
from dataclasses import dataclass, field

from document_explorer.document_notice_service import DOMAIN_PERSONAL

DOCS_SUPERVISOR_ROLE = "DOCS_SUPERVISOR"


@dataclass
class ScopeSnapshot:
    """
    One supervisor's scope, flattened to sets for fast matching.

    ---

    Ámbito de un supervisor ya aplanado a conjuntos, para comprobar
    miles de avisos sin más consultas.
    """

    company_user: object
    personal_all: bool = False
    personal_companies: set = field(default_factory=set)
    personal_person_ids: set = field(default_factory=set)
    machine_all: bool = False
    machine_families: set = field(default_factory=set)
    machine_companies: set = field(default_factory=set)
    machine_ids: set = field(default_factory=set)
    excluded_requirement_ids: set = field(default_factory=set)
    excluded_type_ids: set = field(default_factory=set)

    def covers(self, notice):
        """
        True if this notice falls inside the scope.

        ---

        True si el aviso entra en el ámbito de este supervisor.
        """
        if notice.requirement_id in self.excluded_requirement_ids:
            return False
        if notice.document_type_id in self.excluded_type_ids:
            return False
        if notice.domain == DOMAIN_PERSONAL:
            return (
                self.personal_all
                or notice.subject_company in self.personal_companies
                or notice.subject_id in self.personal_person_ids
            )
        return (
            self.machine_all
            or notice.subject_family in self.machine_families
            or notice.subject_company in self.machine_companies
            or notice.subject_id in self.machine_ids
        )


def docs_supervisors(company=None):
    """
    Active documentation supervisors, ordered by name.

    ---

    Supervisores de documentación activos, por nombre.
    """
    from ivr_config.models import CompanyUser

    queryset = CompanyUser.objects.filter(
        role=DOCS_SUPERVISOR_ROLE, is_active=True,
    ).select_related("user")
    if company is not None:
        queryset = queryset.filter(company=company)
    return list(
        queryset.order_by("user__first_name", "user__last_name"),
    )


def load_scopes(company=None):
    """
    ScopeSnapshot of every active documentation supervisor.

    ---

    Un ScopeSnapshot por supervisor de documentación activo (vacío si
    no tiene ficha). Los grupos de reparto se expanden aquí a sus
    personas, para que la comprobación sea solo de conjuntos.
    """
    from document_explorer.models import NoticeRecipientScope

    supervisors = docs_supervisors(company)
    scopes_by_user = {
        scope.company_user_id: scope
        for scope in NoticeRecipientScope.objects.filter(
            company_user__in=supervisors,
        ).prefetch_related(
            "personal_groups__members", "personal_persons", "machines",
            "excluded_requirements", "excluded_document_types",
        )
    }
    snapshots = []
    for company_user in supervisors:
        scope = scopes_by_user.get(company_user.pk)
        snapshot = ScopeSnapshot(company_user=company_user)
        if scope is not None:
            person_ids = {p.pk for p in scope.personal_persons.all()}
            for group in scope.personal_groups.all():
                person_ids |= {p.pk for p in group.members.all()}
            snapshot.personal_all = scope.personal_all
            snapshot.personal_companies = set(scope.personal_companies)
            snapshot.personal_person_ids = person_ids
            snapshot.machine_all = scope.machine_all
            snapshot.machine_families = set(scope.machine_families)
            snapshot.machine_companies = set(scope.machine_companies)
            snapshot.machine_ids = {m.pk for m in scope.machines.all()}
            snapshot.excluded_requirement_ids = {
                r.pk for r in scope.excluded_requirements.all()
            }
            snapshot.excluded_type_ids = {
                t.pk for t in scope.excluded_document_types.all()
            }
        snapshots.append(snapshot)
    return snapshots


def recipients_for(notice, scopes):
    """
    Supervisors (CompanyUser) whose scope covers this notice.

    ---

    Supervisores (CompanyUser) cuyo ámbito cubre el aviso. Lista vacía
    = "Sin destinatario".
    """
    return [
        snapshot.company_user for snapshot in scopes
        if snapshot.covers(notice)
    ]
