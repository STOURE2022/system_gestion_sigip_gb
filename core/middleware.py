"""
Middleware de auditoria e linguagem para SGPIP.
"""
import logging
from django.utils import translation
from .models import AuditLog

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class ForceAdminLanguageMiddleware:
    """Force Portuguese for the admin interface, regardless of browser language."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin'):
            translation.activate('pt')
            request.LANGUAGE_CODE = 'pt'
        response = self.get_response(request)
        return response


class AuditLogMiddleware:
    """
    Middleware que regista acções de login e logout no AuditLog.
    As acções CRUD são registadas nos serializers/views.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        return None
