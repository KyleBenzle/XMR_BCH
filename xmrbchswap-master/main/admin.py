from django.contrib import admin
from main.models import Swap


@admin.register(Swap)
class SwapAdmin(admin.ModelAdmin):
    list_display = [
        "swap_id", "direction", "deposit_amount_expected",
        "send_amount", "status", "created_at",
    ]
    list_filter = ["direction", "status"]
    search_fields = ["swap_id", "deposit_address", "receiving_address"]
    readonly_fields = [
        "swap_id", "created_at", "expires_at",
        "deposit_received_at", "completed_at",
    ]
    ordering = ["-created_at"]
