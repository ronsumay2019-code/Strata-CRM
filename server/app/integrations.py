"""Twilio REST and incoming signature verification. Never store tokens in source control."""
import base64
import hashlib
import hmac
import os
import urllib.parse
import httpx
from fastapi import HTTPException
from .security import crypt


def config(agency):
    if not agency.phone or not agency.twilio_account_sid or not agency.twilio_token_enc:
        raise HTTPException(409, "Twilio account, number and credentials must be configured")
    if not agency.verified_a2p or os.environ.get("STRATA_MESSAGING_APPROVED") != "true":
        raise HTTPException(409, "SMS sending disabled pending A2P/10DLC compliance verification")
    return agency.twilio_account_sid, crypt().decrypt(agency.twilio_token_enc.encode()).decode()


def send_sms(agency, to, body):
    sid, token = config(agency)
    data = {"To": to, "Body": body}
    if agency.twilio_messaging_service_sid:
        data["MessagingServiceSid"] = agency.twilio_messaging_service_sid
    else:
        data["From"] = agency.phone
    with httpx.Client(timeout=20) as client:
        r = client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, token), data=data)
    if r.status_code >= 400:
        raise HTTPException(502, f"Twilio messaging request failed ({r.status_code})")
    return r.json().get("sid")


def validate_twilio(url, params, token, supplied):
    if not supplied:
        return False
    raw = url + "".join(k + str(v) for k, v in sorted(params.items()))
    signature = base64.b64encode(hmac.new(token.encode(), raw.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(signature, supplied)


def twilio_token(agency):
    if not agency.twilio_token_enc:
        raise HTTPException(409, "Twilio not configured")
    return crypt().decrypt(agency.twilio_token_enc.encode()).decode()


def create_click_to_call(agency, operator_phone, lead_phone, webhook_url):
    sid, token = agency.twilio_account_sid, twilio_token(agency)
    if not sid or not agency.phone:
        raise HTTPException(409, "Twilio voice setup is incomplete")
    with httpx.Client(timeout=20) as client:
        r = client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", auth=(sid, token), data={"To":operator_phone, "From":agency.phone,"Url":webhook_url,"Method":"POST"})
    if r.status_code >= 400:
        raise HTTPException(502, f"Twilio calling request failed ({r.status_code})")
    return r.json().get("sid")
