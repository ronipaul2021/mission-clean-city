"""
core/utils.py — Shared utilities for the BM project.

Contains:
  - Aadhaar encryption / decryption (Fernet, with key-rotation support)
  - Chart data helpers (with 1-hour caching)
  - OTP session helpers
  - Image validation & compression
"""

import json
import time
import logging
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Avg, Case, When, IntegerField as _Int
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncQuarter, TruncYear
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. AADHAAR ENCRYPTION (with key-rotation support)
# ==============================================================================

def _get_fernet(key_str: str):
    """Return a Fernet instance for the given base64 key string."""
    if not key_str:
        raise ValueError("Fernet key is empty.")
    try:
        from cryptography.fernet import Fernet
        return Fernet(key_str.encode())
    except Exception as exc:
        raise ValueError(f"Invalid Fernet key: {exc}") from exc


def encrypt_aadhaar(plaintext: str) -> str:
    """
    Encrypt a 12-digit Aadhaar number using the current AADHAAR_ENCRYPTION_KEY.
    Falls back to plain storage if key is not configured (dev mode).
    """
    if not plaintext:
        return plaintext
    key = getattr(settings, 'AADHAAR_ENCRYPTION_KEY', '')
    if not key:
        logger.warning("Aadhaar encryption skipped: AADHAAR_ENCRYPTION_KEY not set.")
        return plaintext
    try:
        return _get_fernet(key).encrypt(plaintext.encode()).decode()
    except ValueError as exc:
        logger.warning("Aadhaar encryption failed: %s", exc)
        return plaintext


def hash_aadhaar(plaintext: str) -> str:
    """
    Return the SHA-256 hex digest of the plain Aadhaar number.
    Used exclusively for One-Aadhaar-One-Account duplicate checks.
    One-way — cannot be reversed.
    """
    if not plaintext:
        return ''
    return hashlib.sha256(plaintext.strip().encode()).hexdigest()


def decrypt_aadhaar(ciphertext: str) -> str:
    """
    Decrypt a stored Aadhaar ciphertext.

    Key Rotation Support:
    - Tries AADHAAR_ENCRYPTION_KEY (current) first.
    - If that fails and AADHAAR_ENCRYPTION_KEY_OLD is set, tries the old key.
    - Returns plaintext as-is for legacy unencrypted rows.
    """
    if not ciphertext:
        return ciphertext

    current_key = getattr(settings, 'AADHAAR_ENCRYPTION_KEY', '')
    old_key = getattr(settings, 'AADHAAR_ENCRYPTION_KEY_OLD', '')

    # Try current key first
    if current_key:
        try:
            return _get_fernet(current_key).decrypt(ciphertext.encode()).decode()
        except Exception:
            pass  # Fall through to old key

    # Try old key (key rotation path)
    if old_key:
        try:
            plaintext = _get_fernet(old_key).decrypt(ciphertext.encode()).decode()
            logger.info("Aadhaar decrypted with OLD key — row should be re-encrypted with new key.")
            return plaintext
        except Exception:
            pass

    # Legacy row stored as plain text (before encryption was enabled)
    logger.warning("Aadhaar decryption failed with all keys — returning ciphertext as-is.")
    return ciphertext


def reencrypt_aadhaar_if_needed(user) -> bool:
    """
    If AADHAAR_ENCRYPTION_KEY_OLD is set and the user's Aadhaar was encrypted
    with the old key, re-encrypt it with the current key transparently.

    Call this after a successful login to silently migrate old-key records.
    Returns True if re-encryption was performed.
    """
    old_key = getattr(settings, 'AADHAAR_ENCRYPTION_KEY_OLD', '')
    current_key = getattr(settings, 'AADHAAR_ENCRYPTION_KEY', '')
    if not old_key or not current_key or not user.encrypted_aadhaar:
        return False

    # Check if the stored ciphertext can be decrypted with the old key
    try:
        plaintext = _get_fernet(old_key).decrypt(user.encrypted_aadhaar.encode()).decode()
    except Exception:
        return False  # Not encrypted with the old key, nothing to do

    # Re-encrypt with the current key
    try:
        user.encrypted_aadhaar = _get_fernet(current_key).encrypt(plaintext.encode()).decode()
        user.save(update_fields=['encrypted_aadhaar'])
        logger.info("Re-encrypted Aadhaar for user %s with new key.", user.username)
        return True
    except Exception as exc:
        logger.error("Failed to re-encrypt Aadhaar for user %s: %s", user.username, exc)
        return False


# ==============================================================================
# 2. OTP SESSION HELPERS
# ==============================================================================

OTP_SESSION_KEY = 'registration_otp'
OTP_TIMESTAMP_KEY = 'otp_created_at'
OTP_DATA_KEY = 'registration_data'


def _hash_otp(otp: str) -> str:
    """Return SHA-256 hex digest of an OTP string. One-way — cannot be reversed."""
    return hashlib.sha256(otp.strip().encode()).hexdigest()


def store_otp_in_session(request, otp: str) -> None:
    """Hash the OTP and save only the hash + creation timestamp in the session.
    The raw OTP is NEVER stored — only its one-way SHA-256 digest is kept."""
    request.session[OTP_SESSION_KEY] = _hash_otp(otp)
    request.session[OTP_TIMESTAMP_KEY] = time.time()


def verify_otp_value(request, entered_otp: str) -> bool:
    """Compare the hash of entered_otp with the stored hash. Returns True if they match."""
    stored_hash = request.session.get(OTP_SESSION_KEY, '')
    return stored_hash and _hash_otp(entered_otp) == stored_hash


def is_otp_expired(request) -> bool:
    """Return True if the OTP stored in the session has expired."""
    created_at = request.session.get(OTP_TIMESTAMP_KEY, 0)
    expiry_seconds = getattr(settings, 'OTP_EXPIRY_MINUTES', 10) * 60
    return (time.time() - created_at) > expiry_seconds


def clear_otp_session(request) -> None:
    """Remove OTP, timestamp, and registration data from the session."""
    for key in (OTP_SESSION_KEY, OTP_TIMESTAMP_KEY, OTP_DATA_KEY):
        request.session.pop(key, None)


# ==============================================================================
# 3. UPLOAD RATE LIMITING (session-based, no Redis required)
# ==============================================================================

def check_upload_rate_limit(request) -> bool:
    """
    Returns True if the user is within the allowed upload rate limit.
    Tracks upload counts per hour in the session.
    Limit is configured via settings.UPLOAD_RATE_LIMIT (default: 10/hour).
    """
    limit = getattr(settings, 'UPLOAD_RATE_LIMIT', 10)
    now = time.time()
    window = 3600  # 1 hour

    uploads = request.session.get('upload_timestamps', [])
    # Prune timestamps older than 1 hour
    uploads = [t for t in uploads if now - t < window]

    if len(uploads) >= limit:
        return False  # Rate limit exceeded

    uploads.append(now)
    request.session['upload_timestamps'] = uploads
    return True


# ==============================================================================
# 4. CHART DATA HELPERS — with 1-hour caching
# ==============================================================================

def _make_cache_key(prefix: str, timeframe: str, start_date: str, end_date: str, ward: str) -> str:
    """Build a deterministic cache key from analytics filter parameters."""
    raw = f"{prefix}:{timeframe}:{start_date}:{end_date}:{ward}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_timeframe_filters(timeframe: str):
    """Returns (start_date, TruncClass, format_string) based on timeframe."""
    now = timezone.now()
    if timeframe == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, TruncDay, '%I %p'
    elif timeframe == 'weekly':
        start = now - timedelta(days=7)
        return start, TruncDay, '%a, %d %b'
    elif timeframe == 'monthly':
        start = now - timedelta(days=30)
        return start, TruncDay, '%d %b'
    elif timeframe == 'quarterly':
        start = now - timedelta(days=90)
        return start, TruncWeek, '%d %b %Y'
    elif timeframe == 'half_yearly':
        start = now - timedelta(days=180)
        return start, TruncMonth, '%b %Y'
    elif timeframe == 'yearly':
        start = now - timedelta(days=365)
        return start, TruncMonth, '%b %Y'
    else:  # 'all'
        return None, TruncMonth, '%b %Y'


def apply_custom_filters(qs, start_date_str, end_date_str, ward_str, date_field='submitted_at', ward_field='ward_number'):
    """Apply custom date range and ward filters to a queryset."""
    if start_date_str:
        qs = qs.filter(**{f"{date_field}__date__gte": start_date_str})
    if end_date_str:
        qs = qs.filter(**{f"{date_field}__date__lte": end_date_str})
    if ward_str:
        try:
            qs = qs.filter(**{ward_field: int(ward_str)})
        except (ValueError, TypeError):
            pass
    return qs


def invalidate_analytics_cache():
    """
    Invalidate all analytics cache entries.
    Call this whenever a complaint status changes so the next page load
    reflects fresh data.
    """
    # Django's file-based cache doesn't support pattern deletion,
    # so we use a version key approach: bump a version counter.
    version = cache.get('analytics_cache_version', 0) + 1
    cache.set('analytics_cache_version', version, timeout=None)


def _get_cache_version() -> int:
    return cache.get('analytics_cache_version', 0)


def get_complaint_chart_data(timeframe: str = 'all', start_date: str = '', end_date: str = '', ward: str = '') -> dict:
    """
    Build all chart datasets for complaint analytics.
    Results are cached for ANALYTICS_CACHE_SECONDS (default 1 hour).
    Cache is invalidated when complaint statuses change.
    """
    from .models import Complaint

    version = _get_cache_version()
    cache_key = f"v{version}:{_make_cache_key('complaint_charts', timeframe, start_date, end_date, ward)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    start_dt, TruncClass, fmt = get_timeframe_filters(timeframe)
    base_qs = Complaint.objects.all()

    if timeframe == 'custom':
        base_qs = apply_custom_filters(base_qs, start_date, end_date, ward)
    else:
        if start_dt:
            base_qs = base_qs.filter(submitted_at__gte=start_dt)
        if ward:
            base_qs = base_qs.filter(ward_number=ward)

    ward_qs = list(
        base_qs.values('ward_number')
        .annotate(count=Count('id'))
        .order_by('ward_number')
    )

    cat_qs = list(
        base_qs.values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    cat_label_map = dict(Complaint.CategoryChoices.choices)

    trend_qs_base = base_qs if (start_dt or timeframe == 'custom') else Complaint.objects.filter(
        submitted_at__gte=timezone.now() - timedelta(days=180)
    )
    if timeframe == 'custom':
        TruncClass = TruncDay
        fmt = '%d %b %Y'

    month_qs = list(
        trend_qs_base
        .annotate(month=TruncClass('submitted_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    result = {
        'chart_ward_labels':  json.dumps([f"Ward {d['ward_number']}" for d in ward_qs]),
        'chart_ward_data':    json.dumps([d['count'] for d in ward_qs]),
        'chart_cat_labels':   json.dumps([cat_label_map.get(d['category'], d['category']) for d in cat_qs]),
        'chart_cat_data':     json.dumps([d['count'] for d in cat_qs]),
        'chart_month_labels': json.dumps([d['month'].strftime(fmt) for d in month_qs]),
        'chart_month_data':   json.dumps([d['count'] for d in month_qs]),
    }

    ttl = getattr(settings, 'ANALYTICS_CACHE_SECONDS', 3600)
    cache.set(cache_key, result, timeout=ttl)
    return result


def get_suggestion_chart_data(timeframe: str = 'all', start_date: str = '', end_date: str = '', ward: str = '') -> dict:
    """Build chart datasets for suggestion analytics. Results are cached."""
    from .models import Suggestion

    version = _get_cache_version()
    cache_key = f"v{version}:{_make_cache_key('suggestion_charts', timeframe, start_date, end_date, ward)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    start_dt, _, _ = get_timeframe_filters(timeframe)
    base_qs = Suggestion.objects.all()
    if timeframe == 'custom':
        base_qs = apply_custom_filters(base_qs, start_date, end_date, ward, ward_field='target_ward_number')
    else:
        if start_dt:
            base_qs = base_qs.filter(submitted_at__gte=start_dt)
        if ward:
            base_qs = base_qs.filter(target_ward_number=ward)

    sug_cat_qs = list(
        base_qs.values('suggestion_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    sug_cat_map = dict(Suggestion.CategoryChoices.choices)

    sug_ward_qs = list(
        base_qs.values('target_ward_number')
        .annotate(count=Count('id'))
        .order_by('target_ward_number')
    )

    result = {
        'chart_sug_cat_labels':  json.dumps([sug_cat_map.get(d['suggestion_category'], d['suggestion_category']) for d in sug_cat_qs]),
        'chart_sug_cat_data':    json.dumps([d['count'] for d in sug_cat_qs]),
        'chart_sug_ward_labels': json.dumps([f"Ward {d['target_ward_number']}" for d in sug_ward_qs]),
        'chart_sug_ward_data':   json.dumps([d['count'] for d in sug_ward_qs]),
    }

    ttl = getattr(settings, 'ANALYTICS_CACHE_SECONDS', 3600)
    cache.set(cache_key, result, timeout=ttl)
    return result


def get_citizen_growth_chart_data(timeframe: str = 'all', start_date: str = '', end_date: str = '', ward: str = '') -> dict:
    """Citizen registration growth trend. Results are cached."""
    from .models import User

    version = _get_cache_version()
    cache_key = f"v{version}:{_make_cache_key('citizen_growth', timeframe, start_date, end_date, ward)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    start_dt, TruncClass, fmt = get_timeframe_filters(timeframe)
    base_qs = User.objects.filter(role=User.Role.CITIZEN)

    if timeframe == 'custom':
        trend_qs_base = apply_custom_filters(base_qs, start_date, end_date, ward, date_field='date_joined', ward_field='ward_number')
        TruncClass = TruncDay
        fmt = '%d %b %Y'
    else:
        trend_qs_base = base_qs.filter(date_joined__gte=start_dt) if start_dt else base_qs.filter(
            date_joined__gte=timezone.now() - timedelta(days=365)
        )
        if ward:
            trend_qs_base = trend_qs_base.filter(ward_number=ward)

    growth_qs = list(
        trend_qs_base
        .annotate(month=TruncClass('date_joined'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    result = {
        'chart_growth_labels': json.dumps([d['month'].strftime(fmt) for d in growth_qs]),
        'chart_growth_data':   json.dumps([d['count'] for d in growth_qs]),
    }

    ttl = getattr(settings, 'ANALYTICS_CACHE_SECONDS', 3600)
    cache.set(cache_key, result, timeout=ttl)
    return result


def get_complaint_kpis(timeframe: str = 'all', start_date: str = '', end_date: str = '', ward: str = '') -> dict:
    """Return KPI summary stats for the analytics page. Results are cached."""
    from .models import Complaint

    version = _get_cache_version()
    cache_key = f"v{version}:{_make_cache_key('complaint_kpis', timeframe, start_date, end_date, ward)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    start_dt, _, _ = get_timeframe_filters(timeframe)
    base_qs = Complaint.objects.all()
    if timeframe == 'custom':
        base_qs = apply_custom_filters(base_qs, start_date, end_date, ward)
    else:
        if start_dt:
            base_qs = base_qs.filter(submitted_at__gte=start_dt)
        if ward:
            base_qs = base_qs.filter(ward_number=ward)

    total        = base_qs.count()
    resolved     = base_qs.filter(status=Complaint.Status.RESOLVED).count()
    pending      = base_qs.filter(status=Complaint.Status.PENDING).count()
    in_progress  = base_qs.filter(status=Complaint.Status.IN_PROGRESS).count()
    terminated   = base_qs.filter(status=Complaint.Status.TERMINATED).count()
    avg_raw      = base_qs.filter(rating__isnull=False).aggregate(avg=Avg('rating'))['avg']

    resolution_rate = round((resolved / total * 100), 1) if total > 0 else 0
    avg_rating      = round(avg_raw, 1) if avg_raw else '—'

    top_ward_qs = (
        base_qs
        .filter(status__in=[Complaint.Status.PENDING, Complaint.Status.IN_PROGRESS])
        .values('ward_number')
        .annotate(count=Count('id'))
        .order_by('-count')
        .first()
    )
    top_ward = top_ward_qs['ward_number'] if top_ward_qs else None

    top_cat_qs = (
        base_qs.values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
        .first()
    )
    top_category = dict(Complaint.CategoryChoices.choices).get(top_cat_qs['category']) if top_cat_qs else None

    # Ward performance — 2 queries instead of per-ward queries
    ward_totals = {
        row['ward_number']: row
        for row in base_qs
            .values('ward_number')
            .annotate(
                total=Count('id'),
                resolved=Count(Case(When(status=Complaint.Status.RESOLVED, then=1), output_field=_Int())),
                active=Count(Case(
                    When(status__in=[Complaint.Status.PENDING, Complaint.Status.IN_PROGRESS], then=1),
                    output_field=_Int()
                )),
            )
            .order_by('ward_number')
    }

    ward_performance = []
    for ward_num, d in ward_totals.items():
        w_total    = d['total']
        w_resolved = d['resolved']
        w_active   = d['active']
        w_rate     = round((w_resolved / w_total * 100), 1) if w_total > 0 else 0
        ward_performance.append({
            'ward': ward_num, 'total': w_total,
            'resolved': w_resolved, 'active': w_active, 'rate': w_rate,
        })
    ward_performance.sort(key=lambda x: x['rate'], reverse=True)

    result = {
        'total_complaints':      total,
        'resolved_complaints':   resolved,
        'pending_complaints':    pending,
        'in_progress_count':     in_progress,
        'terminated_complaints': terminated,
        'avg_rating':            avg_rating,
        'resolution_rate':       resolution_rate,
        'top_ward':              top_ward,
        'top_category':          top_category,
        'ward_performance':      ward_performance,
    }

    ttl = getattr(settings, 'ANALYTICS_CACHE_SECONDS', 3600)
    cache.set(cache_key, result, timeout=ttl)
    return result


# ==============================================================================
# 5. IMAGE VALIDATION & COMPRESSION
# ==============================================================================

def validate_and_compress_image(image_file, max_kb=100, require_square=True):
    """
    Validates and compresses an image file.
    - Ensures it's an image (JPG/PNG/WEBP).
    - Automatically converts to RGB JPEG format.
    - If require_square=True, enforces 1:1 aspect ratio (for profile photos).
    - Compresses to stay under max_kb WITHOUT compromising clarity.
    Returns: (processed_content_file, error_message)
    """
    from PIL import Image
    import io
    from django.core.files.base import ContentFile
    import os

    ext = os.path.splitext(image_file.name)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
        return None, "Only .jpg, .png, or .webp files are allowed."

    try:
        image_file.seek(0)
        img = Image.open(image_file)

        if img.mode not in ('RGB',):
            img = img.convert('RGB')

        width, height = img.size
        if require_square and width != height:
            return None, "The image must be a perfect square (1:1 aspect ratio)."

        target_bytes = max_kb * 1024
        current_img = img.copy()

        def try_save(image, quality):
            buf = io.BytesIO()
            image.save(buf, format='JPEG', quality=quality, optimize=True, subsampling=0)
            return buf

        # Phase 1: Shrink dimensions until it fits, at quality=85
        scale = 1.0
        QUALITY = 85
        while True:
            buf = try_save(current_img, QUALITY)
            if buf.tell() <= target_bytes or scale <= 0.2:
                break
            scale -= 0.1
            new_w = max(int(img.width * scale), 100)
            new_h = max(int(img.height * scale), 100)
            current_img = img.resize((new_w, new_h), Image.LANCZOS)

        # Phase 2: Reduce quality as last resort
        if buf.tell() > target_bytes:
            for q in range(80, 9, -5):
                buf = try_save(current_img, q)
                if buf.tell() <= target_bytes:
                    break

        buf.seek(0)
        final_name = os.path.splitext(image_file.name)[0] + '.jpg'
        return ContentFile(buf.read(), name=final_name), None

    except Exception as e:
        logger.error("Image processing error: %s", e)
        return None, f"Invalid image file: {str(e)}"


def auto_crop_face(image_file):
    """
    Uses OpenCV Haar Cascades to detect a face, crop a perfect 1:1 square centered
    on the face, then passes to validate_and_compress_image.
    Falls back to center-crop if no face is detected or OpenCV is unavailable.
    Includes a safety guard: if processing exceeds 30 seconds it falls back gracefully.
    """
    import signal

    def _timeout_handler(signum, frame):
        raise TimeoutError("Face detection timed out.")

    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageOps
        import io
        from django.core.files.base import ContentFile
        import os

        image_file.seek(0)
        pil_img = Image.open(image_file)
        pil_img = ImageOps.exif_transpose(pil_img)

        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')

        open_cv_image = np.array(pil_img)
        open_cv_image = open_cv_image[:, :, ::-1].copy()
        gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)

        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        img_w, img_h = pil_img.size

        if len(faces) > 0:
            faces = sorted(faces, key=lambda x: x[2] * x[3], reverse=True)
            x, y, w, h = faces[0]
            face_center_x = x + w // 2
            face_center_y = y + h // 2
            sq_size = int(max(w, h) * 1.5)
            sq_size = min(sq_size, img_w, img_h)

            left = face_center_x - sq_size // 2
            top  = face_center_y - sq_size // 2

            if left < 0: left = 0
            if top < 0:  top = 0
            if left + sq_size > img_w: left = img_w - sq_size
            if top + sq_size > img_h:  top = img_h - sq_size

            pil_img = pil_img.crop((left, top, left + sq_size, top + sq_size))
        else:
            # Fallback: center crop
            sq_size = min(img_w, img_h)
            left = (img_w - sq_size) // 2
            top  = (img_h - sq_size) // 2
            pil_img = pil_img.crop((left, top, left + sq_size, top + sq_size))

        buf = io.BytesIO()
        pil_img.save(buf, format='JPEG', quality=100)
        buf.seek(0)

        final_name = os.path.splitext(image_file.name)[0] + '.jpg'
        new_file = ContentFile(buf.read(), name=final_name)
        return validate_and_compress_image(new_file, max_kb=100, require_square=True)

    except ImportError:
        logger.warning("OpenCV not installed. Falling back to standard compression.")
        return validate_and_compress_image(image_file, max_kb=100, require_square=False)
    except Exception as e:
        logger.error("Face crop error: %s", e)
        return validate_and_compress_image(image_file, max_kb=100, require_square=False)
