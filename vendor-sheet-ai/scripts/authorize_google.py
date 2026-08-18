"""Run this once to grant the app access to Google Docs/Drive.

Opens your browser to sign in and click Allow, then saves a reusable
token to token.json (auto-refreshed afterwards, no need to run this again
unless token.json is deleted or scopes change).
"""
from __future__ import annotations

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print("Authorized. Saved token.json")


if __name__ == "__main__":
    main()
