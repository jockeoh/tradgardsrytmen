from django.urls import path

from . import api_v1


urlpatterns = [
    path("me/", api_v1.me),
    path("gardens/", api_v1.gardens),
    path("gardens/<uuid:garden_id>/", api_v1.garden_detail),
    path("gardens/<uuid:garden_id>/plants/", api_v1.plants),
    path("gardens/<uuid:garden_id>/plants/<uuid:plant_id>/", api_v1.plant_detail),
    path("gardens/<uuid:garden_id>/tasks/", api_v1.tasks),
    path("gardens/<uuid:garden_id>/tasks/<uuid:task_id>/", api_v1.task_detail),
    path("gardens/<uuid:garden_id>/tasks/<uuid:task_id>/complete/", api_v1.complete_task),
]
