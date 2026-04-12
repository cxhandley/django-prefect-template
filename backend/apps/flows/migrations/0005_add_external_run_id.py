# Generated for BL-037: Pluggable Pipeline Backend

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flows", "0004_seed_scoring_model_v1"),
    ]

    operations = [
        migrations.AddField(
            model_name="flowexecution",
            name="external_run_id",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
