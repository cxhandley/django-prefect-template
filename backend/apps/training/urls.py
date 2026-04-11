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
]
