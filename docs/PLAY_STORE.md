# Android and Google Play release plan

## Current build

A native Android WebView activity securely opens your hosted IAmStrata CRM with an explicit HTTPS server setup screen, secure cookies, and a CSV file chooser. This app **does not send SMS using device permissions**. All communications are handled server-side via authorized Twilio APIs.

The Android project is at `android/`; app id `com.iamstrata.crm`; min API 26; **target Android API 36** (Google Play requirement for new apps as of August 31, 2026). No `SEND_SMS`, `READ_SMS`, `CALL_PHONE` or `READ_CALL_LOG` permissions are declared.

## Build from GitHub on phone

1. Open **Actions → Android - debug APK and unsigned AAB → Run workflow**.
2. Wait for the build to complete. Download `iamstrata-crm-debug-apk` from **Artifacts**.
3. Install the APK only on your own test phone. Choose **Connect workspace** and enter the fully deployed HTTPS CRM server URL.
4. The workflow also emits an **unsigned AAB** for compile verification. It is NOT directly eligible for Play Store upload. Do not upload unsigned bundles.

## Publish on Google Play

1. Create your official [Google Play Console](https://play.google.com/console/) developer account. Google charges a one-time account registration fee. Complete the required identity verification.
2. Host the real CRM on HTTPS and publish a legitimate privacy policy, terms, account deletion and support contact; complete the Data safety form accurately. Ensure the app has meaningful functionality for reviewers.
3. Arrange the app signing keystore securely in a secret store. Keep the keystore and upload key outside public GitHub; enroll in Google Play App Signing. Configure GitHub secrets `STRATA_UPLOAD_KEYSTORE_BASE64`, `STRATA_KEYSTORE_PASSWORD`, `STRATA_KEY_ALIAS`, and `STRATA_KEY_PASSWORD`, then run **Android - signed Play AAB**. The job verifies the signed AAB; retain the key long-term. Alternatively, sign in Android Studio.
4. Prepare original screenshots (phone), proper store icon/feature graphic, app descriptions and production account access for reviewers; use the app's actual features, not marketing simulations.
5. Submit the Android App Bundle to internal testing, then closed testing as appropriate for the developer account. Meet any eligibility/testing period requirements that apply to your Play developer account.
6. Obtain required policy/permission approvals and submit production release for review. Publication is only successful after Google Play's approval. Hosting, SMS/calling setup and carrier approvals are separate.

**Not completed:** no Google account enrollment, signing key, signed AAB, uploaded listing, closed test or public release. An APK does not automatically appear on Google Play.

Policy references:
- https://support.google.com/googleplay/android-developer/answer/11926878
- https://support.google.com/googleplay/android-developer/answer/6112435
- https://support.google.com/googleplay/android-developer/answer/10208820