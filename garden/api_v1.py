from datetime import date, timezone as dt_timezone

from django.db import transaction
from django.db.models import Q
from django.core import signing
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from uuid import UUID, uuid4

from .api_support import api_authenticated, api_error, idempotent_mutation, parse_json_object
from .models import Garden, GardenItem, GardenMembership, TaskOccurrence


def _timestamp(value):
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def _garden_json(garden, role):
    return {"id": str(garden.public_id), "name": garden.name, "role": role, "version": garden.version, "created_at": _timestamp(garden.created_at)}


def _plant_json(item):
    return {
        "id": str(item.public_id), "garden_id": str(item.garden.public_id), "name": item.name,
        "notes": item.notes, "has_care_plan": item.plans.filter(status="active").exists(),
        "version": item.version, "created_at": _timestamp(item.created_at),
    }


def _task_json(task):
    return {
        "id": str(task.public_id), "garden_id": str(task.item.garden.public_id),
        "plant_id": str(task.item.public_id), "title": task.title, "instructions": task.instructions,
        "due_date": task.window_start.isoformat(), "status": task.status, "manual": task.manual,
        "note": task.note, "completed_at": _timestamp(task.completed_at) if task.completed_at else None,
        "version": task.version, "created_at": _timestamp(task.created_at), "updated_at": _timestamp(task.updated_at),
    }


def _body(request, allowed, required=()):
    data = parse_json_object(request)
    if data is None:
        return None, api_error("invalid_json", "Begäran innehåller inte giltig JSON.", 400)
    unknown = sorted(set(data) - set(allowed))
    missing = [field for field in required if field not in data]
    fields = {}
    for field in unknown:
        fields[field] = ["unknown"]
    for field in missing:
        fields.setdefault(field, []).append("required")
    if fields:
        return None, api_error("validation_error", "Kontrollera uppgifterna.", 400, fields)
    return data, None


def _name(data, field="name", maximum=120):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        return None, {field: ["required"]}
    value = value.strip()
    if len(value) > maximum:
        return None, {field: ["too_long"]}
    return value, None


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _membership(user, garden_id):
    return GardenMembership.objects.select_related("garden").filter(user=user, garden__public_id=garden_id).first()


def _limit(request):
    try:
        value = int(request.GET.get("limit", "50"))
    except ValueError:
        return None
    return value if 1 <= value <= 100 else None


def _list_response(request, queryset, serializer, limit, context, time_field="created_at", id_field="pk", row_time=None, row_id=None):
    cursor = request.GET.get("cursor")
    if cursor:
        try:
            payload = signing.loads(cursor, salt="garden-api-v1-cursor", max_age=60 * 60 * 24 * 30)
            if payload.get("context") != context:
                raise signing.BadSignature
            after_time = payload["time"]
            after_id = payload["id"]
        except (signing.BadSignature, KeyError, TypeError):
            return None
        queryset = queryset.filter(
            Q(**{f"{time_field}__gt": after_time}) |
            Q(**{time_field: after_time, f"{id_field}__gt": after_id})
        )
    rows = list(queryset.order_by(time_field, id_field)[: limit + 1])
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1]
        timestamp = row_time(last) if row_time else getattr(last, time_field)
        identifier = row_id(last) if row_id else getattr(last, id_field)
        next_cursor = signing.dumps({"context": context, "time": timestamp.isoformat(), "id": identifier}, salt="garden-api-v1-cursor", compress=True)
    return {"results": [serializer(row) for row in page], "next_cursor": next_cursor}


@require_GET
@api_authenticated
def me(request):
    user = request.api_user
    return JsonResponse({"id": str(user.public_id), "display_name": user.get_full_name() or user.username})


@require_http_methods(["GET", "POST"])
@api_authenticated
def gardens(request):
    if request.method == "GET":
        limit = _limit(request)
        if limit is None:
            return api_error("invalid_cursor", "Listmarkören är ogiltig.", 400)
        memberships = GardenMembership.objects.filter(user=request.api_user).select_related("garden")
        payload = _list_response(request, memberships, lambda row: _garden_json(row.garden, row.role), limit,
            f"gardens:{request.api_user.pk}", time_field="garden__created_at", id_field="garden_id",
            row_time=lambda row: row.garden.created_at, row_id=lambda row: row.garden_id)
        if payload is None:
            return api_error("invalid_cursor", "Listmarkören är ogiltig.", 400)
        return JsonResponse(payload)
    data, error = _body(request, {"name"}, {"name"})
    if error:
        return error
    name, fields = _name(data)
    if fields:
        return api_error("validation_error", "Kontrollera uppgifterna.", 400, fields)

    def create():
        garden = Garden.objects.create(name=name)
        GardenMembership.objects.create(garden=garden, user=request.api_user, role=GardenMembership.Role.OWNER)
        return 201, _garden_json(garden, GardenMembership.Role.OWNER)

    def replay_allowed(payload):
        return GardenMembership.objects.filter(user=request.api_user, garden__public_id=payload.get("id")).exists()

    return idempotent_mutation(request, data, create, replay_allowed)


@require_GET
@api_authenticated
def garden_detail(request, garden_id):
    membership = _membership(request.api_user, garden_id)
    if not membership:
        return api_error("not_found", "Trädgården finns inte.", 404)
    return JsonResponse(_garden_json(membership.garden, membership.role))


@require_http_methods(["GET", "POST"])
@api_authenticated
def plants(request, garden_id):
    membership = _membership(request.api_user, garden_id)
    if not membership:
        return api_error("not_found", "Trädgården finns inte.", 404)
    if request.method == "GET":
        limit = _limit(request)
        if limit is None:
            return api_error("invalid_cursor", "Listmarkören är ogiltig.", 400)
        payload = _list_response(request, GardenItem.objects.filter(garden=membership.garden, active=True), _plant_json, limit, f"plants:{membership.garden_id}")
        if payload is None:
            return api_error("invalid_cursor", "Listmarkören är ogiltig.", 400)
        return JsonResponse(payload)
    data, error = _body(request, {"name", "notes"}, {"name"})
    if error:
        return error
    name, fields = _name(data)
    notes = data.get("notes", "")
    if not isinstance(notes, str):
        fields = {"notes": ["invalid"]}
    elif len(notes) > 10000:
        fields = {"notes": ["too_long"]}
    if fields:
        return api_error("validation_error", "Kontrollera uppgifterna.", 400, fields)

    def create():
        item = GardenItem.objects.create(garden=membership.garden, name=name, notes=notes)
        return 201, _plant_json(item)

    return idempotent_mutation(request, data, create)


@require_GET
@api_authenticated
def plant_detail(request, garden_id, plant_id):
    membership = _membership(request.api_user, garden_id)
    if not membership:
        return api_error("not_found", "Växten finns inte.", 404)
    item = GardenItem.objects.filter(garden=membership.garden, public_id=plant_id, active=True).first()
    if not item:
        return api_error("not_found", "Växten finns inte.", 404)
    return JsonResponse(_plant_json(item))


@require_http_methods(["GET", "POST"])
@api_authenticated
def tasks(request, garden_id):
    membership = _membership(request.api_user, garden_id)
    if not membership:
        return api_error("not_found", "Trädgården finns inte.", 404)
    if request.method == "GET":
        limit = _limit(request)
        if limit is None:
            return api_error("invalid_cursor", "Listmarkören är ogiltig.", 400)
        queryset = TaskOccurrence.objects.filter(item__garden=membership.garden).select_related("item", "item__garden")
        status = request.GET.get("status")
        if status:
            if status not in dict(TaskOccurrence.STATUS_CHOICES):
                return api_error("validation_error", "Kontrollera filtren.", 400, {"status": ["invalid"]})
            queryset = queryset.filter(status=status)
        plant_id = request.GET.get("plant_id")
        if plant_id:
            plant_uuid = _uuid(plant_id)
            if plant_uuid is None or not GardenItem.objects.filter(garden=membership.garden, public_id=plant_uuid).exists():
                return api_error("not_found", "Växten finns inte.", 404)
            queryset = queryset.filter(item__public_id=plant_uuid)
        context = f"tasks:{membership.garden_id}:status={status or ''}:plant={plant_id or ''}"
        payload = _list_response(request, queryset, _task_json, limit, context)
        if payload is None:
            return api_error("invalid_cursor", "Listmarkören är ogiltig.", 400)
        return JsonResponse(payload)
    data, error = _body(request, {"plant_id", "title", "instructions", "due_date"}, {"plant_id", "title", "due_date"})
    if error:
        return error
    title, fields = _name(data, "title", 180)
    instructions = data.get("instructions", "")
    if not isinstance(instructions, str):
        fields = {**(fields or {}), "instructions": ["invalid"]}
    elif len(instructions) > 10000:
        fields = {**(fields or {}), "instructions": ["too_long"]}
    try:
        due_date = date.fromisoformat(data["due_date"])
    except (ValueError, TypeError):
        fields = {**(fields or {}), "due_date": ["invalid"]}
        due_date = None
    plant_uuid = _uuid(data.get("plant_id"))
    item = GardenItem.objects.filter(garden=membership.garden, public_id=plant_uuid, active=True).first() if plant_uuid else None
    if item is None:
        return api_error("not_found", "Växten finns inte.", 404)
    if fields:
        return api_error("validation_error", "Kontrollera uppgifterna.", 400, fields)

    def create():
        task = TaskOccurrence.objects.create(
            item=item, title=title, instructions=instructions, occurrence_key=f"manual:{uuid4()}",
            season_year=due_date.year, occurrence_month=due_date.month, window_start=due_date, window_end=due_date, manual=True,
        )
        return 201, _task_json(task)

    return idempotent_mutation(request, data, create)


def _authorized_task(user, garden_id, task_id):
    membership = _membership(user, garden_id)
    if not membership:
        return None, None
    task = TaskOccurrence.objects.select_related("item", "item__garden").filter(item__garden=membership.garden, public_id=task_id).first()
    return membership, task


@require_GET
@api_authenticated
def task_detail(request, garden_id, task_id):
    _, task = _authorized_task(request.api_user, garden_id, task_id)
    if not task:
        return api_error("not_found", "Uppgiften finns inte.", 404)
    return JsonResponse(_task_json(task))


@require_POST
@api_authenticated
def complete_task(request, garden_id, task_id):
    membership, task = _authorized_task(request.api_user, garden_id, task_id)
    if not task:
        return api_error("not_found", "Uppgiften finns inte.", 404)
    data, error = _body(request, {"expected_version", "note"}, {"expected_version"})
    if error:
        return error
    if type(data.get("expected_version")) is not int or data["expected_version"] < 1:
        return api_error("validation_error", "Kontrollera uppgifterna.", 400, {"expected_version": ["invalid"]})
    note = data.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 10000):
        return api_error("validation_error", "Kontrollera uppgifterna.", 400, {"note": ["too_long" if isinstance(note, str) else "invalid"]})

    def complete():
        locked = TaskOccurrence.objects.select_for_update().select_related("item", "item__garden").get(pk=task.pk)
        if locked.version != data["expected_version"]:
            return 409, {"error": {"code": "version_conflict", "message": "Uppgiften har ändrats. Hämta den senaste versionen.", "fields": {}, "request_id": f"req_{uuid4().hex}"}}
        if locked.status != "pending":
            return 409, {"error": {"code": "invalid_transition", "message": "Uppgiften kan inte markeras klar från sitt nuvarande läge.", "fields": {}, "request_id": f"req_{uuid4().hex}"}}
        locked.status = "completed"
        locked.completed_at = timezone.now()
        if note is not None:
            locked.note = note
        locked.version += 1
        locked.save(update_fields=["status", "completed_at", "note", "version", "updated_at"])
        return 200, _task_json(locked)

    return idempotent_mutation(request, data, complete)
