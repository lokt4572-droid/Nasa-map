"""Download and register the small global Mars DEM used by the demo (MOLA MEGDR 4 px/deg, 2 MB).

Files come from the NASA PDS Geosciences Node and are checked against the MD5 sums the bundle
publishes before import. Idempotent: does nothing when the dataset is already registered and its
files exist. Intended for deployments whose disk may be empty (e.g. after a redeploy).

    python manage.py bootstrap_demo_data
"""
from __future__ import annotations

import hashlib
import urllib.request
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command

from apps.datasets.models import Dataset
from services import http_client

BUNDLE = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived"
FILES = ("megt90n000cb.xml", "megt90n000cb.img")
NAME = "mola-global"


def published_md5() -> dict[str, str]:
    text = http_client.get_bytes("NASA PDS", f"{BUNDLE}/urn-nasa-pds-mgs_mola_topography_derived.md5", timeout=60.0, max_bytes=20_000_000).decode("utf-8", "replace")
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].replace("\\", "/").startswith("meg004/"):
            out[parts[1].split("/")[-1].split("\\")[-1]] = parts[0].lower()
    return out


def md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - integrity check against the archive's published MD5, not security
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Download (MD5-checked) and register the MOLA MEGDR 4 px/deg global DEM for the demo."

    def handle(self, *args, **opts):
        target = Path(settings.MARS_DATA_DIR) / "raw" / "mola"
        existing = Dataset.objects.filter(name=NAME, status=Dataset.Status.VALID).first()
        if existing and all((target / f).is_file() for f in FILES):
            self.stdout.write(f"{NAME} already registered; nothing to do.")
            return
        target.mkdir(parents=True, exist_ok=True)
        sums = published_md5()
        for f in FILES:
            dest = target / f
            if not (dest.is_file() and md5(dest) == sums.get(f)):
                self.stdout.write(f"Downloading {f} from NASA PDS…")
                req = urllib.request.Request(f"{BUNDLE}/meg004/{f}", headers={"User-Agent": http_client.user_agent()})
                with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - fixed PDS URL
                    dest.write_bytes(resp.read(10_000_000))
            if md5(dest) != sums.get(f):
                dest.unlink(missing_ok=True)
                raise CommandError(f"MD5 of {f} does not match the PDS manifest; file removed")
        call_command("import_dem", "--file", str(target / FILES[0]), "--name", NAME, "--source", "NASA PDS Geosciences Node",
                     "--instrument", "MGS MOLA", "--product-id", "megt90n000cb", "--license", "NASA PDS public data",
                     stdout=StringIO(), stderr=StringIO())
        self.stdout.write(self.style.SUCCESS(f"Registered {NAME} (MD5 verified against the PDS manifest)."))
