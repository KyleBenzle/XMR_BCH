"""
Django settings for XMRTo.Cash.

Everything configurable lives in .env (see .env.example) and is loaded by
config.py. You should not need to edit this file.
"""
import os
import secrets
import sys

# Allow importing config.py from the project folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import config  # noqa: E402  (loads .env)

os.makedirs(config.DATA_DIR, exist_ok=True)


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [v.strip() for v in raw.split(",") if v.strip()]


def _secret_key():
    """Use DJANGO_SECRET_KEY, or create one in data/secret_key on first run."""
    key = os.environ.get('DJANGO_SECRET_KEY')
    if key:
        return key
    path = os.path.join(config.DATA_DIR, 'secret_key')
    if not os.path.exists(path):
        with open(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600), 'w') as f:
            f.write(secrets.token_urlsafe(50))
    with open(path) as f:
        return f.read().strip()


SECRET_KEY = _secret_key()
DEBUG = _env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _env_list('DJANGO_CSRF_TRUSTED_ORIGINS', '')
# gunicorn only listens on 127.0.0.1, so the only client is our own reverse
# proxy (Apache/nginx) — trust the host it forwards.
USE_X_FORWARDED_HOST = True

# URL prefix, e.g. "XMRBCH" → site lives at /XMRBCH/
URL_PREFIX = config.URL_PREFIX
_PREFIX_PATH = f"/{URL_PREFIX}" if URL_PREFIX else ""


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'main',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'xmrbchswap.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'main.views.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'xmrbchswap.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(config.DATA_DIR, 'db.sqlite3'),
        'OPTIONS': {'timeout': 20},
    }
}

CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files are served by Django itself (WhiteNoise) — no web-server config needed.
STATIC_URL = f'{_PREFIX_PATH}/static/'
STATIC_ROOT = os.path.join(config.DATA_DIR, 'staticfiles')
os.makedirs(STATIC_ROOT, exist_ok=True)
WHITENOISE_USE_FINDERS = True   # also works before `collectstatic` has run

LOGIN_URL = f'{_PREFIX_PATH}/admin/login/'
SESSION_COOKIE_PATH = f'{_PREFIX_PATH}/' if _PREFIX_PATH else '/'
CSRF_COOKIE_PATH = SESSION_COOKIE_PATH

if not DEBUG:
    SESSION_COOKIE_SECURE = _env_bool('DJANGO_SESSION_COOKIE_SECURE', True)
    CSRF_COOKIE_SECURE = _env_bool('DJANGO_CSRF_COOKIE_SECURE', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
