from django.urls import path
from django.contrib import admin
from django.views.generic import TemplateView
from main.views import RatesView, SwapInitView, SwapStatusView

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("api/rates/", RatesView.as_view(), name="rates"),
    path("api/swap/init/", SwapInitView.as_view(), name="swap_init"),
    path("api/swap/<uuid:swap_id>/", SwapStatusView.as_view(), name="swap_status"),
    path("admin/", admin.site.urls),
]
