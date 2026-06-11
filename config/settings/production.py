"""
SIGIP-GB – Production settings (Railway)
"""
from .base import *  # noqa: F401, F403
from decouple import config
import dj_database_url

DEBUG = False

# ── Security ────────────────────────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY')

# Railway injecte le domaine *.railway.app + domaine custom si configuré
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='.railway.app,localhost,127.0.0.1',
    cast=lambda v: [h.strip() for h in v.split(',')]
)

# Railway gère le SSL au niveau du proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False  # Railway redirige déjà en HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# CSRF — accepter le domaine Railway
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.railway.app',
    cast=lambda v: [h.strip() for h in v.split(',')]
)

# ── Database — Railway fournit DATABASE_URL ──────────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        env='DATABASE_URL',
        conn_max_age=60,
        conn_health_checks=True,
    )
}

# ── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='SIGIP-GB <noreply@sigip.gov.gw>')
