from django.urls import path

from . import api_v1, mobile_workspace
from accounts import mobile


urlpatterns = [
    path("gardens/<uuid:garden_id>/workspace/", mobile_workspace.workspace),
    path("auth/login/", mobile.login),
    path("auth/logout/", mobile.logout),
    path("reconcile/", api_v1.reconcile),
    path("me/", api_v1.me),
    path("gardens/", api_v1.gardens),
    path("gardens/<uuid:garden_id>/", api_v1.garden_detail),
    path("gardens/<uuid:garden_id>/plants/", api_v1.plants),
    path("gardens/<uuid:garden_id>/plants/<uuid:plant_id>/", api_v1.plant_detail),
    path("gardens/<uuid:garden_id>/tasks/", api_v1.tasks),
    path("gardens/<uuid:garden_id>/tasks/<uuid:task_id>/", api_v1.task_detail),
    path("gardens/<uuid:garden_id>/tasks/<uuid:task_id>/complete/", api_v1.complete_task),
]
