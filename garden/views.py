import json
from datetime import date
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.staticfiles import finders
from .models import CarePlanVersion, CareRule, GardenItem, GardenSettings, PushSubscription, ResearchProposal, TaskOccurrence
from .research import ResearchError, approve_proposal, create_research_proposal
from .tasks import dashboard_for, materialize_active_rules, month_end

MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None


def _task_json(task):
    return {
        "id": task.pk, "title": task.title, "instructions": task.instructions, "status": task.status,
        "item": {"id": task.item_id, "name": task.item.name}, "start": task.window_start.isoformat(),
        "end": task.window_end.isoformat(), "month": task.occurrence_month, "manual": task.manual,
        "conditional": bool(task.rule and task.rule.conditional),
        "sources": task.rule.source_urls if task.rule else [],
    }


def _item_json(item, detail=False):
    data = {
        "id": item.pk, "name": item.name, "canonical_name": item.canonical_name, "aliases": item.aliases,
        "category": item.category, "kind": item.kind, "cultivar": item.cultivar, "quantity": item.quantity,
        "age_stage": item.age_stage, "location": item.location, "notes": item.notes, "icon": item.icon,
    }
    if detail:
        data["next_tasks"] = [_task_json(t) for t in item.tasks.filter(status="pending")[:8]]
        plan = item.plans.filter(status="active").first() or item.plans.filter(status="pending").first()
        if plan:
            data["plan"] = _plan_json(plan)
    return data


def _plan_json(plan):
    proposal = getattr(plan, "proposal", None)
    return {
        "id": plan.pk, "version": plan.version, "status": plan.status, "summary": plan.summary,
        "warnings": plan.warnings, "uncertainties": plan.uncertainties,
        "proposal_id": proposal.pk if proposal else None,
        "sources": [{"title": s.title, "url": s.url, "domain": s.domain} for s in plan.sources.all()],
        "rules": [{
            "id": r.pk, "title": r.title, "category": r.category, "instructions": r.instructions,
            "cadence": r.cadence, "start_month": r.start_month, "end_month": r.end_month,
            "conditional": r.conditional, "confidence": r.confidence, "source_validated": r.source_validated,
            "source_urls": r.source_urls,
        } for r in plan.rules.all()],
    }


@require_GET
def health(request):
    GardenSettings.load()
    return JsonResponse({"status": "ok", "service": "tradgardsrytmen", "time": timezone.now().isoformat()})


@ensure_csrf_cookie
def index(request):
    return render(request, "garden/index.html", {"today": timezone.localdate(), "month_name": MONTHS[timezone.localdate().month - 1]})


@require_GET
def service_worker(request):
    path = finders.find("garden/sw.js")
    if not path:
        return HttpResponse("", status=404)
    return HttpResponse(open(path, encoding="utf-8").read(), content_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


@require_GET
def api_bootstrap(request):
    materialize_active_rules()
    day = timezone.localdate()
    board = dashboard_for(day)
    completed = board.pop("completed")
    task_groups = {key: [_task_json(t) for t in value] for key, value in board.items()}
    total = completed + sum(len(v) for v in task_groups.values())
    settings = GardenSettings.load()
    return JsonResponse({
        "today": day.isoformat(), "month_name": MONTHS[day.month - 1], "completed": completed,
        "total": total, "progress": round(completed * 100 / total) if total else 0,
        "tasks": task_groups, "items": [_item_json(i) for i in GardenItem.objects.filter(active=True)],
        "settings": {"garden_name": settings.garden_name, "city": settings.city, "cultivation_zone": settings.cultivation_zone, "exposure": settings.exposure},
        "pending_proposals": ResearchProposal.objects.filter(status="pending").count(),
        "year": [{"month": m, "name": MONTHS[m-1], "open": TaskOccurrence.objects.filter(status="pending", window_start__lte=month_end(day.year, m), window_end__gte=date(day.year, m, 1)).count()} for m in range(1, 13)],
    })


@require_GET
def api_search(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    normalized = "Flammentanz" if query.casefold() == "flammantz" else query
    item_hits = GardenItem.objects.filter(Q(name__icontains=normalized) | Q(canonical_name__icontains=normalized) | Q(category__icontains=normalized) | Q(cultivar__icontains=normalized) | Q(notes__icontains=normalized))[:8]
    results = [{"type": "item", "id": i.pk, "title": i.name, "subtitle": " · ".join(x for x in [i.category, i.cultivar] if x)} for i in item_hits]
    for item in GardenItem.objects.filter(active=True):
        if any(normalized.casefold() in str(alias).casefold() for alias in item.aliases) and not any(r["id"] == item.pk for r in results):
            results.append({"type": "item", "id": item.pk, "title": item.name, "subtitle": "Alias"})
    tasks = TaskOccurrence.objects.filter(Q(title__icontains=normalized) | Q(instructions__icontains=normalized)).select_related("item")[:8]
    results.extend({"type": "task", "id": t.pk, "title": t.title, "subtitle": t.item.name} for t in tasks)
    plans = CarePlanVersion.objects.filter(Q(summary__icontains=normalized) | Q(item__name__icontains=normalized)).select_related("item")[:5]
    results.extend({"type": "care", "id": p.item_id, "title": f"Skötselråd: {p.item.name}", "subtitle": p.summary[:90]} for p in plans)
    return JsonResponse({"results": results[:15]})


@require_http_methods(["GET", "POST"])
def api_items(request):
    if request.method == "GET":
        return JsonResponse({"items": [_item_json(i) for i in GardenItem.objects.filter(active=True)]})
    data = _json_body(request)
    if data is None or not data.get("name"):
        return JsonResponse({"error": "Namn krävs."}, status=400)
    item = GardenItem.objects.create(
        name=data["name"].strip(), canonical_name=data.get("canonical_name", ""), aliases=data.get("aliases", []),
        category=data.get("category", ""), kind=data.get("kind", "individual"), cultivar=data.get("cultivar", ""),
        quantity=max(1, int(data.get("quantity", 1))), age_stage=data.get("age_stage", ""),
        location=data.get("location", ""), notes=data.get("notes", ""),
    )
    response = {"item": _item_json(item)}
    try:
        proposal = create_research_proposal(item, GardenSettings.load())
        response["proposal"] = _plan_json(proposal.plan)
    except ResearchError as exc:
        response["research_error"] = str(exc)
    return JsonResponse(response, status=201)


@require_http_methods(["GET", "PATCH"])
def api_item(request, item_id):
    item = get_object_or_404(GardenItem, pk=item_id, active=True)
    if request.method == "GET":
        return JsonResponse({"item": _item_json(item, True), "proposals": [_plan_json(p.plan) for p in item.proposals.filter(status="pending").order_by("-plan__version")]})
    data = _json_body(request) or {}
    for field in ["name", "canonical_name", "aliases", "category", "kind", "cultivar", "quantity", "age_stage", "location", "notes"]:
        if field in data:
            setattr(item, field, data[field])
    item.save()
    return JsonResponse({"item": _item_json(item, True)})


@require_POST
def api_research(request, item_id):
    item = get_object_or_404(GardenItem, pk=item_id, active=True)
    try:
        proposal = create_research_proposal(item, GardenSettings.load())
    except ResearchError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse({"proposal": _plan_json(proposal.plan)}, status=201)


@require_http_methods(["GET", "DELETE"])
def api_proposal(request, proposal_id):
    proposal = get_object_or_404(ResearchProposal, pk=proposal_id)
    if request.method == "GET":
        return JsonResponse({"proposal": _plan_json(proposal.plan)})
    proposal.status = "rejected"
    proposal.reviewed_at = timezone.now()
    proposal.save(update_fields=["status", "reviewed_at"])
    proposal.plan.status = "rejected"
    proposal.plan.save(update_fields=["status"])
    return JsonResponse({"ok": True})


@require_POST
def api_approve_proposal(request, proposal_id):
    proposal = get_object_or_404(ResearchProposal, pk=proposal_id, status="pending")
    data = _json_body(request) or {}
    selected = approve_proposal(proposal, [int(v) for v in data.get("rule_ids", [])])
    return JsonResponse({"ok": True, "approved": len(selected)})


@require_POST
def api_tasks(request):
    data = _json_body(request) or {}
    try:
        item = GardenItem.objects.get(pk=data.get("item_id"), active=True)
        start = date.fromisoformat(data["window_start"])
        end = date.fromisoformat(data.get("window_end") or data["window_start"])
    except (GardenItem.DoesNotExist, KeyError, ValueError):
        return JsonResponse({"error": "Kontrollera växt och datum."}, status=400)
    task = TaskOccurrence.objects.create(
        item=item, title=data.get("title", "Egen uppgift").strip(), instructions=data.get("instructions", ""),
        occurrence_key=f"manual:{timezone.now().timestamp()}:{item.pk}", season_year=start.year,
        occurrence_month=start.month, window_start=start, window_end=end, manual=True,
    )
    return JsonResponse({"task": _task_json(task)}, status=201)


@require_http_methods(["GET", "PATCH"])
def api_task(request, task_id):
    task = get_object_or_404(TaskOccurrence.objects.select_related("item", "rule"), pk=task_id)
    if request.method == "GET":
        return JsonResponse({"task": _task_json(task)})
    data = _json_body(request) or {}
    status = data.get("status")
    if status in {"pending", "completed", "skipped"}:
        task.status = status
        task.completed_at = timezone.now() if status == "completed" else None
        task.skipped_at = timezone.now() if status == "skipped" else None
    for field in ["title", "instructions", "note"]:
        if field in data:
            setattr(task, field, data[field])
    task.save()
    return JsonResponse({"task": _task_json(task)})


@require_http_methods(["PATCH"])
def api_rule(request, rule_id):
    rule = get_object_or_404(CareRule, pk=rule_id, plan__status="pending")
    data = _json_body(request) or {}
    for field in ["title", "category", "instructions", "cadence", "start_month", "end_month", "conditional"]:
        if field in data:
            setattr(rule, field, data[field])
    if not 1 <= int(rule.start_month) <= 12 or not 1 <= int(rule.end_month) <= 12:
        return JsonResponse({"error": "Månad måste vara 1–12."}, status=400)
    rule.save()
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "PATCH"])
def api_settings(request):
    settings = GardenSettings.load()
    if request.method == "PATCH":
        data = _json_body(request) or {}
        for field in ["garden_name", "city", "cultivation_zone", "exposure", "monthly_digest_day", "reminder_weekday", "reminder_hour"]:
            if field in data:
                setattr(settings, field, data[field])
        settings.save()
    return JsonResponse({"settings": {"garden_name": settings.garden_name, "city": settings.city, "cultivation_zone": settings.cultivation_zone, "exposure": settings.exposure, "monthly_digest_day": settings.monthly_digest_day, "reminder_weekday": settings.reminder_weekday, "reminder_hour": settings.reminder_hour}})


@require_GET
def api_push_public_key(request):
    from .vapid import get_vapid_keys
    return JsonResponse({"public_key": get_vapid_keys()[0]})


@require_http_methods(["POST", "DELETE"])
def api_push_subscription(request):
    data = _json_body(request) or {}
    endpoint = data.get("endpoint") or (data.get("subscription") or {}).get("endpoint")
    if not endpoint:
        return JsonResponse({"error": "Prenumerationen saknar endpoint."}, status=400)
    if request.method == "DELETE":
        PushSubscription.objects.filter(endpoint=endpoint).update(active=False)
        return JsonResponse({"ok": True})
    raw = data.get("subscription") or data
    keys = raw.get("keys") or {}
    sub, _ = PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        "p256dh": keys.get("p256dh", ""), "auth": keys.get("auth", ""), "device_name": data.get("device_name", "iPhone/PWA"),
        "monthly_digest": bool(data.get("monthly_digest", False)), "task_reminders": bool(data.get("task_reminders", False)), "active": True,
    })
    return JsonResponse({"ok": True, "id": sub.pk})


@require_POST
def api_push_test(request):
    from .push import send_test_push
    sent = send_test_push()
    return JsonResponse({"ok": True, "sent": sent})
