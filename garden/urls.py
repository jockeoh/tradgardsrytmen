from django.urls import path
from . import views
from .api_support import legacy_garden_required


def secured(view):
    return legacy_garden_required(view)

urlpatterns = [
    path("jobs/<uuid:job_id>/", secured(views.api_job)),
    path("bootstrap/", secured(views.api_bootstrap)),
    path("month/", secured(views.api_month)),
    path("proposals/", secured(views.api_proposals)),
    path("works/<int:work_id>/need/", secured(views.api_need)),
    path("works/<int:work_id>/", secured(views.api_work)),
    path("search/", secured(views.api_search)),
    path("items/", secured(views.api_items)),
    path("items/<int:item_id>/", secured(views.api_item)),
    path("items/<int:item_id>/research/", secured(views.api_research)),
    path("areas/", secured(views.api_areas)),
    path("areas/<int:area_id>/", secured(views.api_area)),
    path("proposals/<int:proposal_id>/", secured(views.api_proposal)),
    path("proposals/<int:proposal_id>/approve/", secured(views.api_approve_proposal)),
    path("tasks/", secured(views.api_tasks)),
    path("tasks/<int:task_id>/", secured(views.api_task)),
    path("rules/<int:rule_id>/", secured(views.api_rule)),
    path("settings/", secured(views.api_settings)),
    path("push/public-key/", secured(views.api_push_public_key)),
    path("push/subscriptions/", secured(views.api_push_subscription)),
    path("push/test/", secured(views.api_push_test)),
]
