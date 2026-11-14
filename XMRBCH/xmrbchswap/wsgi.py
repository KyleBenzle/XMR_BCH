"""WSGI entry point (used by gunicorn: xmrbchswap.wsgi:application)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "xmrbchswap.settings")

application = get_wsgi_application()
