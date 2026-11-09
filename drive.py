from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import GOOGLE_SA_INFO

FOLDER = "application/vnd.google-apps.folder"
MEDIA_OK = ("video/", "image/jpeg", "image/png", "image/webp")
_svc = None


def svc():
    global _svc
    if _svc is None:
        creds = service_account.Credentials.from_service_account_info(
            GOOGLE_SA_INFO, scopes=["https://www.googleapis.com/auth/drive"])
        _svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _svc


def _list(q):
    res = svc().files().list(q=q, fields="files(id,name,mimeType,size)", orderBy="name_natural",
                             pageSize=100, supportsAllDrives=True,
                             includeItemsFromAllDrives=True).execute()
    return res.get("files", [])


def create_folder(name, parent):
    body = {"name": name, "mimeType": FOLDER, "parents": [parent]}
    return svc().files().create(body=body, fields="id", supportsAllDrives=True).execute()["id"]


def find_folder(prefix, parent):
    hits = _list(f"'{parent}' in parents and mimeType='{FOLDER}' "
                 f"and name contains '{prefix}' and trashed=false")
    hits = [h for h in hits if h["name"].startswith(prefix)]
    return hits[0]["id"] if hits else ""


def list_media(folder_id):
    files = _list(f"'{folder_id}' in parents and trashed=false")
    return [f for f in files if f["mimeType"].startswith(MEDIA_OK)]


def download(file_id, dest: Path):
    req = svc().files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req, chunksize=50 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
    return dest

