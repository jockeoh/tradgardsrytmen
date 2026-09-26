"""Shared write order: garden, job (when present), user/profile/membership, item, work, occurrence.

The no-op UPDATE also obtains SQLite's write reservation before reading state.
All domain writers must take the garden lock before reading mutable input.
No external transport may run inside this transaction.
"""
from functools import wraps
from django.db import transaction
from django.db.models import F
from .models import Garden, GardenItem


def lock_garden(garden_id):
    if garden_id is not None:
        Garden.objects.filter(pk=garden_id).update(version=F("version"))


def lock_item(item_id):
    Garden.objects.filter(items__pk=item_id).update(version=F("version"))
    GardenItem.objects.filter(pk=item_id).update(version=F("version"))


def garden_mutation(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return view(request, *args, **kwargs)
        with transaction.atomic():
            lock_garden(request.garden.pk)
            return view(request, *args, **kwargs)
    return wrapped
