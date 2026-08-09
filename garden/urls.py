from django.urls import path
from . import views

urlpatterns = [
    path("bootstrap/", views.api_bootstrap),
    path("search/", views.api_search),
    path("items/", views.api_items),
    path("items/<int:item_id>/", views.api_item),
    path("items/<int:item_id>/research/", views.api_research),
    path("proposals/<int:proposal_id>/", views.api_proposal),
    path("proposals/<int:proposal_id>/approve/", views.api_approve_proposal),
    path("tasks/", views.api_tasks),
    path("tasks/<int:task_id>/", views.api_task),
    path("rules/<int:rule_id>/", views.api_rule),
    path("settings/", views.api_settings),
    path("push/public-key/", views.api_push_public_key),
    path("push/subscriptions/", views.api_push_subscription),
    path("push/test/", views.api_push_test),
]
