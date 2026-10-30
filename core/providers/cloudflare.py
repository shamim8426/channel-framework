"""Free-tier image provider (Cloudflare Workers AI). Daily quota: HTTP 429 -> ProviderUnavailable -> fallback chain moves on.
Needs env CLOUDFLARE_ACCOUNT_ID and the env var named by api_key_env. Not exercised by tests."""
import base64
import os
from pathlib import Path

import requests

from ..secrets import api_key
from .base import ImageProvider, ProviderUnavailable, Result


class CloudflareImage(ImageProvider):
    name = "cloudflare"

    def __init__(self, conf: dict):
        self.model, self.env = conf.get("model", "@cf/black-forest-labs/flux-1-schnell"), conf.get("api_key_env")

    def generate(self, prompt, out_path, size=(1280, 720)):
        acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not acct:
            raise ProviderUnavailable("CLOUDFLARE_ACCOUNT_ID not set")
        r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{self.model}",
                          headers={"Authorization": f"Bearer {api_key(self.env)}"}, json={"prompt": prompt}, timeout=180)
        if r.status_code == 429:
            raise ProviderUnavailable("cloudflare free daily quota used up")
        r.raise_for_status()
        data = r.json().get("result", {}).get("image")
        if not data:
            raise RuntimeError("cloudflare returned no image")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(base64.b64decode(data))
        return Result(Path(out_path), 0.0, self.name)
