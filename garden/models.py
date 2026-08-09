from django.db import models
from django.utils import timezone


class GardenSettings(models.Model):
    garden_name = models.CharField(max_length=120, default="Vår trädgård")
    city = models.CharField(max_length=80, default="Karlskrona")
    cultivation_zone = models.CharField(max_length=20, default="1")
    exposure = models.CharField(max_length=160, default="Skyddat, kustnära läge")
    timezone = models.CharField(max_length=64, default="Europe/Stockholm")
    monthly_digest_day = models.PositiveSmallIntegerField(default=1)
    reminder_weekday = models.PositiveSmallIntegerField(default=6)
    reminder_hour = models.PositiveSmallIntegerField(default=9)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class GardenItem(models.Model):
    INDIVIDUAL = "individual"
    GROUP = "group"
    BED = "bed"
    KIND_CHOICES = [(INDIVIDUAL, "Enskild växt"), (GROUP, "Grupp"), (BED, "Odlingsbädd")]
    name = models.CharField(max_length=120)
    canonical_name = models.CharField(max_length=120, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=80, blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=INDIVIDUAL)
    cultivar = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    age_stage = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    icon = models.CharField(max_length=20, default="leaf")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]


class CarePlanVersion(models.Model):
    STATUS_CHOICES = [("pending", "Väntar på granskning"), ("active", "Aktiv"), ("superseded", "Ersatt"), ("rejected", "Avvisad"), ("failed", "Misslyckad")]
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="plans")
    version = models.PositiveIntegerField(default=1)
    summary = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True)
    uncertainties = models.JSONField(default=list, blank=True)
    source_type = models.CharField(max_length=20, default="ai")
    model_name = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["item", "version"], name="unique_plan_version")]


class SourceReference(models.Model):
    plan = models.ForeignKey(CarePlanVersion, on_delete=models.CASCADE, related_name="sources")
    title = models.CharField(max_length=300)
    url = models.URLField(max_length=1000)
    domain = models.CharField(max_length=160, blank=True)
    summary = models.TextField(blank=True)
    accessed_at = models.DateTimeField(default=timezone.now)
    is_swedish_authority = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "url"], name="unique_plan_source")]


class CareRule(models.Model):
    CADENCE_CHOICES = [("one_off", "Engångsuppgift"), ("seasonal", "En gång per säsong"), ("monthly", "Varje månad i fönstret")]
    CONFIDENCE_CHOICES = [("high", "Hög"), ("medium", "Medel"), ("low", "Låg")]
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="care_rules")
    plan = models.ForeignKey(CarePlanVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="rules")
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, blank=True)
    instructions = models.TextField(blank=True)
    cadence = models.CharField(max_length=20, choices=CADENCE_CHOICES, default="seasonal")
    start_month = models.PositiveSmallIntegerField(default=1)
    end_month = models.PositiveSmallIntegerField(default=1)
    one_off_date = models.DateField(null=True, blank=True)
    conditional = models.BooleanField(default=False)
    confidence = models.CharField(max_length=12, choices=CONFIDENCE_CHOICES, default="medium")
    source_urls = models.JSONField(default=list, blank=True)
    source_validated = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    reminder_day = models.PositiveSmallIntegerField(default=8)
    created_at = models.DateTimeField(auto_now_add=True)


class ResearchProposal(models.Model):
    STATUS_CHOICES = [("pending", "Väntar"), ("approved", "Godkänd"), ("rejected", "Avvisad"), ("failed", "Misslyckad")]
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="proposals")
    plan = models.OneToOneField(CarePlanVersion, on_delete=models.CASCADE, related_name="proposal")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    response_id = models.CharField(max_length=120, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class TaskOccurrence(models.Model):
    STATUS_CHOICES = [("pending", "Öppen"), ("completed", "Klar"), ("skipped", "Hoppad över")]
    rule = models.ForeignKey(CareRule, on_delete=models.CASCADE, null=True, blank=True, related_name="occurrences")
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=180)
    instructions = models.TextField(blank=True)
    occurrence_key = models.CharField(max_length=220, unique=True)
    season_year = models.PositiveIntegerField()
    occurrence_month = models.PositiveSmallIntegerField()
    window_start = models.DateField()
    window_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    manual = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    skipped_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["window_end", "window_start", "title"]
        indexes = [models.Index(fields=["status", "window_start", "window_end"]), models.Index(fields=["item", "occurrence_month"])]


class PushSubscription(models.Model):
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=500)
    auth = models.CharField(max_length=500)
    device_name = models.CharField(max_length=120, blank=True)
    monthly_digest = models.BooleanField(default=False)
    task_reminders = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ReminderDelivery(models.Model):
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE, related_name="deliveries")
    occurrence = models.ForeignKey(TaskOccurrence, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=30)
    delivery_key = models.CharField(max_length=240, unique=True)
    scheduled_for = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="pending")
    error = models.TextField(blank=True)

