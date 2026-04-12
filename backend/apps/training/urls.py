from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    # Dataset management
    path("", views.dataset_list, name="dataset_list"),
    path("generate/", views.generate_dataset, name="generate"),
    path("<slug:slug>/", views.dataset_detail, name="detail"),
    path("<slug:slug>/status/", views.dataset_status, name="status"),
    path("<slug:slug>/delete/", views.delete_dataset, name="delete"),
    # Training runs
    path("<slug:slug>/runs/", views.run_list, name="run_list"),
    path("<slug:slug>/runs/start/", views.start_run, name="start_run"),
    path("runs/<int:run_id>/", views.run_detail, name="run_detail"),
    path("runs/<int:run_id>/status/", views.run_status, name="run_status"),
    # Backtest
    path("runs/<int:run_id>/backtest/", views.trigger_backtest, name="trigger_backtest"),
    path("runs/<int:run_id>/backtest/section/", views.backtest_section, name="backtest_section"),
    path("runs/<int:run_id>/backtest/export/", views.backtest_export, name="backtest_export"),
    # Charts — return Altair JSON specs
    path("runs/compare/charts/metrics/", views.chart_compare_metrics, name="chart_compare_metrics"),
    path("runs/<int:run_id>/charts/umap/", views.chart_umap, name="chart_umap"),
    path(
        "runs/<int:run_id>/charts/score-distribution/",
        views.chart_score_distribution,
        name="chart_score_distribution",
    ),
    path(
        "runs/<int:run_id>/charts/confusion-matrix/",
        views.chart_confusion_matrix,
        name="chart_confusion_matrix",
    ),
    path(
        "runs/<int:run_id>/charts/class-metrics/",
        views.chart_class_metrics,
        name="chart_class_metrics",
    ),
    path("<slug:slug>/charts/gini-trend/", views.chart_gini_trend, name="chart_gini_trend"),
]
