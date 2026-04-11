from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    path("", views.dataset_list, name="dataset_list"),
    path("generate/", views.generate_dataset, name="generate"),
    path("<slug:slug>/", views.dataset_detail, name="detail"),
    path("<slug:slug>/status/", views.dataset_status, name="status"),
    path("<slug:slug>/delete/", views.delete_dataset, name="delete"),
]
