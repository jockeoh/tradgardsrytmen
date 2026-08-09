import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from .models import CarePlanVersion, CareRule, ResearchProposal, SourceReference

ALLOWED_DOMAINS = ["svensktradgard.se", "slu.se", "for.se", "jordbruksverket.se", "rhs.org.uk"]
SWEDISH_AUTHORITY_DOMAINS = {"slu.se", "jordbruksverket.se"}

TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "tasks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "category": {"type": "string"},
                "instructions": {"type": "string"},
                "cadence": {"type": "string", "enum": ["one_off", "seasonal", "monthly"]},
                "start_month": {"type": "integer", "minimum": 1, "maximum": 12},
                "end_month": {"type": "integer", "minimum": 1, "maximum": 12},
                "conditional": {"type": "boolean"},
                "evidence_conflict": {"type": "boolean"},
                "source_urls": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "category", "instructions", "cadence", "start_month", "end_month", "conditional", "evidence_conflict", "source_urls"],
            "additionalProperties": False,
        }},
    },
    "required": ["summary", "warnings", "uncertainties", "tasks"],
    "additionalProperties": False,
}


class ResearchError(Exception):
    pass


def _domain(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def _extract_response(payload):
    text = ""
    sources = []
    for output in payload.get("output", []):
        if output.get("type") == "web_search_call":
            sources.extend((output.get("action") or {}).get("sources") or [])
        if output.get("type") == "message":
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    text += content.get("text", "")
    if not text:
        raise ResearchError("AI-svaret saknade strukturerat innehåll.")
    try:
        return json.loads(text), sources
    except json.JSONDecodeError as exc:
        raise ResearchError("AI-svaret var inte giltig JSON.") from exc


def call_openai(item, garden):
    if not settings.OPENAI_API_KEY:
        raise ResearchError("OpenAI-nyckel saknas. Manuella funktioner fungerar fortfarande.")
    prompt = f"""Ta fram korta, praktiska och försiktiga skötselråd för {item.name} ({item.cultivar or 'sort okänd'}), kategori {item.category or 'okänd'}.
Trädgården ligger i {garden.city}, odlingszon {garden.cultivation_zone}, {garden.exposure}. Posten är {item.kind}, antal {item.quantity}, stadium {item.age_stage or 'okänt'}, placering {item.location or 'ej angiven'}.
Prioritera svenska källor och komplettera bara med RHS. Ange realistiska månadsfönster och markera evidence_conflict när källorna motsäger varandra eller underlaget är tunt. Två samstämmiga källor är bäst. Kemiskt växtskydd kräver aktuell svensk myndighetskälla. Exakta gödseldoser ska vara villkorade när jord, sort eller produkt är okänd. Kopiera inte artikeltext; sammanfatta."""
    request_body = {
        "model": settings.OPENAI_MODEL,
        "reasoning": {"effort": "low"},
        "tools": [{"type": "web_search", "filters": {"allowed_domains": ALLOWED_DOMAINS}, "user_location": {"type": "approximate", "country": "SE", "city": garden.city, "region": "Blekinge"}}],
        "include": ["web_search_call.action.sources"],
        "input": prompt,
        "text": {"format": {"type": "json_schema", "name": "garden_care_proposal", "strict": True, "schema": TASK_SCHEMA}},
    }
    encoded = json.dumps(request_body).encode()
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=encoded, headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if attempt == 0 and (exc.code == 429 or exc.code >= 500):
                time.sleep(1)
                continue
            raise ResearchError(f"AI-tjänsten svarade med felkod {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 0:
                time.sleep(1)
                continue
            raise ResearchError("AI-analysen tog för lång tid eller kunde inte nås.") from exc


@transaction.atomic
def create_research_proposal(item, garden, response_payload=None):
    payload = response_payload or call_openai(item, garden)
    result, raw_sources = _extract_response(payload)
    required_top = {"summary", "warnings", "uncertainties", "tasks"}
    required_task = {"title", "category", "instructions", "cadence", "start_month", "end_month", "conditional", "evidence_conflict", "source_urls"}
    if set(result) != required_top or not isinstance(result["tasks"], list) or any(set(task) != required_task or task["cadence"] not in {"one_off", "seasonal", "monthly"} or not 1 <= task["start_month"] <= 12 or not 1 <= task["end_month"] <= 12 for task in result["tasks"]):
        raise ResearchError("AI-svaret följde inte det strikta schemat.")
    replaced_at = timezone.now()
    older_pending = ResearchProposal.objects.filter(item=item, status="pending")
    CarePlanVersion.objects.filter(proposal__in=older_pending).update(status="superseded", reviewed_at=replaced_at)
    older_pending.update(status="superseded", reviewed_at=replaced_at)
    consulted = {}
    for source in raw_sources:
        url = source.get("url", "")
        domain = _domain(url)
        if url and any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS):
            consulted[url.rstrip("/")] = source
    next_version = (CarePlanVersion.objects.filter(item=item).aggregate(v=Max("version"))["v"] or 0) + 1
    plan = CarePlanVersion.objects.create(
        item=item, version=next_version, summary=result["summary"], warnings=result["warnings"],
        uncertainties=result["uncertainties"], model_name=settings.OPENAI_MODEL,
    )
    for url, source in consulted.items():
        domain = _domain(url)
        SourceReference.objects.create(plan=plan, title=source.get("title") or domain, url=url, domain=domain, summary=f"Källa använd i skötselanalysen för {item.name}.", is_swedish_authority=domain in SWEDISH_AUTHORITY_DOMAINS)
    for task in result["tasks"]:
        validated = [url.rstrip("/") for url in task["source_urls"] if url.rstrip("/") in consulted]
        unique_domains = {_domain(url) for url in validated}
        confidence = "low" if task["evidence_conflict"] else "high" if len(unique_domains) >= 2 else "medium" if len(unique_domains) == 1 else "low"
        chemical = any(word in (task["title"] + " " + task["instructions"]).lower() for word in ["bekämpningsmedel", "fungicid", "insekticid", "pesticid", "kemisk"])
        source_validated = bool(validated) and (not chemical or any(_domain(u) in SWEDISH_AUTHORITY_DOMAINS for u in validated))
        nutrition = any(word in (task["title"] + " " + task["instructions"]).lower() for word in ["gödsel", "näring", "npk", "gram", "dos"])
        CareRule.objects.create(
            item=item, plan=plan, title=task["title"], category=task["category"], instructions=task["instructions"],
            cadence=task["cadence"], start_month=task["start_month"], end_month=task["end_month"],
            conditional=task["conditional"] or nutrition, confidence=confidence, source_urls=validated,
            source_validated=source_validated, active=False,
        )
    return ResearchProposal.objects.create(item=item, plan=plan, response_id=payload.get("id", ""))


@transaction.atomic
def approve_proposal(proposal, rule_ids):
    from .tasks import add_months, materialize_rule, replace_future_tasks
    first_future = add_months(timezone.localdate().replace(day=1), 1)
    old_rules = list(CareRule.objects.filter(item=proposal.item, active=True))
    selected = list(proposal.plan.rules.filter(pk__in=rule_ids, source_validated=True))
    CarePlanVersion.objects.filter(item=proposal.item, status="active").update(status="superseded")
    CareRule.objects.filter(pk__in=[r.pk for r in old_rules]).update(active=False)
    replace_future_tasks(proposal.item, old_rules, first_future)
    proposal.plan.status = "active"
    proposal.plan.reviewed_at = timezone.now()
    proposal.plan.save(update_fields=["status", "reviewed_at"])
    CareRule.objects.filter(pk__in=[r.pk for r in selected]).update(active=True)
    for rule in selected:
        rule.active = True
        materialize_rule(rule, not_before=first_future)
    proposal.status = "approved"
    proposal.reviewed_at = timezone.now()
    proposal.save(update_fields=["status", "reviewed_at"])
    return selected
