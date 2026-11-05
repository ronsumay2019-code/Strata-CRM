"""Run as separate worker process: python -m app.worker. One queue row is claimed before each provider request."""
import os
import time
from sqlalchemy import select
from .db import Agency, Campaign, Contact, Message, Outbox, SessionLocal, initialize
from .integrations import send_sms


def process_one():
    with SessionLocal.begin() as db:
        row = db.scalar(select(Outbox).where(Outbox.state == "queued").order_by(Outbox.created_at).with_for_update(skip_locked=True).limit(1))
        if not row:
            return False
        row.state = "sending"
        row.attempts += 1
        record_id = row.id
    with SessionLocal.begin() as db:
        row = db.get(Outbox, record_id)
        agency, contact, campaign = db.get(Agency, row.agency_id), db.get(Contact, row.contact_id), db.get(Campaign, row.campaign_id)
        if not agency or not contact or not campaign or not contact.sms_consent or contact.opted_out_at:
            row.state = "skipped"
            row.last_error = "Contact no longer eligible for messaging"
            return True
        try:
            sid = send_sms(agency, contact.phone, campaign.body)
        except Exception as exc:
            # Never automatically retry an ambiguous provider failure (to avoid duplicate sends).
            row.state = "failed"
            row.last_error = str(exc)[:500]
            return True
        db.add(Message(agency_id=agency.id, contact_id=contact.id, direction="outbound", body=campaign.body, provider_sid=sid, status="submitted"))
        row.state = "sent"
    return True


def main():
    initialize()
    print("IAmStrata outbox worker online")
    while True:
        if process_one():
            time.sleep(float(os.getenv("STRATA_SEND_INTERVAL_SECONDS", "2")))
        else:
            time.sleep(5)


if __name__ == "__main__":
    main()
