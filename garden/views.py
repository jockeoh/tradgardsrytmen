import json
from datetime import date
from django.db import IntegrityError, transaction
from django.db.models import Q, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.staticfiles import finders
from .models import CarePlanVersion, CareRule, GardenArea, GardenItem, GardenSettings, PushSubscription, ResearchProposal, TaskOccurrence, WorkIdentity
from .research import ResearchError, approve_proposal, create_research_proposal
from .tasks import dashboard_for, visible_pending, month_end, needs_now, set_excluded
from .care_contract import validate_rule, CareValidationError, plan_comparison, canonical_scope
from .work_categories import WORK_CATEGORIES, normalize_work_category

MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]


def _json_body(request):
    try:
        value = json.loads(request.body or "{}")
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _task_json(task):
    category = normalize_work_category(task.category or (task.rule.category if task.rule else ""), task.title, task.instructions)
    area = {"id": task.item.area_id, "name": task.item.area.name} if task.item.area_id else None
    return {
        "work_id": task.work_id, "scope": task.work.scope if task.work else "",
        "relevance_reason": task.rule.relevance_reason if task.rule else "",
        "archive_reason": task.archive_reason, "note": task.note,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "id": task.pk, "title": task.title, "instructions": task.instructions, "status": task.status,
        "category": category, "area": area, "location_detail": task.item.location,
        "item": {"id": task.item_id, "name": task.item.name}, "start": task.window_start.isoformat(),
        "end": task.window_end.isoformat(), "month": task.occurrence_month, "manual": task.manual,
        "conditional": bool(task.rule and task.rule.conditional),
        "sources": task.rule.source_urls if task.rule else [],
    }


def _item_json(item, detail=False):
    area = {"id": item.area_id, "name": item.area.name} if item.area_id else None
    data = {
        "id": item.pk, "name": item.name, "canonical_name": item.canonical_name, "aliases": item.aliases,
        "category": item.category, "kind": item.kind, "cultivar": item.cultivar, "quantity": item.quantity,
        "has_care_plan": item.plans.filter(status="active").exists(),
        "age_stage": item.age_stage, "area": area, "area_id": item.area_id,
        "location": item.location, "location_detail": item.location, "notes": item.notes, "icon": item.icon,
    }
    if detail:
        data["next_tasks"] = [_task_json(t) for t in visible_pending().filter(item=item)]
        data["history"] = [_task_json(t) for t in item.tasks.exclude(status="pending").select_related("rule", "work").order_by("-updated_at")]
        data["advice"] = [_rule_json(r) for r in item.care_rules.filter(active=True, advice_kind__in=["on_demand", "general"], work__excluded_at__isnull=True).select_related("work")]
        data["excluded"] = [{"id": w.pk, "action_key": w.action_key, "scope": w.scope, "title": w.rules.order_by("-pk").first().title if w.rules.exists() else w.action_key} for w in item.works.filter(merged_into=None).exclude(excluded_at=None)]
        plan = item.plans.filter(status="active").first() or item.plans.filter(status="pending").first()
        if plan:
            data["plan"] = _plan_json(plan)
    return data


def _rule_json(r):
    return {"id": r.pk, "title": r.title, "category": r.category, "instructions": r.instructions,
        "cadence": r.cadence, "start_month": r.start_month, "end_month": r.end_month,
        "conditional": r.conditional, "confidence": r.confidence, "source_validated": r.source_validated,
        "source_urls": r.source_urls, "work_id": r.work_id, "action_key": r.work.action_key if r.work else "",
        "scope": r.work.scope if r.work else "", "advice_kind": r.advice_kind,
        "relevance_reason": r.relevance_reason, "need_condition": r.need_condition,
        "evidence_conflict": r.evidence_conflict, "identity_source_id": r.identity_source_id,
        "identity_change_kind": r.identity_change_kind,
        "one_off_date": str(r.one_off_date or ""), "one_off_end": str(r.one_off_end or ""),
        "item": {"id": r.item_id, "name": r.item.name},
        "works": [{"id": w.pk, "scope": w.scope, "title": w.rules.order_by("-pk").first().title if w.rules.exists() else w.action_key} for w in r.item.works.filter(merged_into=None)]}


def _plan_json(plan):
    proposal = getattr(plan, "proposal", None)
    return {
        "id": plan.pk, "version": plan.version, "status": plan.status, "summary": plan.summary,
        "warnings": plan.warnings, "uncertainties": plan.uncertainties,
        "proposal_id": proposal.pk if proposal else None,
        "sources": [{"title": s.title, "url": s.url, "domain": s.domain} for s in plan.sources.all()],
        "comparison": plan_comparison(plan) if plan.status == "pending" else None,
        "rules": [_rule_json(r) for r in plan.rules.select_related("work").all()],
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
    day = timezone.localdate()
    board = dashboard_for(day)
    completed = board.pop("completed")
    task_groups = {key: [_task_json(t) for t in value] for key, value in board.items()}
    total = completed + sum(len(v) for v in task_groups.values())
    settings = GardenSettings.load()
    return JsonResponse({
        "today": day.isoformat(), "month_name": MONTHS[day.month - 1], "completed": completed,
        "total": total, "progress": round(completed * 100 / total) if total else 0,
        "tasks": task_groups, "items": [_item_json(i) for i in GardenItem.objects.filter(active=True).select_related("area")],
        "areas": [{"id": area.pk, "name": area.name, "item_count": area.items.filter(active=True).count()} for area in GardenArea.objects.all()],
        "work_categories": list(WORK_CATEGORIES),
        "advice": [_rule_json(r) for r in CareRule.objects.filter(active=True, item__active=True, advice_kind="on_demand", work__excluded_at__isnull=True).select_related("work", "item")],
        "settings": {"garden_name": settings.garden_name, "city": settings.city, "cultivation_zone": settings.cultivation_zone, "exposure": settings.exposure},
        "pending_proposals": ResearchProposal.objects.filter(status="pending").count(),
        "year": [{"month": m, "name": MONTHS[m-1], "open": visible_pending().filter( window_start__lte=month_end(day.year, m), window_end__gte=date(day.year, m, 1)).count()} for m in range(1, 13)],
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
        area=GardenArea.objects.filter(pk=data.get("area_id")).first() if data.get("area_id") else None,
        location=data.get("location_detail", data.get("location", "")), notes=data.get("notes", ""),
    )
    response = {"item": _item_json(item)}
    return JsonResponse(response, status=201)


@require_http_methods(["GET", "PATCH"])
def api_item(request, item_id):
    item = get_object_or_404(GardenItem, pk=item_id, active=True)
    if request.method == "GET":
        return JsonResponse({"item": _item_json(item, True), "proposals": [_plan_json(p.plan) for p in item.proposals.filter(status="pending").order_by("-plan__version")]})
    data = _json_body(request) or {}
    if "area_id" in data:
        area_id = data.get("area_id")
        if area_id and not GardenArea.objects.filter(pk=area_id).exists():
            return JsonResponse({"error": "Området finns inte."}, status=400)
        item.area_id = area_id or None
    if "location_detail" in data:
        data["location"] = data["location_detail"]
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
    proposal = get_object_or_404(ResearchProposal, pk=proposal_id)
    data = _json_body(request) or {}
    try:
        selected = approve_proposal(proposal, [int(v) for v in data.get("rule_ids", [])], data.get("comparison_token"), data.get("resolutions"))
    except (ResearchError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=409)
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
    if end < start:
        return JsonResponse({"error": "Slutdatum måste vara efter startdatum."}, status=400)
    category = data.get("category", "Övrigt")
    if category not in WORK_CATEGORIES:
        return JsonResponse({"error": "Välj en giltig arbetskategori."}, status=400)
    task = TaskOccurrence.objects.create(
        item=item, title=data.get("title", "Egen uppgift").strip(), instructions=data.get("instructions", ""),
        category=category,
        occurrence_key=f"manual:{timezone.now().timestamp()}:{item.pk}", season_year=start.year,
        occurrence_month=start.month, window_start=start, window_end=end, manual=True,
    )
    return JsonResponse({"task": _task_json(task)}, status=201)


@require_http_methods(["GET", "PATCH"])
@transaction.atomic
def api_task(request, task_id):
    task = get_object_or_404(TaskOccurrence.objects.select_related("item", "item__area", "rule"), pk=task_id)
    if request.method == "GET":
        return JsonResponse({"task": _task_json(task)})
    GardenItem.objects.filter(pk=task.item_id).update(active=F("active"))
    task.refresh_from_db()
    data = _json_body(request) or {}
    status = data.get("status")
    if task.status == "archived" and status:
        return JsonResponse({"error": "Arkiverade tillfällen bevaras som historik."}, status=409)
    if status == "pending" and (task.archive_reason or (task.work_id and task.work.excluded_at)):
        return JsonResponse({"error": "Arkiverade eller bortvalda arbeten kan inte återöppnas här."}, status=409)
    if status == "pending" and task.work_id and task.rule and task.rule.advice_kind == "on_demand" and task.work.occurrences.filter(status="pending").exclude(pk=task.pk).exists():
        return JsonResponse({"error": "Ett senare behov är redan öppet för arbetet."}, status=409)
    if status in {"pending", "completed", "skipped"}:
        task.status = status
        task.completed_at = timezone.now() if status == "completed" else None
        task.skipped_at = timezone.now() if status == "skipped" else None
    for field in ["title", "instructions", "note"]:
        if field in data:
            setattr(task, field, data[field])
    if "category" in data:
        if data["category"] not in WORK_CATEGORIES:
            return JsonResponse({"error": "Välj en giltig arbetskategori."}, status=400)
        task.category = data["category"]
    task.save()
    return JsonResponse({"task": _task_json(task)})


@require_http_methods(["PATCH"])
@transaction.atomic
def api_rule(request, rule_id):
    rule = get_object_or_404(CareRule, pk=rule_id, plan__status="pending")
    data = _json_body(request) or {}
    try:
        with transaction.atomic():
            for field in ["title", "category", "instructions", "cadence", "start_month", "end_month", "advice_kind", "relevance_reason", "need_condition", "conditional", "source_urls", "evidence_conflict"]:
                if field in data:
                    setattr(rule, field, data[field])
            for field in ["one_off_date", "one_off_end"]:
                if field in data:
                    setattr(rule, field, date.fromisoformat(data[field]) if data[field] else None)
            original = rule.identity_source or rule.work
            mode = data.get("identity_mode")
            if mode is None:
                mode = "existing"
            if mode not in {"existing", "refine", "merge", "new"}:
                raise CareValidationError("Välj hur arbetsidentiteten ska hanteras.")
            chosen = None
            if mode != "new":
                chosen = WorkIdentity.objects.filter(pk=data.get("work_id", rule.work_id), item=rule.item, merged_into=None).first()
                if not chosen:
                    raise CareValidationError("Välj ett aktivt arbete på samma växt.")
            if mode == "existing":
                target, identity_source = chosen, None
            elif mode == "refine":
                scope = canonical_scope(str(data.get("scope", "")))
                if not scope or scope == canonical_scope(chosen.scope):
                    raise CareValidationError("Ange en ny, tydligare undergrupp.")
                target, _ = WorkIdentity.objects.get_or_create(item=rule.item, action_key=chosen.action_key, scope=scope)
                identity_source = chosen
            elif mode == "merge":
                if not original or original.pk == chosen.pk:
                    raise CareValidationError("Välj ett annat befintligt arbete att slå ihop med.")
                target, identity_source = chosen, original
            else:
                from uuid import uuid4
                scope = canonical_scope(str(data.get("scope", "")))
                target = WorkIdentity.objects.create(item=rule.item, action_key=f"manual-{uuid4().hex}", scope=scope)
                identity_source = None
            action, scope = target.action_key, canonical_scope(target.scope)
            import re
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", action) or not scope or len(scope) > 160:
                raise CareValidationError("Ange en arbetsnyckel och berörd undergrupp.")
            rule.work, rule.identity_source = target, identity_source
            rule.identity_change_kind = mode if mode in {"refine", "merge"} else ""
            if type(rule.conditional) is not bool or type(rule.evidence_conflict) is not bool:
                raise CareValidationError("Villkor och källkonflikt måste vara ja eller nej.")
            if not isinstance(rule.source_urls, list) or any(not isinstance(u, str) for u in rule.source_urls):
                raise CareValidationError("Kontrollera källorna.")
            consulted = set(rule.plan.sources.values_list("url", flat=True))
            # Cleanup proposals retain the original already verified source list.
            if rule.plan.source_type == "cleanup":
                consulted.update(CareRule.objects.get(pk=rule.pk).source_urls)
            rule.source_validated = bool(rule.source_urls) and all(u.rstrip('/') in {x.rstrip('/') for x in consulted} for u in rule.source_urls)
            from .research import _domain, SWEDISH_AUTHORITY_DOMAINS
            chemical = any(w in (rule.title + " " + rule.instructions).lower() for w in ["bekämpningsmedel", "fungicid", "insekticid", "pesticid", "kemisk"])
            if chemical and not any(_domain(u) in SWEDISH_AUTHORITY_DOMAINS for u in rule.source_urls):
                rule.source_validated = False
            validate_rule(rule)
            rule.save()
    except (CareValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "rule": _rule_json(rule), "comparison": plan_comparison(rule.plan)})


@require_GET
def api_proposals(request):
    return JsonResponse({"proposals": [{"item": {"id": p.item_id, "name": p.item.name}, "plan": _plan_json(p.plan)} for p in ResearchProposal.objects.filter(status="pending").select_related("item", "plan")]})


@require_GET
def api_month(request):
    try:
        year = int(request.GET.get("year", timezone.localdate().year))
        month = int(request.GET.get("month", timezone.localdate().month))
        first, last = date(year, month, 1), month_end(year, month)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Välj ett giltigt år och en månad."}, status=400)
    tasks = TaskOccurrence.objects.filter(item__active=True).select_related("item", "item__area", "rule", "work")
    return JsonResponse({"year": year, "month": month,
        "counts": [{"month": m, "open": tasks.filter(status="pending", archive_reason="", work__excluded_at__isnull=True, window_start__lte=month_end(year,m), window_end__gte=date(year,m,1)).count()} for m in range(1,13)],
        "planned": [_task_json(t) for t in tasks.filter(status="pending", archive_reason="", work__excluded_at__isnull=True, window_start__lte=last, window_end__gte=first)],
        "history": [_task_json(t) for t in tasks.exclude(status="pending").filter(Q(completed_at__date__range=(first,last)) | Q(skipped_at__date__range=(first,last)) | Q(archived_at__date__range=(first,last)))]})


@require_POST
def api_need(request, work_id):
    get_object_or_404(WorkIdentity, pk=work_id, merged_into=None)
    try:
        task, created = needs_now(work_id)
    except CareValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse({"task": _task_json(task), "created": created}, status=201 if created else 200)


@require_http_methods(["PATCH"])
def api_work(request, work_id):
    get_object_or_404(WorkIdentity, pk=work_id, merged_into=None)
    data = _json_body(request) or {}
    if type(data.get("excluded")) is not bool:
        return JsonResponse({"error": "Ange om arbetet ska vara bortvalt."}, status=400)
    work = set_excluded(work_id, data["excluded"])
    return JsonResponse({"ok": True, "excluded": bool(work.excluded_at)})


@require_http_methods(["GET", "POST"])
def api_areas(request):
    if request.method == "GET":
        return JsonResponse({"areas": [{"id": area.pk, "name": area.name, "item_count": area.items.filter(active=True).count()} for area in GardenArea.objects.all()]})
    data = _json_body(request) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return JsonResponse({"error": "Områdesnamn krävs."}, status=400)
    if GardenArea.objects.filter(name__iexact=name).exists():
        return JsonResponse({"error": "Området finns redan."}, status=400)
    try:
        area = GardenArea.objects.create(name=name)
    except IntegrityError:
        return JsonResponse({"error": "Området finns redan."}, status=400)
    return JsonResponse({"area": {"id": area.pk, "name": area.name, "item_count": 0}}, status=201)


@require_http_methods(["PATCH", "DELETE"])
def api_area(request, area_id):
    area = get_object_or_404(GardenArea, pk=area_id)
    if request.method == "DELETE":
        area.delete()
        return JsonResponse({"ok": True})
    data = _json_body(request) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return JsonResponse({"error": "Områdesnamn krävs."}, status=400)
    if GardenArea.objects.filter(name__iexact=name).exclude(pk=area.pk).exists():
        return JsonResponse({"error": "Området finns redan."}, status=400)
    area.name = name
    area.save(update_fields=["name", "updated_at"])
    return JsonResponse({"area": {"id": area.pk, "name": area.name, "item_count": area.items.filter(active=True).count()}})


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
