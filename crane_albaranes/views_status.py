# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/views_status.py
"""
Twilio delivery status of the planning notices (S165).

---

Informe de entrega de Twilio de los avisos del planning a los gruistas
(S165): POST /api/gruas/aviso-estado/<token>/ con el envío firmado
(crane_albaranes.traffic.status_url). Guarda si se entregó, se leyó o
falló, para Tráfico › Envíos.
"""
import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from crane_albaranes.traffic import notice_pk_from_token, set_notice_status

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class PlanningNoticeStatusView(View):
    """
    POST: Twilio status callback of one planning notice.

    ---

    POST: estado de entrega de Twilio de un envío del planning.
    """

    def post(self, request, token):
        notice_pk = notice_pk_from_token(token)
        if notice_pk is None:
            logger.warning("# [TRÁFICO ESTADO] Token no válido.")
            return HttpResponse(status=403)
        status = request.POST.get("MessageStatus", "")
        logger.info("# [TRÁFICO ESTADO] Envío pk=%s: %s %s", notice_pk,
                    status, request.POST.get("ErrorCode", ""))
        set_notice_status(notice_pk, status)
        return HttpResponse(status=204)
