from django.db import migrations, models


def fill_order_numbers(apps, schema_editor):
    Swap = apps.get_model("main", "Swap")
    for swap in Swap.objects.filter(order_number=""):
        swap.order_number = f"{swap.created_at.strftime('%Y%m%d%H%M%S')}_{swap.deposit_address[-6:]}"
        swap.save(update_fields=["order_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="swap",
            name="order_number",
            field=models.CharField(blank=True, db_index=True, max_length=40),
        ),
        migrations.AddField(
            model_name="swap",
            name="sweep_tx_hash",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name="swap",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Deposit"),
                    ("confirming", "Deposit Seen, Confirming"),
                    ("received", "Deposit Received"),
                    ("sending", "Sending Funds"),
                    ("complete", "Complete"),
                    ("expired", "Expired"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(fill_order_numbers, migrations.RunPython.noop),
    ]
