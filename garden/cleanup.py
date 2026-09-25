"""Conservative inventory/cleanup. No model calls, deletion or note edits."""
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from .models import CareRule, CarePlanVersion, ResearchProposal, TaskOccurrence, WorkIdentity, GardenItem
from .care_contract import normalized, overlaps
from .tasks import archive_task


@transaction.atomic
def clean_existing_content(garden, apply=False, queue=True):
    tasks_qs = TaskOccurrence.objects.filter(item__garden=garden)
    items_qs = GardenItem.objects.filter(garden=garden)
    rules_qs = CareRule.objects.filter(item__garden=garden)
    works_qs = WorkIdentity.objects.filter(item__garden=garden)
    report = {'date': str(timezone.localdate()), 'garden_id': str(garden.public_id), 'applied': apply, 'tasks_scanned': tasks_qs.count(),
              'expired': [], 'duplicates': [], 'review_items': [], 'queued_proposals': [], 'possible_overlaps': [],
              'items_scanned': items_qs.count(), 'rules_scanned': rules_qs.count(), 'works_scanned': works_qs.count(),
              'task_status_counts': {status: tasks_qs.filter(status=status).count() for status in ['pending','completed','skipped','archived']},
              'manual_tasks': tasks_qs.filter(manual=True).count(),
              'legacy_rules': list(rules_qs.filter(advice_kind='review').values_list('pk',flat=True))}
    seen_pending = {}
    # Separate completed/skipped need requests are real history. Only concurrent
    # open snapshots can be automatic duplicates of one another.
    tasks = list(tasks_qs.filter(manual=False).select_related('rule', 'work').order_by('created_at', 'pk'))
    tasks.sort(key=lambda t: (t.status == 'pending', t.pk))
    for task in tasks:
        if task.status == 'archived' or task.archive_reason:
            continue
        # Only exact snapshots qualify, never just matching titles/categories.
        signature = (task.item_id, task.work.scope if task.work else 'okänd', normalized(task.title), normalized(task.instructions), task.window_start, task.window_end)
        if task.status == 'pending' and task.window_end < timezone.localdate():
            report['expired'].append(task.pk)
            if apply:
                archive_task(task, 'Passerat automatiskt tidsfönster')
        elif task.status == 'pending' and signature in seen_pending:
            report['duplicates'].append({'id': task.pk, 'retained_id': seen_pending[signature]})
            if apply:
                archive_task(task, f'Entydig automatisk dubblett av tillfälle {seen_pending[signature]}')
        elif task.status == 'pending':
            seen_pending.setdefault(signature, task.pk)
    rules = list(rules_qs.filter(active=True).select_related('work').order_by('pk'))
    review_items = {r.item_id for r in rules if r.advice_kind == 'review'}
    for index, rule in enumerate(rules):
        for other in rules[index+1:]:
            if other.item_id != rule.item_id or not overlaps(rule, other):
                continue
            proposal = ResearchProposal.objects.filter(plan_id=rule.plan_id, status='approved').first() if rule.plan_id == other.plan_id else None
            resolutions = proposal.review_receipt.get('resolutions', {}) if proposal else {}
            if not (resolutions.get(str(rule.pk)) and resolutions.get(str(other.pk))):
                report['possible_overlaps'].append({'item_id': rule.item_id, 'rule_ids': [rule.pk,other.pk], 'titles': [rule.title,other.title]})
                review_items.add(rule.item_id)
    report['review_items'] = sorted(review_items)
    if apply and queue:
        for item_id in sorted(review_items):
            if ResearchProposal.objects.filter(item__garden=garden, item_id=item_id, status='pending').exists():
                continue
            version = (CarePlanVersion.objects.filter(item_id=item_id).aggregate(v=Max('version'))['v'] or 0) + 1
            plan = CarePlanVersion.objects.create(item_id=item_id, version=version, source_type='cleanup',
                summary='Granska befintliga råd: klassificera relevans och berörd undergrupp, och lös möjliga överlapp.')
            for rule in [r for r in rules if r.item_id == item_id]:
                source_pk = rule.pk
                rule.pk = None
                rule.plan = plan
                rule.active = False
                rule.save()
                rule.pk = source_pk
            proposal = ResearchProposal.objects.create(item_id=item_id, plan=plan)
            report['queued_proposals'].append(proposal.pk)
    return report
