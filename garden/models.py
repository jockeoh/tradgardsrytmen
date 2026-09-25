from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from uuid import uuid4
from .work_categories import WORK_CATEGORY_CHOICES


class GardenSettings(models.Model):
    garden = models.OneToOneField("Garden", on_delete=models.PROTECT, null=True, blank=True, related_name="settings")
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
    def load(cls, garden=None):
        if garden is None:
            return cls.objects.filter(garden__isnull=True, pk=1).first() or cls(pk=1)
        return cls.objects.filter(garden=garden).first() or cls(garden=garden, garden_name=garden.name)


class GardenArea(models.Model):
    garden = models.ForeignKey("Garden", on_delete=models.PROTECT, null=True, blank=True, related_name="areas")
    name = models.CharField(max_length=80)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [models.UniqueConstraint(fields=["garden", "name"], name="unique_garden_area_name")]


class GardenItem(models.Model):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    garden = models.ForeignKey("Garden", on_delete=models.PROTECT, null=True, blank=True, related_name="items")
    version = models.PositiveIntegerField(default=1)
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
    area = models.ForeignKey(GardenArea, on_delete=models.SET_NULL, null=True, blank=True, related_name="items")
    location = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    icon = models.CharField(max_length=20, default="leaf")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.area_id and self.area.garden_id != self.garden_id:
            raise ValidationError("Området måste tillhöra samma trädgård som växten.")
        return super().save(*args, **kwargs)


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
    effective_from = models.DateField(null=True, blank=True)
    research_context = models.JSONField(default=dict, blank=True)

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


class WorkIdentity(models.Model):
    """Stable identity, shared by rule versions and all their occurrences."""
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="works")
    action_key = models.CharField(max_length=100)
    scope = models.CharField(max_length=160, default="hela-växten")
    excluded_at = models.DateTimeField(null=True, blank=True)
    merged_into = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="merged_identities")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "action_key", "scope"], name="unique_item_work_scope")]

    def save(self, *args, **kwargs):
        if self.merged_into_id and self.merged_into.item_id != self.item_id:
            raise ValidationError("Sammanslagna arbeten måste tillhöra samma växt.")
        return super().save(*args, **kwargs)


class CareRule(models.Model):
    ADVICE_CHOICES = [("planned", "Planerat arbete"), ("on_demand", "Vid behov"), ("general", "Allmänt råd"), ("review", "Kräver granskning")]
    work = models.ForeignKey(WorkIdentity, on_delete=models.PROTECT, null=True, blank=True, related_name="rules")
    identity_source = models.ForeignKey(WorkIdentity, on_delete=models.PROTECT, null=True, blank=True, related_name="refinement_rules")
    identity_change_kind = models.CharField(max_length=12, blank=True)
    advice_kind = models.CharField(max_length=20, choices=ADVICE_CHOICES, default="planned")
    relevance_reason = models.TextField(blank=True)
    need_condition = models.TextField(blank=True)
    evidence_conflict = models.BooleanField(default=False)
    one_off_end = models.DateField(null=True, blank=True)
    CADENCE_CHOICES = [("one_off", "Engångsuppgift"), ("seasonal", "En gång per säsong"), ("monthly", "Varje månad i fönstret")]
    CONFIDENCE_CHOICES = [("high", "Hög"), ("medium", "Medel"), ("low", "Låg")]
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="care_rules")
    plan = models.ForeignKey(CarePlanVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="rules")
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, choices=WORK_CATEGORY_CHOICES, default="Övrigt")
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

    def save(self, *args, **kwargs):
        for relation in ("plan", "work", "identity_source"):
            related_id = getattr(self, f"{relation}_id")
            if related_id and getattr(self, relation).item_id != self.item_id:
                raise ValidationError(f"{relation} måste tillhöra samma växt som skötselregeln.")
        return super().save(*args, **kwargs)


class ResearchProposal(models.Model):
    STATUS_CHOICES = [("pending", "Väntar"), ("approved", "Godkänd"), ("rejected", "Avvisad"), ("superseded", "Ersatt"), ("failed", "Misslyckad")]
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="proposals")
    plan = models.OneToOneField(CarePlanVersion, on_delete=models.CASCADE, related_name="proposal")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    response_id = models.CharField(max_length=120, blank=True)
    error = models.TextField(blank=True)
    review_receipt = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.plan_id and self.plan.item_id != self.item_id:
            raise ValidationError("Planen måste tillhöra samma växt som förslaget.")
        return super().save(*args, **kwargs)


class TaskOccurrence(models.Model):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    version = models.PositiveIntegerField(default=1)
    work = models.ForeignKey(WorkIdentity, on_delete=models.PROTECT, null=True, blank=True, related_name="occurrences")
    identity_slot = models.CharField(max_length=240, unique=True, null=True, blank=True)
    archive_reason = models.CharField(max_length=240, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    STATUS_CHOICES = [("pending", "Öppen"), ("completed", "Klar"), ("skipped", "Hoppad över"), ("archived", "Arkiverad")]
    rule = models.ForeignKey(CareRule, on_delete=models.CASCADE, null=True, blank=True, related_name="occurrences")
    item = models.ForeignKey(GardenItem, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, choices=WORK_CATEGORY_CHOICES, default="Övrigt")
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

    def save(self, *args, **kwargs):
        for relation in ("rule", "work"):
            related_id = getattr(self, f"{relation}_id")
            if related_id and getattr(self, relation).item_id != self.item_id:
                raise ValidationError(f"{relation} måste tillhöra samma växt som uppgiften.")
        return super().save(*args, **kwargs)


class PushSubscription(models.Model):
    garden = models.ForeignKey("Garden", on_delete=models.PROTECT, null=True, blank=True, related_name="push_subscriptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=500)
    auth = models.CharField(max_length=500)
    device_name = models.CharField(max_length=120, blank=True)
    monthly_digest = models.BooleanField(default=False)
    task_reminders = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.garden_id and self.user_id and not GardenMembership.objects.filter(garden_id=self.garden_id, user_id=self.user_id).exists():
            raise ValidationError("Pushmottagaren måste ha ett aktuellt medlemskap i trädgården.")
        return super().save(*args, **kwargs)


class ReminderDelivery(models.Model):
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE, related_name="deliveries")
    occurrence = models.ForeignKey(TaskOccurrence, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=30)
    delivery_key = models.CharField(max_length=240, unique=True)
    scheduled_for = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="pending")
    error = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.occurrence_id and self.subscription.garden_id != self.occurrence.item.garden_id:
            raise ValidationError("Påminnelsen och uppgiften måste tillhöra samma trädgård.")
        return super().save(*args, **kwargs)


class Garden(models.Model):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GardenMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Ägare"
        MEMBER = "member", "Medlem"

    garden = models.ForeignKey(Garden, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="garden_memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["garden", "user"], name="unique_garden_user"),
            models.CheckConstraint(condition=models.Q(role__in=["owner", "member"]), name="valid_garden_member_role"),
        ]


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="idempotency_records")
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "method", "path", "key"], name="unique_idempotent_request")
        ]
        indexes = [models.Index(fields=["created_at"])]
