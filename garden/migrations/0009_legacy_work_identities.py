from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    Rule = apps.get_model('garden', 'CareRule')
    Work = apps.get_model('garden', 'WorkIdentity')
    Task = apps.get_model('garden', 'TaskOccurrence')
    Plan = apps.get_model('garden', 'CarePlanVersion')
    for rule in Rule.objects.order_by('pk').iterator():
        # Never infer subgroup or semantics from old prose. Cleanup queues review.
        work = Work.objects.create(item_id=rule.item_id, action_key=f'legacy-{rule.pk}', scope='okänd')
        rule.work_id = work.pk
        rule.advice_kind = 'review'
        rule.save(update_fields=['work', 'advice_kind'])
        Task.objects.filter(rule_id=rule.pk, manual=False).update(work_id=work.pk)
    for plan in Plan.objects.exclude(reviewed_at=None).iterator():
        plan.effective_from = timezone.localtime(plan.reviewed_at).date()
        plan.save(update_fields=['effective_from'])


class Migration(migrations.Migration):
    dependencies = [('garden', '0008_careplanversion_effective_from_and_more')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
