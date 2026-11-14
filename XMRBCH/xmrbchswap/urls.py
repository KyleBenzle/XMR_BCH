from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from django.views.generic import TemplateView

from main.views import RatesView, SwapInitView, SwapStatusView

app_urls = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("api/rates/", RatesView.as_view(), name="rates"),
    path("api/swap/init/", SwapInitView.as_view(), name="swap_init"),
    path("api/swap/<uuid:swap_id>/", SwapStatusView.as_view(), name="swap_status"),
    path("admin/", admin.site.urls),
]

if settings.URL_PREFIX:
    # Everything lives under /<URL_PREFIX>/ so the web server can simply
    # forward that path to us unchanged.
    urlpatterns = [
        path(f"{settings.URL_PREFIX}/", include(app_urls)),
        path("", lambda request: redirect(f"/{settings.URL_PREFIX}/")),
    ]
else:
    urlpatterns = app_urls
