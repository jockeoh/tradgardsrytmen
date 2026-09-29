"""Opt-in Expo Push transport. Fixed provider URL, no arbitrary callback URLs."""
import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from django.conf import settings
from django.core.exceptions import ValidationError
from .models import PushSubscription
from .transport_outcomes import ExternalOutcomeUnknown

TOKEN = re.compile(r'^(?:ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{10,200}\]$')
URL = 'https://exp.host/--/api/v2/push/send'


def save_subscription(member, data, request):
    from accounts.models import MobileSession
    from accounts.mobile import digest, password_stamp
    from django.utils import timezone
    header = request.headers.get('Authorization', '')
    session = MobileSession.objects.filter(user=member.user, token_hash=digest(header[7:]), expires_at__gt=timezone.now()).first() if header.startswith('Bearer home_') else None
    if session is None or session.password_stamp != password_stamp(member.user):
        raise ValidationError('Mobilnotiser kräver en aktuell privat mobilinloggning.')
    token = data.get('token', '')
    if not isinstance(token,str) or not TOKEN.fullmatch(token):
        raise ValidationError('En giltig enhetsregistrering krävs.')
    if data.get('active',True) and not settings.NATIVE_PUSH_ENABLED:
        raise ValidationError('Mobilnotiser är inte aktiverade på servern.')
    endpoint = URL + '#' + quote(token, safe='') + ':' + str(member.user_id) + ':' + str(member.garden_id)
    existing = PushSubscription.objects.filter(provider='expo',native_token=token,active=True).exclude(user=member.user,garden=member.garden).first()
    if existing:
        raise ValidationError('Enheten är registrerad för ett annat konto eller en annan trädgård. Avregistrera den där först.')
    sub, _ = PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        'garden':member.garden,'user':member.user,'provider':'expo','native_token':token,
        'native_membership_pk':member.pk,'native_session':session,'p256dh':'','auth':'','device_name':'Expo',
        'monthly_digest':data.get('monthly_digest',False),'task_reminders':data.get('task_reminders',False),
        'active':data.get('active',True)})
    return {'active':sub.active,'monthly_digest':sub.monthly_digest,'task_reminders':sub.task_reminders}


def prepare(subscription, payload):
    if not settings.NATIVE_PUSH_ENABLED or not TOKEN.fullmatch(subscription.native_token):
        raise ValidationError('Mobilnotiser är inte aktiverade eller registreringen är ogiltig.')
    # Private details are fetched only after opening and authenticating the app.
    # This also avoids stale sensitive notifications after logout.
    return Request(URL, data=json.dumps({'to':subscription.native_token,
        'title':'Trädgårdsrytmen','body':'Du har en påminnelse i din trädgård.',
        'data':{'garden':str(subscription.garden.public_id)},'sound':'default','channelId':'garden'}).encode(),
        headers={'Content-Type':'application/json','Accept':'application/json'}, method='POST')


def send(request, subscription):
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read(65536))
    except HTTPError as exc:
        if 400 <= exc.code < 500: return False, 'transport_rejected'
        raise ExternalOutcomeUnknown('Notisens externa utfall är oklart.') from exc
    except Exception as exc:
        raise ExternalOutcomeUnknown('Notisens externa utfall är oklart.') from exc
    ticket = payload.get('data', {})
    if isinstance(ticket,dict) and ticket.get('status')=='ok' and ticket.get('id'):
        return True, ''  # Provider accepted; physical delivery is not asserted.
    if isinstance(ticket,dict) and ticket.get('status')=='error':
        if ticket.get('details',{}).get('error')=='DeviceNotRegistered':
            PushSubscription.objects.filter(pk=subscription.pk,native_token=subscription.native_token).update(active=False)
        return False, 'transport_rejected'
    raise ExternalOutcomeUnknown('Leverantörens svar kunde inte bekräftas.')
