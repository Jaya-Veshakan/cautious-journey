# Google Docs Static Blog (GitHub Pages)

A static blog generator that turns Google Docs in one Drive folder into separate pages. Publishing is manual: run **Actions → Publish Google Docs blog → Run workflow**.

## How incremental publishing works

- The script stores a manifest in `site/_data/manifest.json`.
- If a document's Google Drive `modifiedTime` has not changed, its article HTML is not re-exported.
- New documents get new article pages.
- Edited documents update their existing article page.
- The homepage and sitemap are refreshed.
- If a document is removed from the configured Drive folder, only its previously managed article page is removed.
- Generated `site/` files are committed to the repository so the next workflow run can compare against the previous state.

## 1. Create a public repository

Create a GitHub repository, for example `drive-blog`, and add the files from this starter project. Keep the repository public for GitHub Pages on the GitHub Free plan.

## 2. Create and configure a Google service account

1. Open the Google Cloud Console and create/select a project.
2. Enable **Google Drive API**.
3. Create a service account and generate a JSON key.
4. Copy the service account email address.
5. Share your blog's Google Drive folder with that email as **Viewer**.
6. Put only the Google Docs you want to publish in that folder. The docs may also be publicly viewable; the service account needs folder access for reliable API listing and export.

Treat the JSON key as a password. Do not add it to this repository or a public issue.

## 3. Add GitHub secrets and variable

In the repository, open **Settings → Secrets and variables → Actions**.

Add these repository secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`: paste the complete service-account JSON key.
- `DRIVE_FOLDER_ID`: the ID from the folder URL `https://drive.google.com/drive/folders/FOLDER_ID`.

Add this repository variable:

- `SITE_URL`: the full Pages URL with trailing slash, for example `https://YOUR-USERNAME.github.io/drive-blog/`.

Use the actual account and repository values. Do not paste credentials into source files.

## 4. Enable Pages

Open **Settings → Pages → Build and deployment** and set **Source** to **GitHub Actions**.

Under **Settings → Actions → General → Workflow permissions**, ensure workflows can write repository contents. The workflow needs this to commit the generated pages.

## 5. Publish

1. Open the repository's **Actions** tab.
2. Select **Publish Google Docs blog**.
3. Click **Run workflow** and confirm.
4. Open the run to see whether documents were `UPDATED`, `UNCHANGED`, or `REMOVED`.
5. After a successful run, open the Pages URL.

The first run exports every document. Later runs only re-export changed or new documents, while leaving unchanged article HTML files alone.

## Important limitations

- This first version uses the GitHub Actions tab as the manual Publish control. It does not provide a public website admin button; securely triggering GitHub Actions from a web page requires an authenticated server-side component or another carefully designed identity flow.
- Anything deployed to GitHub Pages is public. Do not publish private or sensitive content.
- Google Docs export HTML may not preserve every layout or embedded object exactly.
- Review exported pages before sharing the website publicly.
- GitHub Actions and GitHub Pages have plan-specific usage and size limits.
