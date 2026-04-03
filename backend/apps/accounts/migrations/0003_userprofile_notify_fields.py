from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_add_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="notify_on_success",
            field=models.BooleanField(
                default=False,
                help_text="Notify when an execution completes successfully.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="notify_in_app",
            field=models.BooleanField(
                default=True,
                help_text="Create in-app notifications (bell icon).",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="notify_via_email",
            field=models.BooleanField(
                default=True,
                help_text="Send email notifications.",
            ),
        ),
    ]
