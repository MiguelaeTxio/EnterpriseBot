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
usuarios activos con rol de supervisor de documentación o de
administrador (S126, Miguel Ángel: el administrador configura los
avisos que quiere recibir y prueba el circuito de extremo a extremo
sin depender de un supervisor).
"""
import re
import unicodedata
from dataclasses import dataclass, field

from document_explorer.document_notice_service import DOMAIN_PERSONAL

DOCS_SUPERVISOR_ROLE = "DOCS_SUPERVISOR"
ADMIN_ROLE = "ADMIN"
RECIPIENT_ROLES = (DOCS_SUPERVISOR_ROLE, ADMIN_ROLE)


def _squash_company(value):
    """
    Uppercase letters and digits only, without accents.

    ---

    Solo letras y dígitos en mayúsculas, sin acentos: "TRANSGRUAL
    S.L." y "TRANSGRUAL SL" quedan iguales.
    """
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", value.upper())


class CompanyKeyResolver:
    """
    Same key for every spelling of the same group company.

    ---

    Misma clave para todas las grafías de una misma empresa del grupo
    (S126). El ámbito de un destinatario guarda el texto de
    `employer_company` que había al guardarlo, y ese texto cambia
    cuando el sistema normaliza la empresa (S125: "TRANSGRUAL S.L." ->
    "TRANSGRUAL SL"); comparando por texto literal el aviso dejaba de
    llegar y la casilla no salía marcada. Se compara por el
    `CompanyFiscalProfile` cuyo nombre o alias casa sin puntos,
    espacios ni acentos; si no casa ninguno, por el texto así
    compactado.
    """

    def __init__(self):
        from document_explorer.models import CompanyFiscalProfile

        self._profiles = []
        for profile in CompanyFiscalProfile.objects.all():
            names = {
                _squash_company(line)
                for line in profile.name_aliases.splitlines()
                if line.strip()
            }
            names.add(_squash_company(profile.legal_name))
            names.discard("")
            self._profiles.append((profile.pk, names))
        self._cache = {}

    def key(self, value):
        """
        Comparison key of a company text.

        ---

        Clave de comparación de un texto de empresa.
        """
        if value not in self._cache:
            squashed = _squash_company(value)
            self._cache[value] = next(
                (
                    "P%d" % pk for pk, names in self._profiles
                    if squashed in names
                ),
                "T:" + squashed,
            )
        return self._cache[value]


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
    company_key: object = None
    whatsapp_enabled: bool = False

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
            company = notice.subject_company
            if self.company_key is not None:
                company = self.company_key(company)
            return (
                self.personal_all
                or company in self.personal_companies
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
    Active notice recipients (documentation supervisors and
    administrators), ordered by name.

    ---

    Destinatarios posibles de avisos activos (supervisores de
    documentación y administradores, S126), por nombre.
    """
    from ivr_config.models import CompanyUser

    queryset = CompanyUser.objects.filter(
        role__in=RECIPIENT_ROLES, is_active=True,
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
    resolver = CompanyKeyResolver()
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
        snapshot = ScopeSnapshot(
            company_user=company_user, company_key=resolver.key,
        )
        if scope is not None:
            person_ids = {p.pk for p in scope.personal_persons.all()}
            for group in scope.personal_groups.all():
                person_ids |= {p.pk for p in group.members.all()}
            snapshot.whatsapp_enabled = scope.whatsapp_enabled
            snapshot.personal_all = scope.personal_all
            snapshot.personal_companies = {
                resolver.key(value) for value in scope.personal_companies
            }
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
