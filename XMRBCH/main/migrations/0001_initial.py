import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Swap",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("swap_id", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
                ("direction", models.CharField(
                    max_length=15,
                    choices=[("bch_to_xmr", "BCH → XMR"), ("xmr_to_bch", "XMR → BCH")],
                )),
                ("deposit_address", models.CharField(max_length=300)),
                ("deposit_private_key", models.CharField(max_length=300, blank=True)),
                ("xmr_subaddress_index", models.IntegerField(null=True, blank=True)),
                ("receiving_address", models.CharField(max_length=300)),
                ("deposit_amount_expected", models.DecimalField(max_digits=24, decimal_places=12)),
                ("deposit_amount_received", models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)),
                ("send_amount", models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)),
                ("rate", models.DecimalField(max_digits=24, decimal_places=12)),
                ("status", models.CharField(
                    max_length=20,
                    default="pending",
                    choices=[
                        ("pending",  "Pending Deposit"),
                        ("received", "Deposit Received"),
                        ("sending",  "Sending Funds"),
                        ("complete", "Complete"),
                        ("expired",  "Expired"),
                        ("failed",   "Failed"),
                    ],
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("deposit_received_at", models.DateTimeField(null=True, blank=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("deposit_tx_hash", models.CharField(max_length=200, blank=True)),
                ("send_tx_hash", models.CharField(max_length=200, blank=True)),
                ("notes", models.TextField(blank=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
