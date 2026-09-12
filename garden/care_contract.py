"""Shared care validation and read-only, context-bound plan comparison."""
import hashlib
import json
import re
import unicodedata
from datetime import date
from django.utils import timezone
from .models import GardenItem, GardenSettings
from .work_categories import WORK_CATEGORIES, suggested_work_category


class CareValidationError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def normalized(value):
    return ' '.join(re.findall(r'\w+', value.casefold()))


def canonical_scope(value):
    scope = ' '.join(unicodedata.normalize('NFC', value).casefold().split())
    return 'hela-växten' if scope == 'hela växten' else scope


def rule_content(rule):
    return {field: getattr(rule, field) for field in (
        'title', 'category', 'instructions', 'cadence', 'start_month', 'end_month',
        'one_off_date', 'one_off_end', 'advice_kind', 'relevance_reason', 'need_condition',
        'conditional', 'source_urls', 'source_validated', 'evidence_conflict', 'work_id', 'identity_source_id', 'identity_change_kind')}


def validate_rule(rule, activation=False):
    if not isinstance(rule.title, str) or not 3 <= len(rule.title.strip()) <= 180:
        raise CareValidationError('Arbetet behöver en rubrik på 3–180 tecken.')
    if not isinstance(rule.instructions, str) or len(rule.instructions.strip()) < 20:
        raise CareValidationError('Skriv en användbar instruktion på minst 20 tecken.')
    if rule.category not in WORK_CATEGORIES:
        raise CareValidationError('Välj en giltig arbetskategori.')
    if rule.cadence not in {'one_off', 'seasonal', 'monthly'} or any(type(m) is not int or not 1 <= m <= 12 for m in [rule.start_month, rule.end_month]):
        raise CareValidationError('Kontrollera återkomst och månader (1–12).')
    if not isinstance(rule.relevance_reason, str) or not isinstance(rule.need_condition, str):
        raise CareValidationError("Motivering och behovsvillkor måste vara text.")
    if rule.advice_kind not in {'planned', 'on_demand', 'general'}:
        raise CareValidationError('Klassificera rådet innan det godkänns.')
    if not rule.work_id or rule.work.item_id != rule.item_id:
        raise CareValidationError('Arbetsidentitet och berörd undergrupp krävs för växten.')
    if rule.work.merged_into_id:
        raise CareValidationError('Arbetsidentiteten har ersatts. Välj den aktuella identiteten.')
    if rule.identity_source_id:
        if rule.identity_source.item_id != rule.item_id or rule.identity_source_id == rule.work_id:
            raise CareValidationError('Identitetskopplingen måste gälla två olika arbeten på samma växt.')
        if rule.identity_source.merged_into_id:
            raise CareValidationError('Källidentiteten har redan slagits ihop. Öppna förslaget igen.')
        if rule.identity_change_kind not in {'refine', 'merge'}:
            raise CareValidationError('Ange om identitetskopplingen är en förtydligad undergrupp eller en sammanslagning.')
    elif rule.identity_change_kind:
        raise CareValidationError('Identitetsändringen saknar en tidigare arbetsidentitet.')
    if rule.advice_kind != 'general':
        suggested = suggested_work_category(rule.title)
        if suggested and suggested != rule.category:
            raise CareValidationError('Arbetskategorin stämmer inte med huvudhandlingen.')
        if re.match(r'^(avstå|undvik|använd inte|behandla inte|ta inte|gör inte|låt bli|ingen)\b', rule.title.strip().casefold()):
            raise CareValidationError('En varning hör till allmänna råd, inte en egen uppgift.')
        instructions = rule.instructions.strip().casefold()
        if re.match(r'^(avstå|undvik|använd inte|behandla inte|ta inte|gör inte|låt bli)\b', instructions) and not re.search(r'\b(vattna|ta bort|plocka|bind|lägg|rensa|kontrollera|inspektera|klipp|gallra|skörda|ge)\b', instructions):
            raise CareValidationError('Ett icke-göra-råd hör till allmänna råd.')
        if not rule.relevance_reason.strip():
            raise CareValidationError('En växtspecifik relevansmotivering krävs.')
    if rule.advice_kind == 'on_demand' and not rule.need_condition.strip():
        raise CareValidationError('Beskriv när arbetet behövs.')
    conditional_title = re.search(r"\b(vid behov|vid torka|om .+ torr|vid torr)\b", rule.title.casefold())
    conditional_water = rule.category == 'Vattna' and re.search(r"\b(vid torka|om .+ torr|vid behov)\b", rule.instructions.casefold())
    if rule.advice_kind == 'planned' and (rule.need_condition.strip() or rule.conditional or conditional_title or conditional_water):
        raise CareValidationError('Villkorat arbete ska klassificeras som Vid behov.')
    if rule.advice_kind == 'planned' and rule.cadence == 'one_off':
        if not isinstance(rule.one_off_date, date) or not isinstance(rule.one_off_end, date) or rule.one_off_end < rule.one_off_date:
            raise CareValidationError('Engångsarbete kräver ett explicit start- och slutdatum.')
    if not isinstance(rule.source_urls, list) or any(not isinstance(u, str) or not u.startswith('https://') for u in rule.source_urls):
        raise CareValidationError('Källor ska vara en lista med https-adresser.')
    if activation and (not rule.source_validated or not rule.source_urls or rule.evidence_conflict):
        raise CareValidationError('Verifierat källstöd utan olöst källkonflikt krävs.')
    if activation and rule.work.excluded_at and not rule.identity_source_id:
        raise CareValidationError('Arbetet är bortvalt här. Återställ bortvalet först.')


def care_context(item):
    item = GardenItem.objects.get(pk=item.pk)
    garden = GardenSettings.load()
    return {
        'today': timezone.localdate().isoformat(),
        'plant': {f: getattr(item, f) for f in ['id', 'name', 'cultivar', 'quantity', 'kind', 'category', 'age_stage', 'area_id', 'location', 'notes', 'updated_at']},
        'garden': {f: getattr(garden, f) for f in ['city', 'cultivation_zone', 'exposure']},
        'works': list(item.works.filter(merged_into=None).order_by('pk').values('id', 'action_key', 'scope', 'excluded_at')),
        'active_rules': [dict(id=r.pk, **rule_content(r)) for r in item.care_rules.filter(active=True).order_by('pk')],
        'history': list(item.tasks.order_by('pk').values('id', 'work_id', 'title', 'instructions', 'status', 'window_start', 'window_end', 'completed_at', 'skipped_at', 'note', 'archive_reason', 'updated_at')),
    }


def overlaps(a, b):
    """Conservative candidate detection only; never infer a semantic merge."""
    if a.work_id == b.work_id:
        return True
    if a.work and b.work and a.work.scope != b.work.scope:
        # An unspecified/all scope may include a named subgroup.
        scopes = {canonical_scope(a.work.scope), canonical_scope(b.work.scope)}
        if scopes == {'sommarhallon', 'hösthallon'} or (any(s.startswith(('unga ', 'ungt ')) for s in scopes) and any(s.startswith(('gamla ', 'gammalt ', 'äldre ')) for s in scopes)):
            return False
    words_a, words_b = set(normalized(a.instructions).split()), set(normalized(b.instructions).split())
    common = len(words_a & words_b) / max(1, min(len(words_a), len(words_b)))
    # Same-category work is reviewed conservatively, including inspection/action
    # split across different categories when instructions share the action.
    return a.category == b.category or common >= .55


def plan_comparison(plan):
    proposed = list(plan.rules.select_related('work').order_by('pk'))
    existing = list(plan.item.care_rules.filter(active=True).exclude(plan=plan).select_related('work').order_by('pk'))
    from django.db.models import Q
    historical = []
    known_works = {r.work_id for r in existing}
    for old in plan.item.care_rules.exclude(plan=plan).filter(Q(occurrences__isnull=False) | Q(work__excluded_at__isnull=False)).select_related('work').order_by('-pk').distinct():
        if old.work_id not in known_works:
            historical.append(old)
            known_works.add(old.work_id)
    context = care_context(plan.item)
    token = digest({'context': context, 'rules': [dict(id=r.pk, **rule_content(r)) for r in proposed]})
    rows = []
    for rule in proposed:
        matches = [r for r in existing if r.work_id and r.work_id == rule.work_id]
        change = 'new' if not matches else 'unchanged' if any(rule_content(rule) == rule_content(r) for r in matches) else 'changed'
        conflicts = []
        for other in existing + historical + proposed:
            if other.pk == rule.pk or (other in existing + historical and other.work_id == rule.work_id):
                continue
            if overlaps(rule, other):
                conflicts.append({'rule_id': other.pk, 'title': other.title, 'scope': other.work.scope if other.work else 'okänd', 'proposed': other in proposed, 'same_work': rule.work_id == other.work_id, 'historical': other in historical})
        error = ''
        try:
            validate_rule(rule, activation=True)
        except CareValidationError as exc:
            error = str(exc)
        rows.append({'rule_id': rule.pk, 'change': change, 'conflicts': conflicts, 'error': error,
                     'preselected': rule.advice_kind == 'planned' and not conflicts and not error,
                     'history_count': sum(1 for t in context['history'] if t['work_id'] == rule.work_id and t['status'] in {'completed','skipped'}),
                     'reason': rule.relevance_reason, 'existing_rule_ids': [r.pk for r in matches]})
    removed = [{'rule_id': r.pk, 'title': r.title, 'work_id': r.work_id, 'scope': r.work.scope if r.work else 'okänd', 'change': 'removed'} for r in existing if not (r.work and r.work.excluded_at) and not any(p.work_id == r.work_id for p in proposed)]
    return {'token': token, 'rows': rows, 'removed': removed,
            'context_changed': bool(plan.research_context and digest({k:v for k,v in context.items() if k != 'works'}) != digest({k:v for k,v in plan.research_context.items() if k != 'works'}))}
