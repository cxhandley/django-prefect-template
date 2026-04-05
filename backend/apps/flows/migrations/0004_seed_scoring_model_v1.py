"""
Seed the initial ScoringModel v1.0 capturing the weights and thresholds
that were previously hardcoded in predict_02_score.ipynb.
"""

from django.db import migrations


def seed_scoring_model(apps, schema_editor):
    ScoringModel = apps.get_model("flows", "ScoringModel")
    ScoringModel.objects.get_or_create(
        version="1.0",
        defaults={
            "description": (
                "Initial scoring algorithm. Weights derived from domain expertise; "
                "thresholds calibrated on internal validation set. "
                "Previously hardcoded in predict_02_score.ipynb."
            ),
            "weights": {
                "credit_score": 0.40,
                "income": 0.30,
                "employment_years": 0.20,
                "age": 0.10,
            },
            "thresholds": {
                "approved": 0.70,
                "review": 0.50,
            },
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("flows", "0003_add_prediction_result_scoring_model_execution_step"),
    ]

    operations = [
        migrations.RunPython(seed_scoring_model, migrations.RunPython.noop),
    ]
