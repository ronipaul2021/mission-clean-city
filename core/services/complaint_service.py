"""
core/services/complaint_service.py

Business logic for Complaint operations extracted from views.py.
Views call these functions instead of containing the logic directly.
This makes each operation independently testable and reusable.
"""

import logging
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Count
from datetime import timedelta

logger = logging.getLogger(__name__)


class ComplaintService:
    """Service class encapsulating all Complaint business logic."""

    # ─── Submission ──────────────────────────────────────────────────────────

    @staticmethod
    def get_submission_limits(user):
        """
        Returns (daily_left, monthly_left, can_submit, unrated_resolved).
        Centralized so both the view and any future API endpoint share the same logic.
        """
        from core.models import Complaint
        now = timezone.now()
        start_of_day   = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        today_count = Complaint.objects.filter(citizen=user, submitted_at__gte=start_of_day).count()
        month_count = Complaint.objects.filter(citizen=user, submitted_at__gte=start_of_month).count()

        daily_left   = max(0, 2 - today_count)
        monthly_left = max(0, 10 - month_count)
        can_submit   = daily_left > 0 and monthly_left > 0

        unrated_resolved = (
            Complaint.objects.filter(
                citizen=user,
                status=Complaint.Status.RESOLVED,
                rating__isnull=True
            ).order_by('resolved_at').first()
        )

        return daily_left, monthly_left, can_submit, unrated_resolved

    @staticmethod
    def check_duplicate(user, category: str):
        """
        Returns a dict with 'duplicate' (bool) and 'message' (str).
        Used by the AJAX duplicate-check endpoint.
        """
        from core.models import Complaint
        now = timezone.now()
        cutoff = now - timedelta(days=30)

        existing = Complaint.objects.filter(
            citizen=user,
            category=category,
            submitted_at__gte=cutoff,
            status__in=[Complaint.Status.PENDING, Complaint.Status.IN_PROGRESS]
        ).order_by('-submitted_at').first()

        if existing:
            return {
                'duplicate': True,
                'message': (
                    f"You already have an active complaint in this category "
                    f"({existing.problem_id}, submitted {existing.submitted_at.strftime('%d %b %Y')}). "
                    "Are you sure you want to submit another one?"
                )
            }
        return {'duplicate': False, 'message': ''}

    @staticmethod
    def create(user, form_data: dict, photos: dict, video=None):
        """
        Create a new Complaint for a citizen.

        Args:
            user:       The citizen User object.
            form_data:  Dict with keys: category, sub_category, description,
                        latitude, longitude, target_address, confirm_duplicate.
            photos:     Dict with keys: photo1, photo2, photo3 (file objects or None).
            video:      Optional video file object.

        Returns:
            (complaint, error_message) — complaint is None on error.
        """
        from core.models import Complaint
        from core.utils import validate_and_compress_image

        category     = form_data.get('category', '').strip()
        sub_category = form_data.get('sub_category', '').strip()
        description  = form_data.get('description', '').strip()
        latitude     = form_data.get('latitude', '').strip()
        longitude    = form_data.get('longitude', '').strip()
        address      = form_data.get('target_address', '').strip()

        if not category:
            return None, "Please select a problem category."
        if not address:
            return None, "Please pin a location on the map."

        complaint = Complaint(
            citizen=user,
            category=category,
            sub_category=sub_category or None,
            description=description or None,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            target_address=address,
        )

        # Process and attach photos
        for idx, field_name in enumerate(['photo1', 'photo2', 'photo3'], start=1):
            photo = photos.get(f'photo{idx}')
            if photo:
                processed, err = validate_and_compress_image(photo, max_kb=75, require_square=False)
                if err:
                    return None, f"Photo {idx}: {err}"
                setattr(complaint, field_name, processed)

        if not complaint.photo1:
            return None, "At least one photo is required."

        if video:
            complaint.video = video

        complaint.save()
        logger.info("Complaint %s created by citizen %s", complaint.problem_id, user.username)
        return complaint, None

    # ─── Status Updates ───────────────────────────────────────────────────────

    @staticmethod
    def update_status(complaint, new_status: str, notes: str = '', resolved_by=None, photo=None):
        """
        Update a single complaint's status.
        Handles resolution timestamp, resolved_by, and optional resolution photo.
        """
        from core.models import Complaint

        complaint.status = new_status
        complaint.resolution_notes = notes or complaint.resolution_notes

        if new_status == Complaint.Status.RESOLVED:
            complaint.resolved_at  = timezone.now()
            complaint.resolved_by  = resolved_by
            complaint.reopen_deadline = timezone.now() + timedelta(days=7)
            if photo:
                complaint.resolution_photo = photo

        elif new_status == Complaint.Status.TERMINATED:
            complaint.resolved_at = timezone.now()
            complaint.resolved_by = resolved_by
            if photo:
                complaint.resolution_photo = photo

        complaint.save()
        logger.info("Complaint %s updated to %s by %s", complaint.problem_id, new_status,
                    resolved_by.username if resolved_by else 'unknown')
        return complaint

    @staticmethod
    def rate(complaint, rating: int):
        """
        Submit a citizen satisfaction rating (1-5) for a resolved complaint.
        Returns (success, error_message).
        """
        from core.models import Complaint
        if complaint.status != Complaint.Status.RESOLVED:
            return False, "Only resolved complaints can be rated."
        if complaint.rating is not None:
            return False, "This complaint has already been rated."
        if rating not in range(1, 6):
            return False, "Rating must be between 1 and 5."

        complaint.rating = rating
        complaint.save(update_fields=['rating'])
        logger.info("Complaint %s rated %d", complaint.problem_id, rating)
        return True, None

    @staticmethod
    def reopen(complaint, citizen):
        """
        Reopen a resolved complaint (within 7-day window, rating 1-3 only).
        Returns (success, error_message).
        """
        from core.models import Complaint
        if complaint.status != Complaint.Status.RESOLVED:
            return False, "Only resolved complaints can be reopened."
        if complaint.citizen != citizen:
            return False, "You can only reopen your own complaints."
        if not complaint.reopen_deadline or timezone.now() > complaint.reopen_deadline:
            return False, "The 7-day reopen window has expired."
        if complaint.rating and complaint.rating > 3:
            return False, "Only complaints rated 3 or below can be reopened."

        complaint.status = Complaint.Status.PENDING
        complaint.resolved_at = None
        complaint.resolved_by = None
        complaint.save(update_fields=['status', 'resolved_at', 'resolved_by'])
        logger.info("Complaint %s reopened by citizen %s", complaint.problem_id, citizen.username)
        return True, None

    @staticmethod
    def submit_appeal(complaint, citizen, appeal_text: str):
        """
        Submit an appeal for a terminated complaint.
        Returns (success, error_message).
        """
        from core.models import Complaint
        if complaint.status != Complaint.Status.TERMINATED:
            return False, "Appeals can only be submitted for terminated complaints."
        if complaint.citizen != citizen:
            return False, "You can only appeal your own complaints."
        if complaint.appeal_text:
            return False, "You have already submitted an appeal for this complaint."

        complaint.appeal_text = appeal_text.strip()
        complaint.save(update_fields=['appeal_text'])
        logger.info("Appeal submitted for %s by %s", complaint.problem_id, citizen.username)
        return True, None

    # ─── Search & Filtering ───────────────────────────────────────────────────

    @staticmethod
    def search(query_params: dict):
        """
        Applies all filter parameters to the Complaint queryset.

        Supported params:
            q           — full-text search across problem_id, citizen name, mobile,
                          description, sub_category, target_address
            ward        — ward number (integer)
            status      — Complaint.Status choice
            category    — Complaint.CategoryChoices choice
            priority    — Complaint.Priority choice
            date_from   — ISO date string (YYYY-MM-DD)
            date_to     — ISO date string (YYYY-MM-DD)
            preset      — preset name: 'pending_urgent', 'in_progress', 'unrated_resolved'

        Returns:
            (queryset, active_filter_count)
        """
        from core.models import Complaint

        qs = Complaint.objects.select_related('citizen', 'resolved_by').order_by('-submitted_at')
        active = 0

        # ── Preset filters ──
        preset = query_params.get('preset', '').strip()
        if preset == 'pending_urgent':
            qs = qs.filter(status=Complaint.Status.PENDING, priority__in=['URGENT', 'HIGH'])
            active += 1
        elif preset == 'in_progress':
            qs = qs.filter(status=Complaint.Status.IN_PROGRESS)
            active += 1
        elif preset == 'unrated_resolved':
            qs = qs.filter(status=Complaint.Status.RESOLVED, rating__isnull=True)
            active += 1
        elif preset == 'appealed':
            qs = qs.filter(status=Complaint.Status.TERMINATED, appeal_text__isnull=False)
            active += 1
        elif preset == 'today':
            today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            qs = qs.filter(submitted_at__gte=today)
            active += 1

        # ── Individual filters (can combine with preset) ──
        ward = query_params.get('ward', '').strip()
        if ward:
            try:
                qs = qs.filter(ward_number=int(ward))
                active += 1
            except ValueError:
                pass

        status = query_params.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
            active += 1

        category = query_params.get('category', '').strip()
        if category:
            qs = qs.filter(category=category)
            active += 1

        priority = query_params.get('priority', '').strip()
        if priority:
            qs = qs.filter(priority=priority)
            active += 1

        date_from = query_params.get('date_from', '').strip()
        if date_from:
            qs = qs.filter(submitted_at__date__gte=date_from)
            active += 1

        date_to = query_params.get('date_to', '').strip()
        if date_to:
            qs = qs.filter(submitted_at__date__lte=date_to)
            active += 1

        # ── Full-text search (covers more fields than the old version) ──
        q = query_params.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(problem_id__icontains=q) |
                Q(citizen__name__icontains=q) |
                Q(citizen__mobile_number__icontains=q) |
                Q(citizen__citizen_id__icontains=q) |
                Q(description__icontains=q) |
                Q(sub_category__icontains=q) |
                Q(target_address__icontains=q) |
                Q(resolution_notes__icontains=q)
            )
            active += 1

        return qs, active
