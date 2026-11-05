"""Operator-only manual approval recording after independent Twilio Console verification."""
import argparse
from sqlalchemy import select
from .db import Agency, SessionLocal, initialize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agency-id', required=True)
    parser.add_argument('--campaign-sid', required=True, help='Approved Twilio campaign SID; independently verify in console first')
    parser.add_argument('--confirmed', action='store_true', help='Attest verified approval in Twilio Console')
    args = parser.parse_args()
    if not args.confirmed or not args.campaign_sid.startswith('QE'):
        raise SystemExit('Require --confirmed and actual approved campaign SID (QE...)')
    initialize()
    with SessionLocal.begin() as db:
        a = db.get(Agency,args.agency_id)
        if not a or not a.twilio_account_sid or not a.twilio_token_enc:
            raise SystemExit('Agency Twilio integration is not configured')
        a.verified_a2p=True
    print('Recorded human-confirmed approval. Carrier approval is still independently enforced by Twilio.')


if __name__ == '__main__':
    main()
