"""Deployment settings and public demo protection."""
import hashlib
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from config.settings import database_from_url

from .raster_fixtures import TempDirMixin, requires_raster


class DatabaseUrlTests(SimpleTestCase):
    def test_postgres_url(self):
        d = database_from_url("postgres://user%40x:p%3Ass@db.example.com:5433/mars?sslmode=require")
        self.assertEqual(d["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((d["NAME"], d["USER"], d["PASSWORD"], d["HOST"], d["PORT"]), ("mars", "user@x", "p:ss", "db.example.com", "5433"))
        self.assertEqual(d["OPTIONS"], {"sslmode": "require"})

    def test_other_schemes_are_refused(self):
        with self.assertRaises(ValueError):
            database_from_url("mysql://u:p@h/db")


@override_settings(PUBLIC_READ_ONLY=True, WRITE_API_TOKEN="op-secret")
class PublicReadOnlyTests(TestCase):
    MISSION = {"name": "Demo", "description": "", "status": "PLANNED"}

    def test_reads_work_and_shared_writes_are_refused(self):
        c = APIClient()
        self.assertEqual(c.get("/api/v1/health/").status_code, 200)
        self.assertEqual(c.get("/api/v1/missions/").status_code, 200)
        r = c.post("/api/v1/missions/", self.MISSION, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"]["code"], "READ_ONLY_DEMO")
        for method, path in (("delete", "/api/v1/missions/1/"), ("patch", "/api/v1/hazards/1/"), ("post", "/api/v1/datasets/register/"), ("post", "/api/v1/hazards/")):
            self.assertEqual(getattr(c, method)(path, {}, format="json").status_code, 403, path)

    def test_computations_stay_available(self):
        c = APIClient()
        # 400 = reached the view (validation), not blocked by the read-only guard
        self.assertNotEqual(c.post("/api/v1/routes/plan/", {}, format="json").status_code, 403)
        self.assertNotEqual(c.post("/api/v1/ai/interpret/", {"instruction": "slope 10 degrees"}, format="json").status_code, 403)
        self.assertNotEqual(c.post("/api/v1/routes/hazards/derive/", {}, format="json").status_code, 403)

    def test_operator_token_allows_writes(self):
        c = APIClient()
        self.assertEqual(c.post("/api/v1/missions/", self.MISSION, format="json", HTTP_X_API_TOKEN="wrong").status_code, 403)
        self.assertEqual(c.post("/api/v1/missions/", self.MISSION, format="json", HTTP_X_API_TOKEN="op-secret").status_code, 201)

    @override_settings(WRITE_API_TOKEN="")
    def test_empty_token_never_matches(self):
        self.assertEqual(APIClient().post("/api/v1/missions/", self.MISSION, format="json", HTTP_X_API_TOKEN="").status_code, 403)


class ReadOnlyOffByDefaultTests(TestCase):
    def test_local_default_allows_writes(self):
        self.assertEqual(APIClient().post("/api/v1/missions/", {"name": "Local", "description": "", "status": "PLANNED"}, format="json").status_code, 201)


@requires_raster
class BootstrapTests(TempDirMixin, TestCase):
    def test_md5_mismatch_is_refused_and_file_removed(self):
        from apps.datasets.management.commands import bootstrap_demo_data as boot

        class Resp:
            def __init__(self, data):
                self.data = data
            def read(self, n):
                return self.data
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        with override_settings(MARS_DATA_DIR=self.tmp), \
             mock.patch.object(boot, "published_md5", return_value={f: "0" * 32 for f in boot.FILES}), \
             mock.patch.object(boot.urllib.request, "urlopen", return_value=Resp(b"not the real file")):
            with self.assertRaises(CommandError):
                call_command("bootstrap_demo_data", stdout=StringIO())
        self.assertFalse((Path(self.tmp) / "raw" / "mola" / boot.FILES[0]).exists())

    def test_existing_files_with_matching_md5_are_not_downloaded(self):
        from apps.datasets.management.commands import bootstrap_demo_data as boot

        real = Path(__file__).resolve().parents[2] / "data" / "mars" / "raw" / "mola"
        if not all((real / f).is_file() for f in boot.FILES):
            self.skipTest("MOLA MEGDR not present in this checkout")
        dest = Path(self.tmp) / "raw" / "mola"
        dest.mkdir(parents=True)
        sums = {}
        for f in boot.FILES:
            (dest / f).write_bytes((real / f).read_bytes())
            sums[f] = hashlib.md5((real / f).read_bytes()).hexdigest()  # noqa: S324
        with override_settings(MARS_DATA_DIR=self.tmp), mock.patch.object(boot, "published_md5", return_value=sums), \
             mock.patch.object(boot.urllib.request, "urlopen", side_effect=AssertionError("must not download")):
            out = StringIO()
            call_command("bootstrap_demo_data", stdout=out)
        self.assertIn("Registered mola-global", out.getvalue())
        from apps.datasets.models import Dataset

        self.assertEqual(Dataset.objects.get(name="mola-global").status, "VALID")
