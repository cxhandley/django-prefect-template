from django.urls import path

from . import views

app_name = "flows"

urlpatterns = [
    path("", views.index, name="index"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("history/", views.history, name="history"),
    path("history/export/", views.export_history_csv, name="export_history_csv"),
    path("execution/<uuid:run_id>/", views.execution_detail, name="execution_detail"),
    path("execution/<uuid:run_id>/stop/", views.stop_execution, name="stop_execution"),
    path("execution/<uuid:run_id>/delete/", views.delete_execution, name="delete_execution"),
    path("execution/<uuid:run_id>/retry/", views.retry_execution, name="retry_execution"),
    path("comparison/", views.comparison, name="comparison"),
    path("comparison/export/", views.comparison_export, name="comparison_export"),
    path("api/flows-menu/", views.flows_menu, name="flows_menu"),
    path("upload-and-process/", views.upload_and_process, name="upload_and_process"),
    path("run-prediction/", views.run_prediction, name="run_prediction"),
    path("prediction-status/<uuid:run_id>/", views.prediction_status, name="prediction_status"),
    path("status/<uuid:run_id>/", views.flow_status, name="flow_status"),
    path("results/<uuid:run_id>/", views.view_flow_results, name="view_flow_results"),
    path(
        "results/<uuid:run_id>/download/<str:format>/",
        views.download_results,
        name="download_results",
    ),
    # Input presets
    path("presets/save/", views.save_preset, name="save_preset"),
    path("presets/load/", views.load_preset, name="load_preset"),
    path("presets/<int:preset_id>/delete/", views.delete_preset, name="delete_preset"),
    # Admin monitoring (staff-only)
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/executions/", views.admin_executions, name="admin_executions"),
    path(
        "admin/executions/<uuid:run_id>/",
        views.admin_execution_detail,
        name="admin_execution_detail",
    ),
]
