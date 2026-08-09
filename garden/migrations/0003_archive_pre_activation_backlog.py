from django.db import migrations
from django.utils import timezone


def archive_pre_activation_backlog(apps, schema_editor):
    TaskOccurrence = apps.get_model("garden", "TaskOccurrence")
    archived_at = timezone.now()
    tasks = TaskOccurrence.objects.filter(
        status="pending", manual=False, rule__plan__reviewed_at__isnull=False
    ).select_related("rule__plan")
    for task in tasks:
        if task.window_end >= timezone.localtime(task.rule.plan.reviewed_at).date():
            continue
        task.status = "skipped"
        task.skipped_at = archived_at
        if not task.note:
            task.note = "Automatiskt undanlagd: uppgiften skapades från ett kalenderfönster före planens godkännande."
        task.save(update_fields=["status", "skipped_at", "note"])


class Migration(migrations.Migration):

    dependencies = [
        ("garden", "0002_alter_researchproposal_status"),
    ]

    operations = [
        migrations.RunPython(archive_pre_activation_backlog, migrations.RunPython.noop),
    ]
