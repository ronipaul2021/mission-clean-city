"""
Django settings for BM (Birnagar Municipality) project.
"""

from pathlib import Path
import os

from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent


# ==============================================================================
# SECURITY SETTINGS — loaded from .env (never hardcode secrets)
# ==============================================================================

SECRET_KEY = config('SECRET_KEY', default='django-insecure-fallback-for-local-only')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,.ngrok-free.dev,.ngrok.io', cast=Csv())

# Load from .env so it's not hardcoded — add your ngrok/production domain there
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8000,http://127.0.0.1:8000,https://*.ngrok-free.dev,https://*.ngrok.io',
    cast=Csv()
)


# ==============================================================================
# APPLICATION DEFINITION
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.NoCacheSecureMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.unread_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ==============================================================================
# DATABASE
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # WAL mode: allows concurrent reads during writes — noticeably faster
        # under multiple simultaneous requests (e.g., multiple browser tabs).
        'OPTIONS': {
            'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
        },
    }
}
# For PostgreSQL in production, replace DATABASES with:
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': config('DB_NAME'),
#         'USER': config('DB_USER'),
#         'PASSWORD': config('DB_PASSWORD'),
#         'HOST': config('DB_HOST', default='localhost'),
#         'PORT': config('DB_PORT', default='5432'),
#     }
# }


# ==============================================================================
# CACHING — File-based by default (no Redis/Memcached required)
# ==============================================================================
# Analytics KPIs and chart data are cached for ANALYTICS_CACHE_SECONDS (1 hour).
# Switch CACHE_BACKEND to 'django.core.cache.backends.redis.RedisCache' in production.

CACHE_BACKEND = config('CACHE_BACKEND', default='django.core.cache.backends.filebased.FileBasedCache')
CACHE_LOCATION = config('CACHE_LOCATION', default=str(BASE_DIR / '.cache'))

CACHES = {
    'default': {
        'BACKEND': CACHE_BACKEND,
        'LOCATION': CACHE_LOCATION,
        'TIMEOUT': 3600,            # 1 hour default TTL
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

# How long (seconds) to cache analytics KPI + chart data
ANALYTICS_CACHE_SECONDS = config('ANALYTICS_CACHE_SECONDS', default=3600, cast=int)


# ==============================================================================
# MUNICIPALITY CONFIGURATION — single source of truth for ward definitions
# ==============================================================================

WARD_COUNT = config('WARD_COUNT', default=14, cast=int)
WARD_CHOICES = [(i, str(i)) for i in range(1, WARD_COUNT + 1)]

# Media upload rate limiting (uploads per user per hour)
UPLOAD_RATE_LIMIT = config('UPLOAD_RATE_LIMIT', default=10, cast=int)


# ==============================================================================
# PASSWORD VALIDATION
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ==============================================================================
# INTERNATIONALISATION
# ==============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True


# ==============================================================================
# STATIC & MEDIA FILES
# ==============================================================================

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Disk space alert threshold (bytes). Default: 5 GB.
# Used by: python manage.py check_disk_space
MEDIA_DISK_ALERT_BYTES = config('MEDIA_DISK_ALERT_BYTES', default=5 * 1024 * 1024 * 1024, cast=int)


# ==============================================================================
# AUTHENTICATION
# ==============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.User'
LOGIN_URL = 'citizen_login'
LOGIN_REDIRECT_URL = 'citizen_tracking'


# ==============================================================================
# EMAIL
# ==============================================================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@birnagarmunicipality.gov.in')


# ==============================================================================
# THIRD-PARTY KEYS (all loaded from .env)
# ==============================================================================

ADMIN_REGISTRATION_SECRET = config('ADMIN_REGISTRATION_SECRET', default='BMD@BIRNAGAR#2026')

# Fernet symmetric key for Aadhaar encryption at rest.
# Generate once: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Store in .env — losing this key means Aadhaar data becomes unreadable.
AADHAAR_ENCRYPTION_KEY = config('AADHAAR_ENCRYPTION_KEY', default='')

# Key rotation: when rotating to a new key, set AADHAAR_ENCRYPTION_KEY to the NEW key
# and AADHAAR_ENCRYPTION_KEY_OLD to the previous key.
# The system will transparently re-encrypt old-key records with the new key on access.
# After 30 days, remove AADHAAR_ENCRYPTION_KEY_OLD.
AADHAAR_ENCRYPTION_KEY_OLD = config('AADHAAR_ENCRYPTION_KEY_OLD', default='')

# OTP validity window in minutes
OTP_EXPIRY_MINUTES = config('OTP_EXPIRY_MINUTES', default=10, cast=int)

# OTP resend delay in seconds
OTP_RESEND_DELAY_SECONDS = config('OTP_RESEND_DELAY_SECONDS', default=60, cast=int)

# AI Assistant
BYTEZ_API_KEY = config('BYTEZ_API_KEY', default='')
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')


# ==============================================================================
# SESSION SECURITY
# ==============================================================================

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 3600           # 60 minutes — matches frontend inactivity timer
SESSION_COOKIE_HTTPONLY = True          # Block JS from reading session cookie
SESSION_COOKIE_SECURE = not DEBUG       # HTTPS-only in production
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG


# ==============================================================================
# PRODUCTION SECURITY HEADERS (only active when DEBUG=False)
# ==============================================================================

if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
