from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("garden", "0009_legacy_work_identities")]
    operations = [
        migrations.AddField(
            model_name="workidentity",
            name="merged_into",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="merged_identities", to="garden.workidentity"),
        ),
        migrations.AddField(
            model_name="carerule",
            name="identity_source",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="refinement_rules", to="garden.workidentity"),
        ),
        migrations.AddField(
            model_name="carerule",
            name="identity_change_kind",
            field=models.CharField(blank=True, max_length=12),
        ),
    ]
