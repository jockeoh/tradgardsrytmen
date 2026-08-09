import calendar
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from .models import CareRule, TaskOccurrence


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
        if rule.one_off_date:
            if season_year != rule.one_off_date.year:
                return []
            when = rule.one_off_date
        else:
            today = timezone.localdate()
            target_year = today.year + int(rule.start_month < today.month)
            if season_year != target_year:
                return []
            when = date(target_year, rule.start_month, min(rule.reminder_day, 28))
        return [(when.month, when, when)]
    months = months_for_season(rule, season_year)
    if rule.cadence == "seasonal":
        first_y, first_m = months[0]
        last_y, last_m = months[-1]
        return [(first_m, date(first_y, first_m, 1), month_end(last_y, last_m))]
    return [(m, date(y, m, 1), month_end(y, m)) for y, m in months]


@transaction.atomic
def materialize_rule(rule, through_year=None, not_before=None):
    today = timezone.localdate()
    through_year = through_year or today.year + 1
    start_year = today.year - 1
    created = []
    for season_year in range(start_year, through_year + 1):
        for position, (month, window_start, window_end) in enumerate(occurrence_specs(rule, season_year)):
            if window_end < today:
                continue
            if not_before and window_start < not_before:
                continue
            key = f"rule:{rule.pk}:season:{season_year}:slot:{position}:{window_start.isoformat()}"
            occurrence, was_created = TaskOccurrence.objects.get_or_create(
                occurrence_key=key,
                defaults={
                    "rule": rule, "item": rule.item, "title": rule.title,
                    "instructions": rule.instructions, "season_year": season_year,
                    "occurrence_month": month, "window_start": window_start,
                    "window_end": window_end,
                },
            )
            if was_created:
                created.append(occurrence)
    return created


@transaction.atomic
def archive_pre_activation_backlog():
    """Keep newly approved plans forward-looking without deleting task history."""
    archived_at = timezone.now()
    archived = 0
    tasks = TaskOccurrence.objects.filter(
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
        task.save(update_fields=["status", "skipped_at", "note", "updated_at"])
        archived += 1
    return archived


def materialize_active_rules():
    archive_pre_activation_backlog()
    total = 0
    for rule in CareRule.objects.filter(active=True).select_related("item"):
        total += len(materialize_rule(rule))
    return total


def replace_future_tasks(item, old_rules, first_future_month):
    TaskOccurrence.objects.filter(
        item=item, rule__in=old_rules, status="pending", window_start__gte=first_future_month
    ).delete()


def dashboard_for(day=None):
    day = day or timezone.localdate()
    first = day.replace(day=1)
    last = month_end(day.year, day.month)
    pending = TaskOccurrence.objects.filter(status="pending").select_related("item", "rule")
    return {
        "overdue": pending.filter(window_end__lt=first),
        "due": pending.filter(window_start__lte=day, window_end__gte=first),
        "later": pending.filter(window_start__gt=day, window_start__lte=last),
        "completed": TaskOccurrence.objects.filter(status="completed", completed_at__date__gte=first, completed_at__date__lte=last).count(),
    }
