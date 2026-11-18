import json
from unittest.mock import patch

from .models import CarePlanVersion, CareRule, Garden, GardenItem, ResearchProposal, WorkIdentity
from .research import ResearchError
from .testing import TenantTestCase


class GardenReviewTests(TenantTestCase):
    def proposal(self, name, title, garden=None, verified=True):
        plant = GardenItem.objects.create(garden=garden or self.tenant_garden, name=name)
        plan = CarePlanVersion.objects.create(item=plant)
        proposal = ResearchProposal.objects.create(plan=plan, item=plant)
        work = WorkIdentity.objects.create(item=plant, action_key="vatten")
        rule = CareRule.objects.create(plan=plan, item=plant, work=work, title=title,
            category="Vattna", instructions="Vattna långsamt vid växtens rötter.", advice_kind="on_demand",
            need_condition="När jorden är torr", relevance_reason="Växtens rötter behöver vatten.",
            source_validated=verified, source_urls=["https://slu.se/test"])
        return proposal, rule

    def queue(self):
        return self.client.get("/api/proposals/").json()["garden_review"]

    def apply(self, review, choices):
        return self.client.post("/api/proposals/approve-garden/", json.dumps({
            "comparison_token": review["token"], "choice_ids": choices}), content_type="application/json")

    def test_one_garden_choice_with_individual_evidence_and_a_distinct_trigger(self):
        rose, r = self.proposal("Ros", "Vattna vid torka")
        raspberry, h = self.proposal("Hallon", "Vattna när jorden torkar")
        blocked, b = self.proposal("Pion", "Vattna vid torka", verified=False)
        planting, p = self.proposal("Lönn", "Vattna efter plantering")
        other, _ = self.proposal("Annan", "Vattna vid torka", garden=Garden.objects.create(name="Annan"))
        review = self.queue()
        self.assertEqual(len(review["choices"]), 2)
        drought = review["choices"][0]
        self.assertEqual({m["rule_id"] for m in drought["members"] if m["eligible"]}, {r.pk, h.pk})
        response = self.apply(review, [drought["id"]])
        self.assertEqual(response.json(), {"ok":True, "approved":2, "plants":2, "rejected":1})
        for proposal, expected in [(rose, "approved"), (raspberry, "approved"), (blocked, "pending"),
                                   (planting, "rejected"), (other, "pending")]:
            proposal.refresh_from_db()
            self.assertEqual(proposal.status, expected)
        for rule in (r,h):
            rule.refresh_from_db()
            self.assertTrue(rule.active)
            self.assertEqual(rule.occurrences.count(), 0)

    def test_changed_queue_or_failed_plant_cannot_partially_approve(self):
        first, _ = self.proposal("Ros", "Vattna vid torka")
        old = self.queue()
        second, _ = self.proposal("Hallon", "Vattna vid torka")
        self.assertEqual(self.apply(old, [old["choices"][0]["id"]]).status_code, 409)
        review = self.queue()
        from .research import approve_proposal
        def fail_second(proposal, *args):
            if proposal.pk == second.pk:
                raise ResearchError("Ändrat råd.")
            return approve_proposal(proposal, *args)
        with patch("garden.views.approve_proposal", side_effect=fail_second):
            self.assertEqual(self.apply(review,[review["choices"][0]["id"]]).status_code,409)
        first.refresh_from_db()
        self.assertEqual(first.status, "pending")
        self.assertFalse(CareRule.objects.filter(active=True).exists())
        self.assertEqual(self.apply(review, []).json()["rejected"], 2)
