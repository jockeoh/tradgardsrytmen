"""Complete private app adapter. Shared domain operations, frozen grant, durable receipts.

Identifiers in this contract are opaque strings; internal integer IDs are never
accepted without garden-scoped domain checks. No request triggers external I/O.
"""
import copy
import hashlib
import json
from datetime import date

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import views
from .api_support import api_authenticated, api_error, idempotent_mutation, parse_json_object
from .locking import lock_garden
from .models import (GardenMembership, GardenItem, GardenArea, GardenSettings,
                     CarePlanVersion, CareRule, WorkIdentity, TaskOccurrence,
                     ResearchProposal, BackgroundJob)

SALT = 'garden.native-workspace.v1'
PROTOCOL = 'workspace-1'


def opaque(value, key=''):
    if isinstance(value, dict):
        return {k: opaque(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [opaque(v, key) for v in value]
    if type(value) is int and (key == 'id' or key.endswith('_id')):
        return str(value)
    return value


def unpack(response):
    return json.loads(response.content)


def revision(garden):
    # Private gardens are small. A single conservative revision also protects
    # profile/area/rule edits that lack their own version counters in legacy data.
    collections = []
    for model, predicate in [
        (GardenItem, {'garden': garden}), (GardenArea, {'garden': garden}),
        (GardenSettings, {'garden': garden}), (CarePlanVersion, {'item__garden': garden}),
        (CareRule, {'item__garden': garden}), (WorkIdentity, {'item__garden': garden}),
        (TaskOccurrence, {'item__garden': garden}), (ResearchProposal, {'item__garden': garden}),
    ]:
        collections.append(list(model.objects.filter(**predicate).order_by('pk').values()))
    return hashlib.sha256(json.dumps(collections, sort_keys=True, default=str).encode()).hexdigest()


def bind(request, member):
    request.user = request.api_user
    request.garden = member.garden
    request.garden_membership = member


def calendar_task(task):
    result = views._task_json(task)
    happened = task.completed_at or task.skipped_at or task.archived_at
    result['happened_on'] = timezone.localtime(happened).date().isoformat() if happened else None
    result['calendar_visible'] = task.item.active and (task.status != 'pending' or
        (not task.archive_reason and not (task.work and task.work.excluded_at)))
    return result


def workspace_item(item):
    data = views._item_json(item, True)
    # A plan retains all proposed rules for review history, including rejected
    # choices. Current care also includes restored rules from older plans.
    data['current_rules'] = [views._rule_json(rule) for rule in
        item.care_rules.filter(active=True, work__excluded_at__isnull=True)
        .select_related('work')]
    return data


def snapshot(request, member):
    base = unpack(views.api_bootstrap(request))
    base['items'] = [workspace_item(item) for item in
                     GardenItem.objects.filter(garden=member.garden, active=True).select_related('area')]
    base['occurrences'] = [calendar_task(task) for task in
                       TaskOccurrence.objects.filter(item__garden=member.garden)
                       .select_related('item__area', 'work', 'rule').order_by('window_start', 'pk')]
    base['history'] = [views._task_json(task) for task in
                       TaskOccurrence.objects.filter(item__garden=member.garden).exclude(status='pending')
                       .select_related('item__area', 'work', 'rule').order_by('-updated_at')]
    base['proposals'] = [views._plan_json(p.plan) for p in
                         ResearchProposal.objects.filter(item__garden=member.garden, status='pending').select_related('plan')]
    base['profile'] = unpack(views.api_settings(request))['settings']
    base['jobs'] = [dict(views._job_json(job), item_id=job.item_id) for job in
                    BackgroundJob.objects.filter(garden=member.garden, actor=request.api_user,
                       membership_pk=member.pk, kind='research').order_by('-pk')[:50]]
    base['context'] = signing.dumps({'account': str(request.api_user.public_id),
                    'garden': str(member.garden.public_id), 'membership': member.pk}, salt=SALT)
    base['revision'] = revision(member.garden)
    base['protocol'] = PROTOCOL
    base['garden_id'] = str(member.garden.public_id)
    base['membership'] = member.pk
    base['capabilities'] = {'research': settings.DURABLE_JOBS,
                           'native_push': getattr(settings, 'NATIVE_PUSH_ENABLED', False)}
    return opaque(base)


# Domain operations are deliberately enumerated, never arbitrary URL forwarding.
OPERATIONS = {
    'plant.create': (views.api_items, 'POST', None),
    'plant.update': (views.api_item, 'PATCH', 'item_id'),
    'task.create': (views.api_tasks, 'POST', None),
    'task.update': (views.api_task, 'PATCH', 'task_id'),
    'area.create': (views.api_areas, 'POST', None),
    'area.update': (views.api_area, 'PATCH', 'area_id'),
    'area.delete': (views.api_area, 'DELETE', 'area_id'),
    'work.need': (views.api_need, 'POST', 'work_id'),
    'work.update': (views.api_work, 'PATCH', 'work_id'),
    'rule.update': (views.api_rule, 'PATCH', 'rule_id'),
    'proposal.approve': (views.api_approve_proposal, 'POST', 'proposal_id'),
    'proposal.reject': (views.api_proposal, 'DELETE', 'proposal_id'),
    'profile.update': (views.api_settings, 'PATCH', None),
}
PLANT_FIELDS = {'name', 'canonical_name', 'aliases', 'category', 'kind', 'cultivar',
                'quantity', 'age_stage', 'area_id', 'location_detail', 'notes'}
RULE_FIELDS = {'title', 'category', 'instructions', 'cadence', 'start_month', 'end_month',
               'advice_kind', 'relevance_reason', 'need_condition', 'conditional',
               'source_urls', 'evidence_conflict', 'one_off_date', 'one_off_end',
               'identity_mode', 'work_id', 'scope'}
ALLOWED = {
    'plant.create': PLANT_FIELDS, 'plant.update': PLANT_FIELDS,
    'task.create': {'item_id', 'title', 'instructions', 'category', 'window_start', 'window_end'},
    'task.update': {'title', 'instructions', 'note', 'status', 'category'},
    'area.create': {'name'}, 'area.update': {'name'}, 'area.delete': set(),
    'work.need': set(), 'work.update': {'excluded'}, 'rule.update': RULE_FIELDS,
    'proposal.approve': {'rule_ids', 'comparison_token', 'resolutions'}, 'proposal.reject': set(),
    'profile.update': {'garden_name', 'city', 'cultivation_zone', 'exposure',
                       'monthly_digest_day', 'reminder_weekday', 'reminder_hour'},
    'research.start': {'consent'},
    'notifications.save': {'token', 'monthly_digest', 'task_reminders', 'active'},
}


def validate(command, values):
    if not isinstance(values, dict) or set(values) - ALLOWED[command]:
        raise ValueError('Kontrollera fälten i formuläret.')
    data = copy.deepcopy(values)
    bools = {'excluded', 'conditional', 'evidence_conflict', 'consent', 'monthly_digest', 'task_reminders', 'active'}
    ints = {'quantity': (1, 100000), 'start_month': (1, 12), 'end_month': (1, 12),
            'monthly_digest_day': (1, 28), 'reminder_weekday': (0, 6), 'reminder_hour': (0, 23)}
    ids = {'item_id', 'area_id', 'work_id'}
    for key, value in data.items():
        if key in bools:
            if type(value) is not bool: raise ValueError('Välj ja eller nej.')
        elif key in ints:
            low, high = ints[key]
            if type(value) is not int or not low <= value <= high: raise ValueError('Kontrollera talet.')
        elif key in ids:
            if key == 'area_id' and value in ('', None): data[key] = None
            elif not isinstance(value, str) or not value.isdecimal() or int(value) < 1: raise ValueError('Ogiltig referens.')
            else: data[key] = int(value)
        elif key in {'aliases', 'source_urls', 'rule_ids'}:
            if not isinstance(value, list) or len(value) > 200 or any(not isinstance(x, str) or len(x)>2000 for x in value):
                raise ValueError('Kontrollera listan.')
            if key == 'rule_ids' and any(not x.isdecimal() for x in value): raise ValueError('Ogiltigt råd.')
        elif key == 'resolutions':
            if not isinstance(value, dict) or len(value)>200 or any(not isinstance(v,str) or len(v)>10000 for v in value.values()): raise ValueError('Kontrollera överlappen.')
        elif not isinstance(value, str) or len(value) > 10000:
            raise ValueError('Kontrollera texten.')
    for key, limit in {'name':120, 'title':180, 'garden_name':120, 'city':80,
                       'cultivation_zone':20, 'exposure':160, 'cultivar':120,
                       'category':80, 'canonical_name':120, 'age_stage':100, 'location_detail':160}.items():
        if key in data and (len(data[key])>limit or (key in {'name','title','garden_name'} and not data[key].strip())):
            raise ValueError('Kontrollera namn och textlängd.')
    if command in {'plant.create','area.create','area.update'} and not data.get('name','').strip(): raise ValueError('Namn krävs.')
    if command.startswith('plant.') and data.get('kind','individual') not in {'individual','group','bed'}: raise ValueError('Välj växttyp.')
    if 'status' in data and data['status'] not in {'pending','completed','skipped'}: raise ValueError('Ogiltig status.')
    if command == 'task.create':
        if not data.get('title','').strip() or not data.get('item_id'): raise ValueError('Uppgift och växt krävs.')
        start = date.fromisoformat(data.get('window_start',''))
        if date.fromisoformat(data.get('window_end') or start.isoformat()) < start: raise ValueError('Kontrollera datumintervallet.')
    if command == 'research.start' and data.get('consent') is not True: raise ValueError('Godkänn först att växtuppgifter skickas för analys.')
    return data


@require_http_methods(['GET', 'POST'])
@api_authenticated
def workspace(request, garden_id):
    member = GardenMembership.objects.select_related('garden').filter(user=request.api_user, garden__public_id=garden_id).first()
    if not member: return api_error('not_found', 'Trädgården finns inte.', 404)
    bind(request, member)
    if request.method == 'GET':
        with transaction.atomic():
            lock_garden(member.garden_id)
            if not GardenMembership.objects.filter(pk=member.pk, user=request.api_user).exists():
                return api_error('not_found', 'Åtkomsten har ändrats.', 404)
            return JsonResponse(snapshot(request, member))
    body = parse_json_object(request)
    if (not isinstance(body, dict) or set(body) != {'command','target','values','context','revision'}
            or not isinstance(body.get('context'), str) or len(body['context']) > 2000
            or not isinstance(body.get('revision'), str) or len(body['revision']) != 64):
        return api_error('validation_error', 'Kontrollera begäran.', 400)
    try:
        context = signing.loads(body['context'], salt=SALT)
        if context != {'account': str(request.api_user.public_id), 'garden': str(garden_id), 'membership': member.pk}:
            return api_error('not_found', 'Åtkomsten har ändrats. Öppna trädgården igen.', 404)
    except (signing.BadSignature, TypeError):
        return api_error('not_found', 'Åtkomsten har ändrats.', 404)
    command = body['command']
    if not isinstance(command,str) or command not in ALLOWED:
        return api_error('validation_error', 'Okänd handling.', 400)
    try:
        values = validate(command, body['values'])
        target = body['target']
        if target is not None and (not isinstance(target,str) or not target.isdecimal() or int(target)<1): raise ValueError('Ogiltig referens.')
        if (command in OPERATIONS and OPERATIONS[command][2] or command=='research.start') and target is None: raise ValueError('Referens krävs.')
    except (ValueError, TypeError) as exc:
        return api_error('validation_error', str(exc), 400)

    def apply():
        if body['revision'] != revision(member.garden):
            return 409, {'error': {'code':'version_conflict','message':'Trädgården har ändrats. Hämta senaste underlaget och granska innan du sparar.','fields':{}}}
        if command == 'research.start':
            if not settings.DURABLE_JOBS:
                return 409, {'error': {'code':'unavailable','message':'Analyskön är inte aktiverad på servern.','fields':{}}}
            from .jobs import enqueue_research
            item = GardenItem.objects.filter(pk=int(target), garden=member.garden, active=True).first()
            if not item: raise Http404
            job = enqueue_research(member.garden, request.api_user, item, request.headers.get('Idempotency-Key',''))
            status, payload = 202, {'job': views._job_json(job)}
        elif command == 'notifications.save':
            from .native_push import save_subscription
            payload = save_subscription(member, values, request)
            status = 200
        else:
            view, method, argument = OPERATIONS[command]
            adapted = copy.copy(request)
            adapted.method = method
            adapted._body = json.dumps(values).encode()
            response = view(adapted, **({argument:int(target)} if argument else {}))
            status, payload = response.status_code, unpack(response)
            if status >= 400:
                message = payload.get('error', 'Handlingen kunde inte genomföras.')
                return status, {'error': {'code':'invalid_transition' if status==409 else 'validation_error',
                                        'message':str(message),'fields':{}}}
        return status, {'protocol':PROTOCOL,'garden_id':str(garden_id), 'membership':member.pk,
                        'result':opaque(payload)}

    try:
        with transaction.atomic():
            lock_garden(member.garden_id)
            if not GardenMembership.objects.select_for_update().filter(pk=member.pk, user=request.api_user, user__is_active=True).exists():
                return api_error('not_found', 'Åtkomsten har ändrats.', 404)
            return idempotent_mutation(request, body, apply)
    except Http404:
        return api_error('not_found','Resursen finns inte.',404)
    except (ValidationError, ValueError, TypeError, IntegrityError) as exc:
        return api_error('validation_error', 'Kontrollera uppgifterna och hämta senaste underlaget.', 400)
