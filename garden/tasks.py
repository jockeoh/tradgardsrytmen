import calendar
from datetime import date
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import CareRule, TaskOccurrence, WorkIdentity
from .work_categories import normalize_work_category


def month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(day, count):
    month_index = day.year * 12 + day.month - 1 + count
    return date(month_index // 12, month_index % 12 + 1, 1)


def months_for_season(rule, season_year):
    months = []
    month = rule.start_month
    year = season_year
    while True:
        months.append((year, month))
        if month == rule.end_month:
            return months
        month += 1
        if month == 13:
            month = 1
            year += 1
        if len(months) > 12:
            raise ValueError("Säsongsfönster får vara högst tolv månader")


def occurrence_specs(rule, season_year):
    if rule.cadence == "one_off":
        if not rule.one_off_date or not rule.one_off_end or season_year != rule.one_off_date.year:
            return []
        return [(rule.one_off_date.month, rule.one_off_date, rule.one_off_end)]
    months = months_for_season(rule, season_year)
    if rule.cadence == "seasonal":
        first_y, first_m = months[0]
        last_y, last_m = months[-1]
        return [(first_m, date(first_y, first_m, 1), month_end(last_y, last_m))]
    return [(m, date(y, m, 1), month_end(y, m)) for y, m in months]


@transaction.atomic
def materialize_rule(rule, through_year=None, not_before=None):
    today = timezone.localdate()
    if rule.work_id:
        WorkIdentity.objects.filter(pk=rule.work_id).update(updated_at=timezone.now())
        rule.refresh_from_db()
    if not rule.active or rule.advice_kind != "planned" or (rule.work_id and rule.work.excluded_at):
        return []
    if not rule.work_id:
        # Compatibility for explicit local/manual rule creation; legacy records
        # receive identities in the data migration and require classification.
        rule.work, _ = WorkIdentity.objects.get_or_create(item=rule.item, action_key=f"legacy-{rule.pk}", scope="okänd")
        rule.save(update_fields=["work"])
    not_before = not_before or (rule.plan.effective_from if rule.plan_id else None)
    through_year = through_year or today.year + 1
    start_year = today.year - 1
    created = []
    for season_year in range(start_year, through_year + 1):
        for month, window_start, window_end in occurrence_specs(rule, season_year):
            if window_end < today:
                continue
            if not_before and window_end < not_before:
                continue
            key = slot_key(rule, season_year, window_start)
            historical = TaskOccurrence.objects.filter(work=rule.work, manual=False, archive_reason="", season_year=season_year)
            if rule.cadence == "monthly":
                historical = historical.filter(window_start__year=window_start.year, occurrence_month=month)
            elif rule.cadence == "one_off":
                historical = historical.filter(window_start__lte=window_end, window_end__gte=window_start)
            previous = historical.filter(status__in=["pending", "completed", "skipped"]).first()
            if previous:
                if previous.status == "pending" and previous.rule_id != rule.pk:
                    previous.rule = rule
                    previous.title, previous.instructions = rule.title, rule.instructions
                    previous.category = rule.category
                    previous.window_start, previous.window_end = window_start, window_end
                    previous.version += 1
                    previous.save(update_fields=["rule", "title", "instructions", "category", "window_start", "window_end", "version", "updated_at"])
                continue
            occurrence, was_created = TaskOccurrence.objects.get_or_create(
                identity_slot=key,
                defaults={
                    "rule": rule, "work": rule.work, "occurrence_key": key, "item": rule.item, "title": rule.title,
                    "category": normalize_work_category(rule.category, rule.title, rule.instructions),
                    "instructions": rule.instructions, "season_year": season_year,
                    "occurrence_month": month, "window_start": window_start,
                    "window_end": window_end,
                },
            )
            if not was_created and occurrence.status == "archived" and (occurrence.archive_reason.startswith("Ersatt vid godkännande") or occurrence.archive_reason == "Bortvalt: inte relevant här"):
                occurrence.rule, occurrence.status = rule, "pending"
                occurrence.title, occurrence.instructions = rule.title, rule.instructions
                occurrence.window_start, occurrence.window_end = window_start, window_end
                occurrence.category = rule.category
                occurrence.archive_reason, occurrence.archived_at = "", None
                occurrence.version += 1
                occurrence.save()
            if was_created:
                created.append(occurrence)
    return created


@transaction.atomic
def archive_pre_activation_backlog(garden):
    """Keep newly approved plans forward-looking without deleting task history."""
    archived_at = timezone.now()
    archived = 0
    tasks = TaskOccurrence.objects.filter(
        item__garden=garden,
        status="pending", manual=False, rule__plan__reviewed_at__isnull=False
    ).select_related("rule__plan")
    for task in tasks:
        activated_on = timezone.localtime(task.rule.plan.reviewed_at).date()
        if task.window_end >= activated_on:
            continue
        task.status = "skipped"
        task.skipped_at = archived_at
        if not task.note:
            task.note = "Automatiskt undanlagd: uppgiften skapades från ett kalenderfönster före planens godkännande."
        task.version += 1
        task.save(update_fields=["status", "skipped_at", "note", "version", "updated_at"])
        archived += 1
    return archived


def slot_key(rule, season_year, window_start):
    recurrence = f"month:{window_start:%Y-%m}" if rule.cadence == "monthly" else f"once:{window_start}" if rule.cadence == "one_off" else f"season:{season_year}"
    return f"work:{rule.work_id}:{recurrence}"


def archive_task(task, reason):
    task.status = "archived"
    task.archive_reason = reason
    task.archived_at = timezone.now()
    task.version += 1
    task.save(update_fields=["status", "archive_reason", "archived_at", "version", "updated_at"])


def materialize_active_rules(garden):
    from .cleanup import clean_existing_content
    clean_existing_content(garden, apply=True, queue=False)
    return sum(len(materialize_rule(rule)) for rule in CareRule.objects.filter(item__garden=garden, active=True).select_related("item", "plan", "work"))


def visible_pending(garden, day=None):
    day = day or timezone.localdate()
    return TaskOccurrence.objects.filter(item__garden=garden, status="pending", item__active=True, archive_reason="").filter(
        Q(work__excluded_at__isnull=True)
    ).filter(Q(manual=True) | Q(window_end__gte=day)).select_related("item", "item__area", "rule", "work")


def dashboard_for(garden, day=None):
    day = day or timezone.localdate()
    first = day.replace(day=1)
    last = month_end(day.year, day.month)
    pending = visible_pending(garden, day)
    return {
        "overdue": pending.filter(manual=True, window_end__lt=day),
        "due": pending.filter(window_start__lte=day, window_end__gte=day),
        "later": pending.filter(window_start__gt=day, window_start__lte=add_months(first, 3)),
        "completed": TaskOccurrence.objects.filter(item__garden=garden, status="completed", completed_at__date__gte=first, completed_at__date__lte=last).count(),
    }


@transaction.atomic
def needs_now(garden, work_id):
    from .care_contract import CareValidationError
    # First statement is a write, serializing SQLite transactions as well as
    # locking the identity on databases supporting row-level locks.
    WorkIdentity.objects.filter(pk=work_id, item__garden=garden).update(updated_at=timezone.now())
    work = WorkIdentity.objects.get(pk=work_id, item__garden=garden)
    rule = work.rules.filter(active=True, advice_kind="on_demand").order_by('-pk').first()
    if work.excluded_at or not rule or not work.item.active:
        raise CareValidationError("Det finns inget aktivt behovsråd för arbetet.")
    previous = work.occurrences.filter(status="pending", archive_reason="").first()
    if previous:
        return previous, False
    from uuid import uuid4
    today = timezone.localdate()
    key = f"work:{work.pk}:need:{uuid4()}"
    return TaskOccurrence.objects.create(work=work, rule=rule, item=work.item, identity_slot=key,
        occurrence_key=key, title=rule.title, instructions=rule.instructions, category=rule.category,
        season_year=today.year, occurrence_month=today.month, window_start=today, window_end=month_end(today.year, today.month)), True


@transaction.atomic
def set_excluded(garden, work_id, excluded):
    WorkIdentity.objects.filter(pk=work_id, item__garden=garden).update(excluded_at=timezone.now() if excluded else None, updated_at=timezone.now())
    work = WorkIdentity.objects.get(pk=work_id, item__garden=garden)
    if excluded:
        for task in work.occurrences.filter(status="pending", manual=False):
            archive_task(task, "Bortvalt: inte relevant här")
    else:
        # Undo a suppression without creating a second occurrence or reviving
        # tasks archived for other reasons. Completed/skipped history stays put.
        active = list(work.rules.filter(active=True))
        if any(r.advice_kind == "on_demand" for r in active):
            task = work.occurrences.filter(status="archived", archive_reason="Bortvalt: inte relevant här", window_end__gte=timezone.localdate()).order_by('-created_at').first()
            if task and not work.occurrences.filter(status="pending").exists():
                task.status, task.archive_reason, task.archived_at = "pending", "", None
                task.rule = next(r for r in active if r.advice_kind == "on_demand")
                task.version += 1
                task.save(update_fields=["status", "rule", "archive_reason", "archived_at", "version", "updated_at"])
        for rule in active:
            # Includes legacy slots whose identity_slot predates the new model.
            for task in work.occurrences.filter(status="archived", archive_reason="Bortvalt: inte relevant här", rule=rule, identity_slot=None, window_end__gte=timezone.localdate()):
                task.status, task.archive_reason, task.archived_at = "pending", "", None
                task.version += 1
                task.save(update_fields=["status", "archive_reason", "archived_at", "version", "updated_at"])
            materialize_rule(rule)
    return work
