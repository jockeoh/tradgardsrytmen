"""Exercise real SQLite locking in an isolated temporary database; no external calls."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    with TemporaryDirectory(prefix='garden-concurrency-') as directory:
        os.environ['TRADGARDSRYTMEN_DB_PATH'] = str(Path(directory) / 'test.sqlite3')
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        import django
        django.setup()
        from django.core.management import call_command
        call_command('migrate', verbosity=0, stdout=StringIO())
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections, connections
        from django.utils import timezone
        from garden.models import GardenItem, WorkIdentity, CarePlanVersion, ResearchProposal, CareRule, TaskOccurrence
        from garden.research import approve_proposal
        from garden.care_contract import plan_comparison
        from garden.tasks import needs_now
        item = GardenItem.objects.create(name='Samtidighetstest')
        work = WorkIdentity.objects.create(item=item, action_key='gallra', scope='hela-växten')
        plan = CarePlanVersion.objects.create(item=item)
        rule = CareRule.objects.create(item=item, plan=plan, work=work, title='Gallra skott', category='Beskära och binda upp',
            instructions='Ta bort gamla fruktade skott och lämna nya skott.', relevance_reason='Hallonets fruktade skott ersätts av nya.',
            start_month=1, end_month=12, source_urls=['https://www.slu.se/'], source_validated=True)
        proposal = ResearchProposal.objects.create(item=item, plan=plan)
        token = plan_comparison(plan)['token']

        def approve(_):
            close_old_connections()
            try:
                return [r.pk for r in approve_proposal(proposal, [rule.pk], token)]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(approve, range(4)))
        assert all(result == [rule.pk] for result in results), results
        assert TaskOccurrence.objects.filter(work=work, season_year=timezone.localdate().year).count() == 1
        work2 = WorkIdentity.objects.create(item=item, action_key='vattna', scope='hela-växten')
        CareRule.objects.create(item=item, plan=plan, work=work2, title='Vattna vid behov', advice_kind='on_demand', active=True, need_condition='Torr jord')

        def need(_):
            close_old_connections()
            try:
                return needs_now(work2.pk)[0].pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(need, range(4)))
        assert len(set(ids)) == 1, ids
        connections.close_all()
        print('PASS: four concurrent approvals and four need requests produce unique occurrences')


if __name__ == '__main__':
    main()
