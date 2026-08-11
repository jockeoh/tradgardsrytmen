from django.db import migrations


def remove_empty_seed_duplicate(apps, schema_editor):
    GardenItem = apps.get_model("garden", "GardenItem")
    if not GardenItem.objects.filter(name="Tomat", canonical_name="Tomat", active=True).exists():
        return
    duplicates = GardenItem.objects.filter(
        name="Tomater", canonical_name="Tomat", category="Köksväxter", kind="bed",
        cultivar="", quantity=1, age_stage="Sommarodling", location="", notes="",
        icon="tomato", active=True, area__isnull=True, tasks__isnull=True,
        plans__isnull=True, proposals__isnull=True,
    )
    if duplicates.count() == 1:
        duplicates.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("garden", "0005_remove_empty_seed_duplicate"),
    ]

    operations = [
        migrations.RunPython(remove_empty_seed_duplicate, migrations.RunPython.noop),
    ]
