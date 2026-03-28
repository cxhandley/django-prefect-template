from django.urls import path
from . import views

app_name = 'flows' 

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('history/', views.history, name='history'),
    path('execution/<uuid:run_id>/', views.execution_detail, name='execution_detail'),
    path('comparison/', views.comparison, name='comparison'),
    path('api/flows-menu/', views.flows_menu, name='flows_menu'),
    path('upload-and-process/', views.upload_and_process, name='upload_and_process'),
    path('status/<uuid:run_id>/', views.flow_status, name='flow_status'),
    path('results/<uuid:run_id>/', views.view_flow_results, name='view_flow_results'),
    path('results/<uuid:run_id>/download/<str:format>/', views.download_results, name='download_results'),
]