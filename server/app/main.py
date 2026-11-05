"""Multi-agency CRM API. Operational SMS/calls require independent Twilio setup."""
import csv
import hashlib
import io
import json
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import httpx
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .db import (Agency, CallRecord, Campaign, Contact, Membership, Message, Outbox, Session, SessionLocal, User,
                 Workflow, initialize, now)
from .integrations import create_click_to_call, send_sms, twilio_token, validate_twilio
from .security import crypt, get_auth, hash_token, hasher, new_session, secure_cookies

ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="IAmStrata CRM API", docs_url=None if os.getenv("STRATA_ENV") == "production" else "/api/docs")
app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")


@app.on_event("startup")
def on_startup():
    # Fail closed before accepting users on a publicly reachable service.
    if os.getenv("STRATA_ENV") == "production":
        configured = os.getenv("DATABASE_URL", "")
        if not configured.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Production requires a PostgreSQL DATABASE_URL")
        if not os.getenv("STRATA_ENCRYPTION_KEY"):
            raise RuntimeError("Missing STRATA_ENCRYPTION_KEY")
        if not os.getenv("STRATA_PUBLIC_URL", "").startswith("https://"):
            raise RuntimeError("Missing secure public URL")
    initialize()
    if os.getenv("STRATA_ENV") == "production":
        with SessionLocal() as db:
            has_owner = db.query(User).first() is not None
        if not has_owner:
            # Never insert sample records or default passwords.
            from .bootstrap import bootstrap
            bootstrap()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/healthz")
def health():
    return {"status": "ok"}


class LoginBody(BaseModel):
    email: str
    password: str


class AgencyBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str
    email: str | None = None
    tags: list[str] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)
    sms_consent: bool = False
    consent_source: str | None = None


class SendBody(BaseModel):
    contact_id: str
    body: str = Field(min_length=1, max_length=1600)


class WorkflowBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    keyword: str = Field(min_length=1, max_length=90)
    add_tag: str = Field(min_length=1, max_length=50)


class CampaignBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=1600)


class TwilioBody(BaseModel):
    phone: str
    account_sid: str
    auth_token: str
    messaging_service_sid: str | None = None
    forward_phone: str | None = None


class CallBody(BaseModel):
    contact_id: str
    operator_phone: str


def phone(raw: str) -> str:
    value = re.sub(r"[\s().-]", "", str(raw).strip())
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise HTTPException(422, "Phone must be in E.164 format, e.g. +12055550199")
    return value


def agency_access(db, agency_id, auth, owner=False):
    agency = db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(404, "Agency not found")
    if auth["is_owner"]:
        return agency
    membership = db.scalar(select(Membership).where(Membership.user_id == auth["id"], Membership.agency_id == agency_id))
    if not membership:
        raise HTTPException(403, "Access denied to this agency")
    if owner and membership.role not in ("owner", "admin"):
        raise HTTPException(403, "Agency administrator required")
    return agency


def contact_view(c):
    return {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
            "tags": json.loads(c.tags_json), "fields": json.loads(c.fields_json),
            "sms_consent": c.sms_consent, "consent_source": c.consent_source,
            "opted_out": c.opted_out_at is not None}


def _ensure_sendable(c):
    if not c.sms_consent or c.opted_out_at:
        raise HTTPException(409, "Contact lacks documented SMS consent or opted out")


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
        try:
            valid = bool(user and hasher.verify(user.password_hash, body.password))
        except (VerifyMismatchError, Exception):
            valid = False
        if not valid:
            raise HTTPException(401, "Invalid email or password")
        token, csrf = new_session(user.id)
        response.set_cookie("strata_session", token, httponly=True, secure=secure_cookies(), samesite="lax", max_age=604800, path="/")
        return {"email": user.email, "csrf": csrf}


@app.post("/api/auth/logout")
def logout(response: Response, request: Request, auth=Depends(get_auth)):
    with SessionLocal.begin() as db:
        session = db.get(Session, hash_token(request.cookies["strata_session"]))
        if session:
            db.delete(session)
    response.delete_cookie("strata_session", path="/")
    return {"ok": True}


@app.get("/api/me")
def me(auth=Depends(get_auth)):
    return auth


@app.get("/api/agencies")
def agencies(auth=Depends(get_auth)):
    with SessionLocal() as db:
        q = select(Agency) if auth["is_owner"] else select(Agency).join(Membership).where(Membership.user_id == auth["id"])
        result = db.scalars(q.order_by(Agency.created_at)).all()
        return [{"id": a.id, "name": a.name, "phone": a.phone,
                 "twilio_configured": bool(a.twilio_account_sid and a.twilio_token_enc),
                 "a2p_verified": a.verified_a2p} for a in result]


@app.post("/api/agencies")
def create_agency(body: AgencyBody, auth=Depends(get_auth)):
    if not auth["is_owner"]:
        raise HTTPException(403, "Platform owner required")
    with SessionLocal.begin() as db:
        if db.scalar(select(func.count()).select_from(Agency)) >= 4:
            raise HTTPException(409, "Initial plan allows primary agency plus three sub-agencies")
        a = Agency(name=body.name.strip())
        db.add(a)
        db.flush()
        db.add(Membership(agency_id=a.id, user_id=auth["id"], role="owner"))
        return {"id": a.id, "name": a.name}


@app.get("/api/agencies/{agency_id}/dashboard")
def dashboard(agency_id: str, auth=Depends(get_auth)):
    with SessionLocal() as db:
        agency_access(db, agency_id, auth)
        return {"contacts": db.scalar(select(func.count()).select_from(Contact).where(Contact.agency_id == agency_id)),
                "consented": db.scalar(select(func.count()).select_from(Contact).where(Contact.agency_id == agency_id, Contact.sms_consent.is_(True), Contact.opted_out_at.is_(None))),
                "messages": db.scalar(select(func.count()).select_from(Message).where(Message.agency_id == agency_id)),
                "workflows": db.scalar(select(func.count()).select_from(Workflow).where(Workflow.agency_id == agency_id, Workflow.enabled.is_(True)))}


@app.get("/api/agencies/{agency_id}/contacts")
def list_contacts(agency_id: str, q: str = "", auth=Depends(get_auth)):
    with SessionLocal() as db:
        agency_access(db, agency_id, auth)
        stmt = select(Contact).where(Contact.agency_id == agency_id)
        if q.strip():
            stmt = stmt.where((Contact.name.ilike(f"%{q[:80]}%")) | (Contact.phone.ilike(f"%{q[:80]}%")))
        return [contact_view(c) for c in db.scalars(stmt.order_by(Contact.created_at.desc()).limit(200)).all()]


@app.post("/api/agencies/{agency_id}/contacts")
def create_contact(agency_id: str, body: ContactBody, auth=Depends(get_auth)):
    with SessionLocal.begin() as db:
        agency_access(db, agency_id, auth)
        if body.sms_consent and not body.consent_source:
            raise HTTPException(422, "Documented consent source is required when consent is true")
        c = Contact(agency_id=agency_id, name=body.name.strip(), phone=phone(body.phone),
                    email=body.email, tags_json=json.dumps(body.tags[:40]), fields_json=json.dumps(body.fields),
                    sms_consent=body.sms_consent, consent_source=body.consent_source if body.sms_consent else None,
                    consent_at=now() if body.sms_consent else None)
        if db.scalar(select(Contact.id).where(Contact.agency_id == agency_id, Contact.phone == c.phone)):
            raise HTTPException(409, "Phone already exists in this agency")
        db.add(c)
        db.flush()
        return contact_view(c)


@app.post("/api/agencies/{agency_id}/contacts/import")
async def import_csv(agency_id: str, file: UploadFile = File(...), auth=Depends(get_auth)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Upload a CSV file")
    contents = await file.read(2_000_001)
    if len(contents) > 2_000_000:
        raise HTTPException(413, "CSV is too large (2 MB max)")
    try:
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
        if not reader.fieldnames or not {"name", "phone"}.issubset(set(reader.fieldnames)):
            raise HTTPException(422, "CSV requires name and phone columns")
        rows = list(reader)
        if len(rows) > 5000:
            raise HTTPException(413, "Import max 5,000 contacts at once")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8")
    counts = {"created": 0, "duplicates": 0, "invalid": 0}
    with SessionLocal.begin() as db:
        agency_access(db, agency_id, auth)
        existing = set(db.scalars(select(Contact.phone).where(Contact.agency_id == agency_id)).all())
        for row in rows:
            try:
                number = phone(row.get("phone") or "")
                name = (row.get("name") or "").strip()
                if not name or len(name) > 160:
                    raise ValueError("Name invalid")
                optin = str(row.get("sms_consent", "")).strip().lower() in ("true", "yes", "1")
                source = (row.get("consent_source") or "").strip()
                if optin and not source:
                    raise ValueError("Consent source missing")
                if number in existing:
                    counts["duplicates"] += 1
                    continue
                custom = {k[3:]: str(v or "")[:500] for k, v in row.items() if k and k.startswith("cf_")}
                tags = [t.strip() for t in (row.get("tags") or "").split(";") if t.strip()][:40]
                db.add(Contact(agency_id=agency_id, name=name, phone=number, email=(row.get("email") or "")[:320],
                               tags_json=json.dumps(tags), fields_json=json.dumps(custom),
                               sms_consent=optin, consent_source=source if optin else None,
                               consent_at=now() if optin else None))
                existing.add(number)
                counts["created"] += 1
            except (HTTPException, ValueError, TypeError):
                counts["invalid"] += 1
    return counts


@app.get("/api/agencies/{agency_id}/messages")
def list_messages(agency_id: str, auth=Depends(get_auth)):
    with SessionLocal() as db:
        agency_access(db, agency_id, auth)
        items = db.scalars(select(Message).where(Message.agency_id == agency_id).order_by(Message.created_at.desc()).limit(150)).all()
        return [{"id": m.id, "name": (db.get(Contact, m.contact_id).name if db.get(Contact, m.contact_id) else "Unknown"),
                 "contact_id": m.contact_id, "direction": m.direction, "body": m.body, "status": m.status,
                 "date": m.created_at.isoformat()} for m in items]


@app.post("/api/agencies/{agency_id}/messages/send")
def send_message(agency_id: str, body: SendBody, auth=Depends(get_auth)):
    with SessionLocal.begin() as db:
        agency = agency_access(db, agency_id, auth)
        c = db.get(Contact, body.contact_id)
        if not c or c.agency_id != agency_id:
            raise HTTPException(404, "Contact not found in agency")
        _ensure_sendable(c)
        provider_sid = send_sms(agency, c.phone, body.body)
        m = Message(agency_id=agency_id, contact_id=c.id, direction="outbound", body=body.body,
                    provider_sid=provider_sid, status="submitted")
        db.add(m)
        db.flush()
        return {"id": m.id, "status": m.status}


@app.get("/api/agencies/{agency_id}/workflows")
def list_workflows(agency_id: str, auth=Depends(get_auth)):
    with SessionLocal() as db:
        agency_access(db, agency_id, auth)
        return [{"id": w.id, "name": w.name, "keyword": w.keyword, "add_tag": w.add_tag, "enabled": w.enabled}
                for w in db.scalars(select(Workflow).where(Workflow.agency_id == agency_id)).all()]


@app.post("/api/agencies/{agency_id}/workflows")
def create_workflow(agency_id: str, body: WorkflowBody, auth=Depends(get_auth)):
    with SessionLocal.begin() as db:
        agency_access(db, agency_id, auth, owner=True)
        w = Workflow(agency_id=agency_id, name=body.name.strip(), keyword=body.keyword.strip().lower(), add_tag=body.add_tag.strip())
        db.add(w)
        db.flush()
        return {"id": w.id, "name": w.name}


@app.get("/api/agencies/{agency_id}/campaigns")
def list_campaigns(agency_id: str, auth=Depends(get_auth)):
    with SessionLocal() as db:
        agency_access(db, agency_id, auth)
        return [{"id": c.id, "name": c.name, "body": c.body, "state": c.state} for c in db.scalars(select(Campaign).where(Campaign.agency_id == agency_id)).all()]


@app.post("/api/agencies/{agency_id}/campaigns")
def create_campaign(agency_id: str, body: CampaignBody, auth=Depends(get_auth)):
    with SessionLocal.begin() as db:
        agency_access(db, agency_id, auth, owner=True)
        c = Campaign(agency_id=agency_id, name=body.name.strip(), body=body.body)
        db.add(c)
        db.flush()
        return {"id": c.id, "state": "draft"}


@app.post("/api/agencies/{agency_id}/campaigns/{campaign_id}/queue")
def queue_campaign(agency_id: str, campaign_id: str, auth=Depends(get_auth)):
    with SessionLocal.begin() as db:
        agency = agency_access(db, agency_id, auth, owner=True)
        # Do not allow queuing any bulk sending before compliance verification.
        from .integrations import config
        config(agency)
        campaign = db.get(Campaign, campaign_id)
        if not campaign or campaign.agency_id != agency_id:
            raise HTTPException(404, "Campaign not found")
        if campaign.state != "draft":
            raise HTTPException(409, "Campaign is not a draft")
        contacts = db.scalars(select(Contact).where(Contact.agency_id == agency_id, Contact.sms_consent.is_(True), Contact.opted_out_at.is_(None))).all()
        for c in contacts:
            db.add(Outbox(agency_id=agency_id, campaign_id=campaign.id, contact_id=c.id))
        campaign.state = "queued"
        return {"queued": len(contacts), "note": "Start separate worker to dispatch; opted-out contacts excluded"}


@app.get("/api/agencies/{agency_id}/settings")
def settings(agency_id: str, auth=Depends(get_auth)):
    with SessionLocal() as db:
        a = agency_access(db, agency_id, auth, owner=True)
        return {"phone": a.phone, "twilio_account_sid": a.twilio_account_sid,
                "twilio_messaging_service_sid": a.twilio_messaging_service_sid,
                "twilio_configured": bool(a.twilio_token_enc), "a2p_verified": a.verified_a2p,
                "global_sending_enabled": os.getenv("STRATA_MESSAGING_APPROVED") == "true",
                "forward_phone": a.forward_phone}


@app.post("/api/agencies/{agency_id}/settings/twilio")
def configure_twilio(agency_id: str, body: TwilioBody, auth=Depends(get_auth)):
    if not re.fullmatch(r"AC[0-9a-f]{32}", body.account_sid):
        raise HTTPException(422, "Invalid Twilio account SID")
    if not body.auth_token.strip():
        raise HTTPException(422, "Twilio auth token required")
    with SessionLocal.begin() as db:
        a = agency_access(db, agency_id, auth, owner=True)
        a.phone = phone(body.phone)
        a.twilio_account_sid = body.account_sid
        a.twilio_token_enc = crypt().encrypt(body.auth_token.encode()).decode()
        a.twilio_messaging_service_sid = body.messaging_service_sid or None
        a.forward_phone = phone(body.forward_phone) if body.forward_phone else None
        a.verified_a2p = False  # re-verification required after every credential/number change
    return {"configured": True, "a2p_verified": False}


@app.post("/api/agencies/{agency_id}/ai/draft")
def ai_draft(agency_id: str, body: SendBody, auth=Depends(get_auth)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "AI key has not been configured; no draft generated")
    with SessionLocal() as db:
        agency_access(db, agency_id, auth)
        c = db.get(Contact, body.contact_id)
        if not c or c.agency_id != agency_id:
            raise HTTPException(404, "Contact not found")
        messages = db.scalars(select(Message).where(Message.contact_id == c.id, Message.agency_id == agency_id).order_by(Message.created_at.desc()).limit(8)).all()
        convo = "\n".join(f"{m.direction}: {m.body[:500]}" for m in reversed(messages))
    with httpx.Client(timeout=25) as client:
        r = client.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json={
            "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "messages": [{"role": "system", "content": "Draft a short professional CRM response to a real-estate lead. Do not claim facts you cannot verify. Do not send any message. Respect opt-outs."},
                         {"role": "user", "content": f"Recent conversation:\n{convo}\n\nOperator guidance: {body.body}"}],
            "max_tokens": 200})
    if r.status_code >= 400:
        raise HTTPException(502, "AI provider failed; no draft was generated")
    return {"draft": r.json()["choices"][0]["message"]["content"]}


def public_webhook_url(path):
    base = os.getenv("STRATA_PUBLIC_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise HTTPException(503, "Set STRATA_PUBLIC_URL to the public HTTPS domain")
    return base + path


@app.post("/api/twilio/sms")
async def inbound_sms(request: Request):
    params = dict(await request.form())
    to = params.get("To", "")
    from_number = params.get("From", "")
    text = str(params.get("Body", ""))[:1600]
    with SessionLocal.begin() as db:
        agency = db.scalar(select(Agency).where(Agency.phone == to))
        if not agency:
            raise HTTPException(404, "Unknown destination")
        if not validate_twilio(public_webhook_url("/api/twilio/sms"), params, twilio_token(agency), request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "Invalid Twilio signature")
        c = db.scalar(select(Contact).where(Contact.agency_id == agency.id, Contact.phone == from_number))
        if not c:
            c = Contact(agency_id=agency.id, name=from_number, phone=from_number, sms_consent=False)
            db.add(c)
            db.flush()
        keyword = text.strip().upper()
        if keyword in {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "STOPALL"}:
            c.sms_consent = False
            c.opted_out_at = now()
        elif keyword in {"START", "UNSTOP"}:
            c.sms_consent = True
            c.consent_source = "Inbound explicit START request"
            c.consent_at = now()
            c.opted_out_at = None
        elif keyword == "HELP":
            pass
        else:
            for workflow in db.scalars(select(Workflow).where(Workflow.agency_id == agency.id, Workflow.enabled.is_(True))).all():
                if workflow.keyword in text.lower():
                    tags = json.loads(c.tags_json)
                    if workflow.add_tag not in tags:
                        tags.append(workflow.add_tag)
                        c.tags_json = json.dumps(tags)
        if not db.scalar(select(Message.id).where(Message.provider_sid == params.get("MessageSid"))):
            db.add(Message(agency_id=agency.id, contact_id=c.id, direction="inbound", body=text,
                           provider_sid=params.get("MessageSid"), status="received"))
    return PlainTextResponse("<Response></Response>", media_type="application/xml")


@app.post("/api/twilio/voice/inbound")
async def inbound_voice(request: Request):
    params = dict(await request.form())
    with SessionLocal() as db:
        agency = db.scalar(select(Agency).where(Agency.phone == params.get("To")))
        if not agency or not validate_twilio(public_webhook_url("/api/twilio/voice/inbound"), params, twilio_token(agency), request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "Invalid inbound call")
        if agency.forward_phone:
            response = f'<Response><Dial callerId="{xml_escape(agency.phone)}"><Number>{xml_escape(agency.forward_phone)}</Number></Dial></Response>'
        else:
            response = '<Response><Say>Thank you for calling I Am Strata. Please try again later.</Say></Response>'
        return PlainTextResponse(response, media_type="application/xml")


@app.post("/api/agencies/{agency_id}/calls")
def outbound_call(agency_id: str, body: CallBody, auth=Depends(get_auth)):
    with SessionLocal() as db:
        a = agency_access(db, agency_id, auth)
        c = db.get(Contact, body.contact_id)
        if not c or c.agency_id != agency_id:
            raise HTTPException(404, "Contact not found")
        # The operator must answer on their own phone before Twilio bridges the lead.
        # Both numbers are supplied for direct, user-initiated click-to-call only.
        secret = os.environ.get("STRATA_VOICE_BRIDGE_SECRET")
        if not secret:
            raise HTTPException(503, "Voice bridge secret is not configured")
        import hmac
        import time
        expiry = str(int(time.time()) + 180)
        payload = f"{a.id}|{c.phone}|{expiry}"
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        from urllib.parse import urlencode
        url = public_webhook_url("/api/twilio/voice/bridge") + "?" + urlencode({"aid": a.id, "lead": c.phone, "exp": expiry, "sig": sig})
        sid = create_click_to_call(a, phone(body.operator_phone), c.phone, url)
        db.add(CallRecord(agency_id=agency_id, contact_phone=c.phone, direction="outbound", provider_sid=sid, status="initiated"))
        db.commit()
        return {"status": "initiated", "call_sid": sid}


@app.post("/api/twilio/voice/bridge")
async def bridge_voice(request: Request):
    from urllib.parse import urlencode
    import hmac
    import time
    q = request.query_params
    aid, lead, expiry, sig = q.get("aid", ""), q.get("lead", ""), q.get("exp", ""), q.get("sig", "")
    secret = os.environ.get("STRATA_VOICE_BRIDGE_SECRET", "")
    if not secret or not expiry.isdigit() or int(expiry) < time.time():
        raise HTTPException(403, "Expired voice connection")
    expected = hmac.new(secret.encode(), f"{aid}|{lead}|{expiry}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(403, "Invalid voice connection")
    with SessionLocal() as db:
        agency = db.get(Agency, aid)
        if not agency:
            raise HTTPException(404, "Agency not found")
        params = dict(await request.form())
        url = public_webhook_url("/api/twilio/voice/bridge") + "?" + urlencode(dict(q))
        if not validate_twilio(url, params, twilio_token(agency), request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "Invalid provider signature")
    number = phone(lead)
    return PlainTextResponse(f'<Response><Dial callerId="{xml_escape(agency.phone)}"><Number>{xml_escape(number)}</Number></Dial></Response>', media_type="application/xml")
