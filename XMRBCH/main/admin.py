from django.contrib import admin
from main.models import Swap


@admin.register(Swap)
class SwapAdmin(admin.ModelAdmin):
    list_display = [
        "order_number", "direction", "deposit_amount_expected",
        "send_amount", "status", "created_at",
    ]
    list_filter = ["direction", "status"]
    search_fields = ["order_number", "swap_id", "deposit_address", "receiving_address",
                     "deposit_tx_hash", "send_tx_hash"]
    readonly_fields = [
        "swap_id", "order_number", "created_at", "expires_at",
        "deposit_received_at", "completed_at",
    ]
    ordering = ["-created_at"]
    exclude = ["deposit_private_key"]   # never show private keys in the browser
