"""
core/management/commands/check_disk_space.py

Django management command for monitoring media folder disk usage.

Usage:
    python manage.py check_disk_space

Schedule via Windows Task Scheduler or cron (Linux):
    # Every day at 8 AM
    0 8 * * * /path/to/venv/bin/python manage.py check_disk_space

Settings:
    MEDIA_DISK_ALERT_BYTES  — alert threshold in bytes (default: 5 GB)
"""

import os
import shutil
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


def _human_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _folder_size(path: str) -> int:
    """Recursively compute total size of all files under path."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fname in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass
    return total


class Command(BaseCommand):
    help = "Check media folder disk usage and warn if approaching the configured threshold."

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold',
            type=int,
            default=None,
            help="Override alert threshold in bytes (default: settings.MEDIA_DISK_ALERT_BYTES)",
        )

    def handle(self, *args, **options):
        media_root = getattr(settings, 'MEDIA_ROOT', '')
        if not media_root or not os.path.exists(media_root):
            self.stdout.write(self.style.WARNING(
                f"MEDIA_ROOT '{media_root}' does not exist. Nothing to check."
            ))
            return

        # Disk usage of the entire partition containing MEDIA_ROOT
        try:
            total_disk, used_disk, free_disk = shutil.disk_usage(media_root)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Could not read disk usage: {exc}"))
            return

        # Media folder usage (uploaded files only)
        media_used = _folder_size(media_root)

        # Alert threshold
        threshold = options['threshold'] or getattr(
            settings, 'MEDIA_DISK_ALERT_BYTES', 5 * 1024 * 1024 * 1024  # 5 GB default
        )
        disk_usage_pct = (used_disk / total_disk * 100) if total_disk > 0 else 0

        self.stdout.write("\n" + "=" * 55)
        self.stdout.write("  Birnagar Municipality — Disk Space Report")
        self.stdout.write("=" * 55)
        self.stdout.write(f"  Media folder : {media_root}")
        self.stdout.write(f"  Media used   : {_human_size(media_used)}")
        self.stdout.write(f"  Disk total   : {_human_size(total_disk)}")
        self.stdout.write(f"  Disk used    : {_human_size(used_disk)} ({disk_usage_pct:.1f}%)")
        self.stdout.write(f"  Disk free    : {_human_size(free_disk)}")
        self.stdout.write(f"  Alert at     : {_human_size(threshold)} media usage")
        self.stdout.write("=" * 55 + "\n")

        # Check 1: Overall disk usage >80%
        if disk_usage_pct >= 80:
            msg = (
                f"[ALERT] Disk partition is {disk_usage_pct:.1f}% full "
                f"({_human_size(free_disk)} free). Consider archiving old media files."
            )
            self.stdout.write(self.style.ERROR(msg))
            logger.warning(msg)
        elif disk_usage_pct >= 60:
            msg = f"[WARN] Disk partition is {disk_usage_pct:.1f}% full. Monitor closely."
            self.stdout.write(self.style.WARNING(msg))
            logger.info(msg)
        else:
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Disk health is good ({disk_usage_pct:.1f}% used)."
            ))

        # Check 2: Media folder vs configured threshold
        if media_used >= threshold:
            msg = (
                f"[ALERT] Media folder exceeds threshold: "
                f"{_human_size(media_used)} used (threshold: {_human_size(threshold)}). "
                "Consider migrating to cloud storage (S3/Cloudflare R2)."
            )
            self.stdout.write(self.style.ERROR(msg))
            logger.warning(msg)
        else:
            remaining = threshold - media_used
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Media folder within threshold ({_human_size(remaining)} remaining)."
            ))

        self.stdout.write("")
