from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_PATH = "token.json"


def get_credentials() -> Credentials:
    creds = Credentials.from_authorized_user_file(TOKEN_PATH)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def docs_service():
    return build("docs", "v1", credentials=get_credentials())


def drive_service():
    return build("drive", "v3", credentials=get_credentials())
