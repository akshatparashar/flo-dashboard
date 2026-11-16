# Sample Production Dashboard

A Streamlit dashboard for sample order, designer, client, production, delay, and fabric/vendor analysis.

## Dashboard Sections

- Executive Overview
- Designer Dashboard
- Client Dashboard
- Production Process Dashboard
- Fabric & Vendor Tracking
- Searchable Order Details
- CSV export of filtered order data

## Technologies

- Python
- Streamlit
- Pandas
- Plotly
- Google Sheets API
- GitHub
- Streamlit Community Cloud

## Google Sheet Connection

The app reads data from a private Google Sheet using a Google Cloud service account.

### Setup

1. Create or select a project in Google Cloud Console.
2. Enable the Google Sheets API.
3. Create a service account and generate its JSON key.
4. Share the Google Sheet with the service account's email address as Viewer.
5. Configure the service account credentials in Streamlit Secrets.

Keep the source Google Sheet private. Never commit service-account credentials, private keys, or `secrets.toml` to GitHub.

## Run Locally on Windows

Open PowerShell in the project folder and run:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app will normally open at `http://localhost:8501`.

## Deploy to Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, `README.md`, and `.gitignore` to GitHub.
2. Open Streamlit Community Cloud.
3. Sign in and create a new app.
4. Select the GitHub repository `design355/sample-production-dashboard`.
5. Select the `main` branch and `app.py`.
6. Add the Google service-account credentials under the app's Settings → Secrets.
7. Deploy and test the app.

Deployment guide:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

Secrets guide:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

## Important Data Privacy Note

The source Google Sheet can remain private while the dashboard is deployed separately.

However, if the dashboard is made public, data displayed in the app may be visible to anyone who can access it. Do not publish confidential client, order, or business data without authorization.

## Data Mapping Note

The app attempts to match columns by their header names. If a header cannot be matched, fallback column positions are used.

The original Google Apps Script has inconsistent definitions for some production columns across its dashboards. Verify the production, received, pending, and delay columns against the actual sheet before relying on those metrics.
