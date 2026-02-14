from django.urls import path
from . import views

app_name = 'flows' 

urlpatterns = [
    path('', views.index, name='index'),
    path('api/flows-menu/', views.flows_menu, name='flows_menu'),
    path('results/<uuid:run_id>', views.view_flow_results, name='view_flow_results'),
    path('upload-and-process/', views.upload_and_process, name='upload_and_process'),
    
]