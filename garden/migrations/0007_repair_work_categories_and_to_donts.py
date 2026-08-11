from django.db import migrations
from django.utils import timezone


WORK_CATEGORIES = {
    "Vattna", "Beskära och binda upp", "Kontrollera", "Gödsla",
    "Jord och ogräs", "Skörda", "Övrigt",
}
TO_DONT_PREFIXES = ("avstå", "undvik", "använd inte", "behandla inte", "ta inte", "gör inte", "låt bli", "ingen")


def suggested_category(title):
    text = (title or "").strip().casefold()
    if text.startswith(("kontrollera", "inspektera", "sommarinspektera", "följ ", "inventera", "övervaka")):
        return "Kontrollera"
    if text.startswith("bedöm"):
        return "Gödsla" if any(word in text for word in ("göd", "näring")) else "Kontrollera"
    if any(word in text for word in ("göd", "näring")):
        return "Gödsla"
    if any(word in text for word in ("jord", "ogräs", "marktäck", "luckra")):
        return "Jord och ogräs"
    if text.startswith(("vattna", "bevattna")) or " ge vatten" in f" {text}":
        return "Vattna"
    if any(word in text for word in ("beskär", "gallra", "bind upp", "klipp")):
        return "Beskära och binda upp"
    if any(word in text for word in ("skörda", "plocka")):
        return "Skörda"
    return None


def fallback_category(value, instructions):
    if value in WORK_CATEGORIES:
        return value
    text = f"{value or ''} {instructions or ''}".casefold()
    mappings = (
        ("Kontrollera", ("kontroll", "inspek", "inventera", "övervaka", "bedöm", "växtskydd", "sjuk", "skadedjur")),
        ("Vattna", ("vatt", "bevatt")),
        ("Gödsla", ("göd", "näring", "npk")),
        ("Jord och ogräs", ("jord", "ogräs", "luckra", "marktäck", "kompost")),
        ("Beskära och binda upp", ("beskär", "gallra", "bind", "stötta", "klipp", "skott")),
        ("Skörda", ("skörd", "plocka", "frukt", "bär")),
    )
    for category, needles in mappings:
        if any(needle in text for needle in needles):
            return category
    return "Övrigt"


def repair_categories(apps, schema_editor):
    CareRule = apps.get_model("garden", "CareRule")
    TaskOccurrence = apps.get_model("garden", "TaskOccurrence")
    skipped_at = timezone.now()
    for rule in CareRule.objects.all().iterator():
        title = rule.title.strip().casefold()
        if rule.active and title.startswith(TO_DONT_PREFIXES):
            rule.active = False
            rule.save(update_fields=["active"])
            for task in TaskOccurrence.objects.filter(rule=rule, status="pending"):
                task.status = "skipped"
                task.skipped_at = skipped_at
                if not task.note:
                    task.note = "Automatiskt undanlagd: ett icke-göra-råd ska finnas i skötselrådet, inte som uppgift."
                task.save(update_fields=["status", "skipped_at", "note"])
            continue
        category = suggested_category(rule.title) or fallback_category(rule.category, rule.instructions)
        if rule.category != category:
            rule.category = category
            rule.save(update_fields=["category"])
        TaskOccurrence.objects.filter(rule=rule, status="pending").update(category=category)


class Migration(migrations.Migration):

    dependencies = [
        ("garden", "0006_remove_recreated_seed_duplicate"),
    ]

    operations = [
        migrations.RunPython(repair_categories, migrations.RunPython.noop),
    ]
