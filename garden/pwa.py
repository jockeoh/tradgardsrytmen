"""Session-only adapter to the existing v1 completion/receipt contract."""
from django.contrib.staticfiles import finders
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import api_v1
from .api_support import active_membership, legacy_garden_required, web_context_token, parse_json_object
from .models import GardenMembership, TaskOccurrence


@never_cache
@require_GET
def shell(request):
    # Deliberately public and identity-free; the SW may store this file only.
    return FileResponse(open(finders.find('garden/worklist.html'), 'rb'), content_type='text/html')


@never_cache
@require_GET
def context(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({'code': 'unauthenticated'}, status=401)
    member = active_membership(request)
    if member is None:
        return JsonResponse({'code': 'select_garden'}, status=409)
    return JsonResponse({
        'boundary': request.pwa_boundary, 'protocol': 1, 'account': str(request.user.public_id),
        'garden': str(member.garden.public_id), 'membership': member.pk,
        'name': member.garden.name, 'account_name': request.user.username,
        'token': web_context_token(member), 'csrf': get_token(request),
    })


@require_GET
@legacy_garden_required
def snapshot(request):
    rows = TaskOccurrence.objects.filter(item__garden=request.garden).select_related('item', 'item__garden').order_by('window_start', 'pk')
    return JsonResponse({'protocol': 1, 'tasks': [dict(api_v1._task_json(t), plant_name=t.item.name) for t in rows]})


@require_POST
@transaction.atomic
@legacy_garden_required
def complete(request, task_id):
    if request.headers.get("Authorization"):
        return JsonResponse({"code": "session_required"}, status=403)
    # Pin the exact grant through the v1 transaction, including receipt replay.
    if not GardenMembership.objects.select_for_update().filter(pk=request.garden_membership.pk).exists():
        return JsonResponse({'code': 'context_changed'}, status=409)
    request.path = f'/api/v1/gardens/{request.garden.public_id}/tasks/{task_id}/complete/'
    return api_v1.complete_task(request, request.garden.public_id, task_id)


@require_POST
@legacy_garden_required
def reconcile(request):
    if request.headers.get("Authorization"):
        return JsonResponse({"code": "session_required"}, status=403)
    body = parse_json_object(request)
    prefix = f'/api/v1/gardens/{request.garden.public_id}/tasks/'
    if not body or not isinstance(body.get('path'), str) or not body['path'].startswith(prefix) or not body['path'].endswith('/complete/'):
        return JsonResponse({'code': 'context_changed'}, status=409)
    return api_v1.reconcile(request)
