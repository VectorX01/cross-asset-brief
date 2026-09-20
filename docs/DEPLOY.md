# Deployment

One-time setup to get the daily workflow (`.github/workflows/daily.yml`)
publishing to a gated, private Cloudflare Pages site. Run these yourself —
they touch your own Cloudflare and GitHub accounts.

## 1. Get a FRED API key

Register (free) at <https://fredaccount.stlouisfed.org/apikeys> and create a
key. This is the `FRED_API_KEY` secret below.

## 2. Create the Cloudflare Pages project

In the Cloudflare dashboard, under **Workers & Pages**, create a Pages
project named `cross-asset-brief` and choose **Direct Upload** (no git
integration — the GitHub Action pushes the built `dist/` directory itself).

## 3. Create an API token

Under **My Profile → API Tokens**, create a token scoped to the
**Cloudflare Pages: Edit** permission only. Copy the account id from the
dashboard sidebar while you're there.

## 4. Add the three GitHub secrets

In the repository, under **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `FRED_API_KEY` | the key from step 1 |
| `CLOUDFLARE_API_TOKEN` | the token from step 3 |
| `CLOUDFLARE_ACCOUNT_ID` | the account id from step 3 |

## 5. Run the workflow and verify

Push this repository, then trigger the workflow manually from the Actions
tab ("Run workflow"). Expect a green run and the site live at
`https://cross-asset-brief.pages.dev`. Open it on a phone and confirm the
two-column grid collapses to one column and stays readable.

## 6. Gate the site with Cloudflare Access

The built page has no auth of its own — access control is Cloudflare's job,
not the app's. In the Cloudflare dashboard, under **Zero Trust → Access →
Applications**, add a self-hosted application for `cross-asset-brief.pages.dev`
with one policy: action **Allow**, rule **Emails**, value your own email
address. Free for up to 50 users.

Expect opening the URL in a private browser window to now prompt for a
one-time code by email, rather than showing the brief directly.
