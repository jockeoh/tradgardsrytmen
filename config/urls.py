from django.urls import include, path
from garden import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("api/", include("garden.urls")),
    path("", views.index, name="index"),
]
