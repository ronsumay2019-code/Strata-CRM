# Deploy IAmStrata CRM

## Status

This repository contains a working application foundation and native Android WebView client. The backend must be hosted to use the app on a phone. No Twilio number, approved A2P campaign, production database, app signing key, or Play Console listing has been created by this codebase.

## Server local development

1. Create a Python 3.12+ virtualenv; `pip install -r server/requirements.txt`.
2. From `server/`, set `STRATA_ADMIN_EMAIL`, a **unique** `STRATA_ADMIN_PASSWORD` (14+ chars), and `STRATA_ENCRYPTION_KEY` (run `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`). Add `STRATA_VOICE_BRIDGE_SECRET` using 32+ cryptographically random characters for voice calls. Never commit these values.
3. Set `DATABASE_URL=sqlite:///./strata.db` for local testing. Use managed PostgreSQL for production.
4. From `server/`, execute `python -m app.bootstrap` exactly once. This provisions the real initial IAmStrata agency and owner, with no sample leads.
5. Run `uvicorn app.main:app --reload` from `server/`, then open `http://127.0.0.1:8000`.
6. Run tests: `cd server && python -m pytest -q`; syntax check: `node --check web/app.js`.

## Production (Render or equivalent)

1. Connect the GitHub repository to Render using the Dockerfile or `render.yaml`; choose a paid/persistent Postgres instance to keep data safe. Do not rely on ephemeral container filesystem storage. Review provider pricing before enabling billable services.
2. Enter production secrets in the host, not GitHub: `STRATA_ENV=production`, `DATABASE_URL` (PostgreSQL), `STRATA_ADMIN_EMAIL`, `STRATA_ADMIN_PASSWORD`, `STRATA_ENCRYPTION_KEY`, `STRATA_PUBLIC_URL=https://crm.example.com`, `STRATA_VOICE_BRIDGE_SECRET`, optional `OPENAI_API_KEY`.
3. Initialize the owner once in a Render shell or one-time job: `cd /app/server && python -m app.bootstrap`. Confirm HTTPS, `/healthz`, login, contact isolation and backups.
4. If sending campaigns, run an **additional dedicated single worker** service with `PYTHONPATH=/app/server` and command `cd /app/server && python -m app.worker`. Worker claims jobs and throttles sends. Messages with uncertain delivery are not automatically retried.
5. Create agency workspaces from the Overview screen (up to 3 additional agencies). Configure separate Twilio account credentials in each workspace. Phone numbers are never purchased automatically.
6. In the Twilio Console configure the inbound Messaging webhook as `https://YOUR_DOMAIN/api/twilio/sms` (HTTP POST), and incoming Voice webhook as `https://YOUR_DOMAIN/api/twilio/voice/inbound` (HTTP POST). Check your Twilio number permissions, geo calling and messaging use cases.
7. Complete the legal brand and campaign A2P/10DLC registration for each applicable sender. Do **not** try to bypass it. After confirming active approval in the actual Twilio console, use `python -m app.verify_a2p --agency-id AGENCY_UUID --campaign-sid QE... --confirmed`. Then set `STRATA_MESSAGING_APPROVED=true` in production. Both gates are required; Twilio/carrier enforces approval independently.
8. Confirm real SMS and voice call operations on approved, consenting test numbers, inbound opt-outs, retries/duplicate receipts and deliverability. These real provider checks have **not** been done here.

## Important safeguards and current limitations

- Passwords are hashed with Argon2, session cookies use HttpOnly + SameSite=Lax and `Secure` in production, mutating routes require a CSRF token. Add distributed login throttling, password reset/MFA, centralized audit logs, professional monitoring, migrations, retention policies, and security review before large-scale or regulated production use.
- Tenant checks apply to APIs. Initial version bootstraps one owner account; delegated member invitations and advanced permission controls are not yet implemented.
- Contacts only become SMS eligible when accompanied by documented permission. STOP and related keywords suppress future SMS. Automated keyword branches only add tags, not messages.
- Twilio credentials are encrypted at rest with Fernet. Secure the encryption key and rotate carefully. Ensure a privacy policy, service agreements, data removal process and appropriate messaging consent records.
- The current UI supports a rule trigger and tag action, not a drag/drop full GoHighLevel visual builder. Campaigns dispatch from a separate worker; there is no schedule or automatic reply yet. AI is **draft-only**, requiring review before send.
- Inbound voice forwards to the agency's configured E.164 number. Outbound uses Twilio click-to-call to call the operator first; costs and regional restrictions apply. Configure voice webhooks, phone numbers and consent before use.
- Webhook URLs must match the configured `STRATA_PUBLIC_URL` exactly for signature validation. Use HTTPS, and never disable signature verification to make a webhook work.
- Realtime inbox via polling/websocket, delivery receipts, team invitations, subscription billing, advanced reports and lead deduplication logic beyond phone matching are future work.