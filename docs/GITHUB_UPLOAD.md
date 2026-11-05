# Import the project into GitHub

The owner repository is [ronsumay2019-code/Strata-CRM](https://github.com/ronsumay2019-code/Strata-CRM).

The assistant's connected GitHub integration can currently read the repository but received HTTP 403 `Resource not accessible by integration` for both creating a file and creating a Git blob. Repository metadata claiming user push permission does not override the app's granted write scope. No code has been uploaded until a successful commit can be verified.

## Easiest method: computer

1. Download `IAmStrata-CRM-source.zip` from the conversation and extract it.
2. Open the repository in GitHub on a computer and select **Add file → Upload files** (for a genuinely empty repo, choose **uploading an existing file**). Drag the **extracted contents**, not the ZIP, into the browser; verify nested directories, particularly `.github/workflows`, are included. Commit to `main`.
3. Check for `README.md`, `server/app/main.py`, `web/index.html`, `android/app/build.gradle` and `.github/workflows/android.yml` in the repo.
4. Open **Actions → Android - debug APK and unsigned AAB → Run workflow**. If the test passes, get the debug APK from the workflow artifacts. GitHub Actions must be enabled for the repository.

## Alternative: GitHub Codespaces from a phone

1. Using the GitHub website, upload the ZIP file into your repository and commit it (this is not an app installation).
2. Create a GitHub Codespace from the repository and open its integrated terminal. Check plan/quota costs before doing so.
3. Run `unzip -o IAmStrata-CRM-source.zip -d . && rm IAmStrata-CRM-source.zip && git add -A && git commit -m "feat: import IAmStrata CRM source" && git push origin main`.
4. Refresh GitHub and run Android Actions. Configure production hosting separately.

## GitHub app access

Installation configuration page for the currently connected GitHub App: https://github.com/settings/installations/175290391

Reconnecting or granting the repository to the app does not necessarily grant `Contents: write`: the app must actually request and receive that permission. The currently observed requests failed. Never paste GitHub personal access tokens or passwords into chat to work around this.