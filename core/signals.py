"""
Django signals for the core app.
"""
import logging
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .models import AuditLog

logger = logging.getLogger(__name__)


def _get_ip(request):
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
    return None


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    try:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.LOGIN,
            model_name='User',
            object_id=str(user.pk),
            ip_address=_get_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else '',
        )
    except Exception as e:
        logger.warning(f'Could not create audit log for login: {e}')


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    if user:
        try:
            AuditLog.objects.create(
                user=user,
                action=AuditLog.Action.LOGOUT,
                model_name='User',
                object_id=str(user.pk),
                ip_address=_get_ip(request),
            )
        except Exception as e:
            logger.warning(f'Could not create audit log for logout: {e}')
