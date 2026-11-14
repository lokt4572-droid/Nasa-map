from django.core.management.base import BaseCommand

from apps.datasets.models import Dataset
from services.dataset_manager import refresh_file_status


class Command(BaseCommand):
    help = "Check that every registered dataset file still exists (marks missing ones MISSING)."

    def handle(self, *args, **opts):
        total = missing = 0
        for ds in Dataset.objects.all():
            total += 1
            if not refresh_file_status(ds):
                missing += 1
                self.stderr.write(self.style.WARNING(f"MISSING  {ds.name}: {ds.file_path}"))
            else:
                self.stdout.write(f"{ds.status:<10} {ds.name}: {ds.file_path}")
        self.stdout.write(f"{total} dataset(s), {missing} missing")
