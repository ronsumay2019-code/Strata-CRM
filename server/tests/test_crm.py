"""Reproducible API tests; no Twilio or OpenAI external calls."""
import base64
import hashlib
import hmac
import io
import os
import tempfile
from urllib.parse import urlencode

import pytest
from cryptography.fernet import Fernet

_TEMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + _TEMP.name + '/test.db'
os.environ['STRATA_ADMIN_EMAIL'] = 'owner@example.test'
os.environ['STRATA_ADMIN_PASSWORD'] = 'strong-test-password-unique-2026'
os.environ['STRATA_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['STRATA_PUBLIC_URL'] = 'https://crm.example.test'
os.environ['STRATA_MESSAGING_APPROVED'] = 'false'
os.environ['STRATA_VOICE_BRIDGE_SECRET'] = 'unit-test-only-secret'

from fastapi.testclient import TestClient
from app.bootstrap import bootstrap
from app.db import Agency, Contact, Message, SessionLocal
from app.main import app
from app.security import crypt

bootstrap()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def signed_in(c):
    response = c.post('/api/auth/login', json={'email': 'owner@example.test', 'password': 'strong-test-password-unique-2026'})
    assert response.status_code == 200, response.text
    me = c.get('/api/me')
    assert me.status_code == 200
    return {'x-csrf-token': me.json()['csrf']}


def agency(c):
    return c.get('/api/agencies').json()[0]['id']


def test_auth_and_csrf(client):
    assert client.get('/api/me').status_code == 401
    assert client.post('/api/auth/login', json={'email': 'owner@example.test', 'password': 'wrong'}).status_code == 401
    headers = signed_in(client)
    assert client.post('/api/agencies', json={'name': 'Test branch'}).status_code == 403
    assert client.post('/api/agencies', headers=headers, json={'name': 'Test branch'}).status_code == 200
    assert len(client.get('/api/agencies').json()) >= 2


def test_contacts_consent_gate_and_csv(client):
    headers = signed_in(client)
    aid = agency(client)
    url = f'/api/agencies/{aid}/contacts'
    item = client.post(url, headers=headers, json={'name': 'Contact A', 'phone': '+12055550120'}).json()
    assert item['sms_consent'] is False
    assert client.post(f'/api/agencies/{aid}/messages/send', headers=headers, json={'contact_id': item['id'], 'body': 'Hello'}).status_code == 409
    assert client.post(url, headers=headers, json={'name': 'No evidence', 'phone': '+12055550121', 'sms_consent': True}).status_code == 422
    csv_content = ('name,phone,email,tags,sms_consent,consent_source,cf_city\n'
                   'Contact B,+12055550122,b@example.test,seller;alabama,yes,Web form opt-in,Birmingham\n'
                   'Contact C,+12055550123,,,yes,,\n')
    response = client.post(url + '/import', headers=headers, files={'file': ('contacts.csv', io.BytesIO(csv_content.encode()), 'text/csv')})
    assert response.status_code == 200, response.text
    assert response.json()['created'] == 1
    assert response.json()['invalid'] == 1
    result = client.get(url).json()
    record = next(c for c in result if c['name'] == 'Contact B')
    assert record['sms_consent'] and record['fields']['city'] == 'Birmingham'
    assert client.post(f'/api/agencies/{aid}/messages/send', headers=headers, json={'contact_id': record['id'], 'body': 'Hello'}).status_code == 409


def test_workflows_signed_webhook_and_optout(client):
    headers = signed_in(client)
    aid = agency(client)
    base = f'/api/agencies/{aid}'
    c = client.post(base + '/contacts', headers=headers, json={'name': 'Seller', 'phone': '+12055550124', 'sms_consent': True, 'consent_source': 'Consent form 2026'}).json()
    assert client.post(base+'/workflows', headers=headers, json={'name': 'Seller intent', 'keyword': 'SELL', 'add_tag': 'motivated'}).status_code == 200
    with SessionLocal.begin() as db:
        a=db.get(Agency,aid)
        a.phone='+12055550199'
        a.twilio_token_enc=crypt().encrypt(b'test-twilio-token').decode()
    def inbound(body, sid):
        params={'From': c['phone'], 'To': '+12055550199', 'Body':body, 'MessageSid':sid}
        url='https://crm.example.test/api/twilio/sms'
        sign=base64.b64encode(hmac.new(b'test-twilio-token',(url+''.join(k+str(v) for k,v in sorted(params.items()))).encode(),hashlib.sha1).digest()).decode()
        return client.post('/api/twilio/sms', data=params, headers={'X-Twilio-Signature':sign})
    assert client.post('/api/twilio/sms', data={'From': c['phone'], 'To':'+12055550199', 'Body':'SELL'}).status_code == 403
    assert inbound('I want to SELL','SMabc').status_code == 200
    assert 'motivated' in next(x for x in client.get(base+'/contacts').json() if x['id']==c['id'])['tags']
    assert inbound('STOP','SMdef').status_code == 200
    assert next(x for x in client.get(base+'/contacts').json() if x['id']==c['id'])['opted_out']
    assert client.post(base+'/messages/send', headers=headers, json={'contact_id':c['id'],'body':'Hello'}).status_code == 409
    assert inbound('STOP','SMdef').status_code == 200
    with SessionLocal() as db:
        assert db.query(Message).filter(Message.provider_sid=='SMdef').count()==1


def test_campaign_blocked_without_a2p(client):
    headers=signed_in(client)
    aid=agency(client)
    c=client.post(f'/api/agencies/{aid}/campaigns', headers=headers, json={'name':'Consent-only send','body':'Hello, reply STOP to unsubscribe.'}).json()
    response=client.post(f'/api/agencies/{aid}/campaigns/{c["id"]}/queue', headers=headers)
    assert response.status_code==409


def test_agency_limit(client):
    headers=signed_in(client)
    agencies=client.get('/api/agencies').json()
    for i in range(max(0,4-len(agencies))):
        assert client.post('/api/agencies', headers=headers, json={'name': f'Agency {i+1}'}).status_code==200
    assert client.post('/api/agencies', headers=headers, json={'name':'Too many agencies'}).status_code==409


def test_static_interface(client):
    assert client.get('/').status_code == 200
    assert 'IAMSTRATA' in client.get('/').text
    assert client.get('/assets/app.js').status_code == 200


def test_tenant_membership_and_cross_agency_guards(client):
    from app.db import Membership, User
    from app.security import hasher
    headers=signed_in(client)
    first=agency(client)
    second=client.post('/api/agencies', headers=headers, json={'name':'Isolated team'}).json()['id'] if len(client.get('/api/agencies').json()) < 4 else next(a['id'] for a in client.get('/api/agencies').json() if a['id'] != first)
    with SessionLocal.begin() as db:
        u=User(email='agent@example.test', password_hash=hasher.hash('another-strong-password-2026'))
        db.add(u)
        db.flush()
        db.add(Membership(agency_id=first,user_id=u.id,role='agent'))
    guest = TestClient(app)
    login = guest.post('/api/auth/login',json={'email':'agent@example.test','password':'another-strong-password-2026'})
    assert login.status_code==200
    csrf=guest.get('/api/me').json()['csrf']
    assert len(guest.get('/api/agencies').json()) == 1
    assert guest.get(f'/api/agencies/{second}/contacts').status_code==403
    assert guest.post('/api/agencies',headers={'x-csrf-token':csrf},json={'name':'Unauthorized'}).status_code==403
    assert guest.post(f'/api/agencies/{first}/workflows',headers={'x-csrf-token':csrf},json={'name':'Not permitted','keyword':'test','add_tag':'tag'}).status_code==403
    assert guest.post(f'/api/agencies/{first}/contacts',headers={'x-csrf-token':csrf},json={'name':'Authorized','phone':'+12055550131'}).status_code==200
    guest.close()
