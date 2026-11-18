"""Garden-wide review choices. Each plant keeps its own rule, evidence and schedule."""
from collections import defaultdict
import re

from .care_contract import digest, normalized


def choice_key(rule):
    title = normalized(rule["title"])
    kind = rule["advice_kind"]
    if (kind == "on_demand" and rule["category"] == "Vattna"
            and re.search(r"\b(tork\w*|torr\w*)\b", title)
            and not re.search(r"\b(planter\w*|frost\w*|vinter\w*)\b", title)):
        return ("drought",), "Vattna vid torka"
    if rule["category"] == "Beskära och binda upp":
        spent = r"färdigburna|fruktade|(?:burit|gett) (?:frukt|bär)|som (?:har )?gett skörd"
        if (re.search(r"hallon|björnbär", normalized(rule["item"]["name"]))
                and re.search(r"^(gallra|klipp bort|ta bort|skär bort)", title)
                and (re.search(spent, title) or (title == "gallra efter skörd" and re.search(spent, normalized(rule["instructions"]))))):
            return ("spent-canes", kind), "Klipp bort skott som burit bär"
    # A title alone cannot establish the same trigger or season. Retain the
    # original instructions even when two plants share the same review choice.
    timing = (rule["cadence"], rule["start_month"], rule["end_month"], rule["one_off_date"], rule["one_off_end"])
    key = (kind, rule["category"], title, timing, normalized(rule["need_condition"]))
    return key, rule["title"]


def garden_review(plans):
    buckets = defaultdict(list)
    tokens = []
    for plan in plans:
        comparison = plan["comparison"]
        tokens.append((plan["proposal_id"], comparison["token"]))
        rows = {r["rule_id"]: r for r in comparison["rows"]}
        for rule in plan["rules"]:
            key, title = choice_key(rule)
            member = {"rule_id": rule["id"], "item_id": rule["item"]["id"], "proposal_id": plan["proposal_id"],
                      "eligible": bool(rows[rule["id"]]["preselected"] and not rule["identity_source_id"])}
            buckets[key].append((title, member))

    groups = []
    for entries in buckets.values():
        members = [member for _, member in entries]
        if len({m["item_id"] for m in members}) > 1:
            groups.append((entries[0][0], members))
        else:
            groups.extend((title, [member]) for title, member in entries)
    choices = [{"id": str(min(m["rule_id"] for m in members)), "title": title, "members": members}
               for title, members in groups]
    choices.sort(key=lambda c: (-len(c["members"]), c["title"].casefold(), c["id"]))
    return {"token": digest([tokens, choices]), "choices": choices}
