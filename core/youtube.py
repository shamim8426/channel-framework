"""YouTube upload with a channel-ID guard.

Safety contract (tested): before ANY upload the authenticated channel ID must equal channel config `youtube_channel_id`.
A mismatch (or the REPLACE_ME placeholder in live mode) raises GuardError and nothing is uploaded.

Three clients share one small interface:
    RealYouTube(store)      live (needs requirements-youtube.txt + secrets/<ref>/client_secret.json, token.json)
    DryRunYouTube(cfg)      default: no network, reports the configured channel id, records what WOULD be sent
    FakeYouTube(channel_id) tests: records calls, configurable id
"""
import datetime as dt
import json
from pathlib import Path

from .config import ChannelConfig
from .errors import GuardError, SecretsError
from .secrets import SecretStore

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]


class DryRunYouTube:
    live = False

    def __init__(self, cfg: ChannelConfig):
        self.cfg, self.calls = cfg, []

    def my_channel_id(self) -> str:
        return self.cfg["youtube_channel_id"]

    def upload_video(self, path, body, thumbnail=None):
        self.calls.append(("upload", str(path), body))
        return {"id": "DRYRUN-" + __import__("hashlib").sha1((str(path) + body["snippet"]["title"]).encode()).hexdigest()[:8], "dry_run": True}

    def add_to_playlist(self, video_id, playlist_id):
        self.calls.append(("playlist", video_id, playlist_id))


class FakeYouTube(DryRunYouTube):
    """Test double. uploads/playlists are recorded; channel_id decides whether the guard passes."""

    def __init__(self, channel_id: str):
        self._id, self.calls = channel_id, []

    def my_channel_id(self) -> str:
        return self._id

    @property
    def uploads(self):
        return [c for c in self.calls if c[0] == "upload"]


class RealYouTube:
    live = True

    def __init__(self, store: SecretStore):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as e:
            raise SecretsError("live YouTube needs: pip install -r requirements-youtube.txt") from e
        token = store.require("token")
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json())
        self.yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    def my_channel_id(self) -> str:
        items = self.yt.channels().list(part="id", mine=True).execute().get("items", [])
        if not items:
            raise GuardError("the logged-in Google account has no YouTube channel")
        return items[0]["id"]

    def upload_video(self, path, body, thumbnail=None):
        from googleapiclient.http import MediaFileUpload
        req = self.yt.videos().insert(part="snippet,status", body=body,
                                      media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True))
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        if thumbnail:
            self.yt.thumbnails().set(videoId=resp["id"], media_body=MediaFileUpload(str(thumbnail))).execute()
        return resp

    def add_to_playlist(self, video_id, playlist_id):
        self.yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": playlist_id, "resourceId": {
            "kind": "youtube#video", "videoId": video_id}}}).execute()


def authorize(cfg: ChannelConfig, store: SecretStore):  # pragma: no cover - interactive, live only
    """One-time browser login that writes secrets/<ref>/token.json. Log in with the channel that matches youtube_channel_id."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(store.require("client_secret")), SCOPES)
    creds = flow.run_local_server(port=0)
    store.ensure_dir()
    store.path("token").write_text(creds.to_json())
    return store.path("token")


def guard_channel(api, cfg: ChannelConfig, live: bool = False) -> str:
    want = cfg["youtube_channel_id"]
    if live and cfg.is_placeholder_channel_id:
        raise GuardError("youtube_channel_id is still REPLACE_ME in channel config: set the real channel ID before a live upload")
    got = api.my_channel_id()
    if got != want:
        raise GuardError(f"WRONG CHANNEL: authenticated as {got}, but channel '{cfg.slug}' is configured for {want}. "
                         f"Nothing was uploaded. Delete secrets/{cfg['credentials_ref']}/token.json and log in with the right channel.")
    return got


def build_job(cfg: ChannelConfig, video: Path, kind: str, title: str, description: str, tags=None, thumbnail=None,
              slot=None) -> dict:
    yt = cfg["youtube"]
    suffix = yt.get("title_suffix", "")
    full_title = (title if not suffix or title.endswith(suffix) else f"{title} {suffix}").strip()[:100]
    body = {"snippet": {"title": full_title, "description": description, "tags": (tags or []) + yt.get("default_tags", []),
                        "categoryId": yt["category_id"], "defaultLanguage": cfg["language"],
                        "defaultAudioLanguage": cfg["language"]},
            "status": {"privacyStatus": yt["privacy"], "selfDeclaredMadeForKids": yt["made_for_kids"],
                       "containsSyntheticMedia": yt["contains_synthetic_media"]}}
    if slot is not None and yt.get("auto_publish"):
        if slot.action == "now":
            body["status"]["privacyStatus"] = "public"
        else:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = slot.at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"kind": kind, "video": str(video), "thumbnail": str(thumbnail) if thumbnail else None, "body": body,
            "planned_slot": None if slot is None else {"action": slot.action, "at_utc": slot.at.isoformat()}}


def upload(cfg: ChannelConfig, api, job: dict, live: bool = False) -> dict:
    """Guard first, then upload (+ playlist). Returns the result record (also what gets written to upload_result.json)."""
    guard_channel(api, cfg, live)
    resp = api.upload_video(job["video"], job["body"], job.get("thumbnail"))
    for name, pid in cfg["youtube"].get("playlists", {}).items():
        if job["kind"] in ("long",) and name:
            api.add_to_playlist(resp["id"], pid)
    result = {"video_id": resp["id"], "kind": job["kind"], "dry_run": bool(resp.get("dry_run")), "privacy": job["body"]["status"]["privacyStatus"],
              "planned_slot": job["planned_slot"], "uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "studio_action": None}
    if not cfg["youtube"].get("auto_publish") and job["planned_slot"]:
        result["studio_action"] = (f"STUDIO ACTION: video {resp['id']} is {result['privacy']}. Watch it, then "
                                   f"{'publish now' if job['planned_slot']['action'] == 'now' else 'schedule it for ' + job['planned_slot']['at_utc']}.")
    return result


def make_client(cfg: ChannelConfig, ws, live: bool):
    return RealYouTube(SecretStore(ws, cfg["credentials_ref"])) if live else DryRunYouTube(cfg)


def save_result(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
