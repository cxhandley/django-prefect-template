import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeatureFlag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "name",
                    models.SlugField(
                        unique=True,
                        help_text="Unique identifier used in code (e.g. 'notifications').",
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Global on/off fallback when no user-specific rule applies.",
                    ),
                ),
                (
                    "rollout_percentage",
                    models.PositiveSmallIntegerField(
                        default=0,
                        validators=[django.core.validators.MaxValueValidator(100)],
                        help_text="0 = disabled. 1–100 = percentage of users who see the feature (deterministic).",
                    ),
                ),
                (
                    "enabled_for_users",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Users who always see this feature regardless of other settings.",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
    ]
