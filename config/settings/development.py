"""
SIGIP-GB – Development settings
Uses SQLite by default so no PostgreSQL install is needed for local dev.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ['*']

# Use SQLite for development (easy setup)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_dev.sqlite3',  # noqa: F405
    }
}

# Django Debug Toolbar (optional – install separately)
try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ['debug_toolbar']  # noqa: F405
    MIDDLEWARE.insert(1, 'debug_toolbar.middleware.DebugToolbarMiddleware')  # noqa: F405
    INTERNAL_IPS = ['127.0.0.1']
except ImportError:
    pass

# CORS – allow everything in dev
CORS_ALLOW_ALL_ORIGINS = True

# Email – print to console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Celery – run tasks synchronously in dev (no Redis needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Simplified static files
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
