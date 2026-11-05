# IAmStrata CRM

Early-stage multi-agency real estate CRM prototype with an Android launcher and a separately prepared full-source archive.

## Repository status

**Android project is committed.** A GitHub Actions workflow builds a debug APK and an unsigned Android App Bundle. The Android app opens an HTTPS URL configured by the operator; **it requires a separately deployed CRM backend**.

**The full CRM server and web application have NOT yet been imported into this repository.** Do not use this repository as a production service. Current Android builds are testing artifacts only.

## Android build

1. Open [Actions](../../actions/workflows/android.yml).
2. Select a successful run.
3. Download `iamstrata-crm-debug-apk` from Artifacts.
4. Install on a test device. When asked for the CRM server URL, enter your own deployed HTTPS endpoint.

The unsigned AAB is **not** Play Store ready. Signed release credentials, a Play Console account, privacy policy, and Play review are required.

## Security / compliance

- Do not commit credentials or reuse the example `Strata123` password.
- Twilio SMS requires valid consent, registration and approved use cases; 10DLC approval cannot be bypassed.
- No Twilio number, SMS campaign, live CRM backend, AI responder or production sub-agency has been deployed by these commits.
- The GitHub repository is currently public; keep personal information, API tokens, and customer data out of it.

## Deployment and Play Store guides

- [Backend deployment instructions](docs/DEPLOYMENT.md)
- [Play Store preparation](docs/PLAY_STORE.md)
- [Source import instructions](docs/GITHUB_UPLOAD.md)

The previously prepared source archive remains available as a ChatGPT conversation download until its contents are imported into GitHub.
