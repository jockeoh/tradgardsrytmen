import json
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from garden.management.garden_target import add_garden_argument, selected_garden
from garden.models import BackgroundJob
from garden.jobs import digest
from garden.job_operations import reconciliation_snapshot, reconcile_job


class Command(BaseCommand):
    help = 'Preview an uncertain job; explicit evidence is required to reconcile without retrying.'

    def add_arguments(self, parser):
        add_garden_argument(parser)
        parser.add_argument('--job', required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--operator')
        parser.add_argument('--decision', choices=['confirmed_not_sent', 'confirmed_received'])
        parser.add_argument('--evidence')
        parser.add_argument('--expected')

    def handle(self, *args, **options):
        garden = selected_garden(options)
        try:
            job = BackgroundJob.objects.get(garden=garden, public_id=options['job'])
        except (BackgroundJob.DoesNotExist, ValidationError, ValueError):
            raise CommandError('Jobbet finns inte i den valda trädgården.')
        if not options['apply']:
            snapshot = reconciliation_snapshot(job)
            # No raw provider payload, endpoint, user note or attempt token in output.
            self.stdout.write(json.dumps({'job': str(job.public_id), 'state': job.state,
                'kind': job.kind, 'attempts': job.attempts, 'reason': job.reason,
                'delivery_confirmed': bool(job.delivery_id and job.delivery.sent_at),
                'expected': digest(snapshot)}, sort_keys=True))
            return
        try:
            operator = get_user_model().objects.get(username=options['operator'])
            receipt = reconcile_job(garden, options['job'], operator, decision=options['decision'],
                evidence=options['evidence'], expected=options['expected'])
        except (get_user_model().DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError(str(exc))
        self.stdout.write(f'Reconciliation {receipt.pk} recorded. No transport or retry performed.')
