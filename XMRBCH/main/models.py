import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
import config


def make_order_number(deposit_address, when=None):
    when = when or timezone.now()
    return f"{when.strftime('%Y%m%d%H%M%S')}_{deposit_address[-6:]}"


class Swap(models.Model):
    DIRECTION_CHOICES = [
        ('bch_to_xmr', 'BCH → XMR'),
        ('xmr_to_bch', 'XMR → BCH'),
    ]
    STATUS_CHOICES = [
        ('pending',    'Pending Deposit'),
        ('confirming', 'Deposit Seen, Confirming'),
        ('received',   'Deposit Received'),
        ('sending',  'Sending Funds'),
        ('complete', 'Complete'),
        ('expired',  'Expired'),
        ('failed',   'Failed'),
    ]

    # Public identifier
    swap_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Human-friendly order number: YYYYMMDDHHMMSS_<last 6 of deposit address>
    order_number = models.CharField(max_length=40, blank=True, db_index=True)

    # Direction of swap
    direction = models.CharField(max_length=15, choices=DIRECTION_CHOICES)

    # Deposit address (what we give the user to send funds to)
    deposit_address = models.CharField(max_length=300)
    # BCH deposit: store WIF so monitor can check balance & sweep
    deposit_private_key = models.CharField(max_length=300, blank=True)
    # XMR deposit: store subaddress index for wallet RPC queries
    xmr_subaddress_index = models.IntegerField(null=True, blank=True)

    # User's address to receive the output currency
    receiving_address = models.CharField(max_length=300)

    # Amounts (12 decimal places covers both BCH satoshis and XMR piconero)
    deposit_amount_expected = models.DecimalField(max_digits=24, decimal_places=12)
    deposit_amount_received = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    send_amount = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)

    # Rate at time of creation (output per 1 input, after fee)
    rate = models.DecimalField(max_digits=24, decimal_places=12)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    deposit_received_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Transaction hashes
    deposit_tx_hash = models.CharField(max_length=200, blank=True)
    send_tx_hash = models.CharField(max_length=200, blank=True)
    # BCH→XMR: tx that moved the deposit into the operational wallet
    sweep_tx_hash = models.CharField(max_length=200, blank=True)

    # Notes / error messages
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=config.SWAP_EXPIRY_HOURS)
        if not self.order_number and self.deposit_address:
            self.order_number = make_order_number(self.deposit_address)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at and self.status in ('pending', 'confirming')

    def from_currency(self):
        return 'BCH' if self.direction == 'bch_to_xmr' else 'XMR'

    def to_currency(self):
        return 'XMR' if self.direction == 'bch_to_xmr' else 'BCH'

    def __str__(self):
        return f"{self.swap_id} | {self.direction} | {self.status}"

    class Meta:
        ordering = ['-created_at']
