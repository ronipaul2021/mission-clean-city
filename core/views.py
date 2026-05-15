"""
core/views.py

All view logic for the Birnagar Municipality civic platform.

Improvements over the original:
  - All imports moved to the top (PEP 8)
  - OTP expiry enforced (configurable via OTP_EXPIRY_MINUTES in settings)
  - Aadhaar encrypted on registration via utils.encrypt_aadhaar()
  - Chart/KPI data extracted to utils.py (views stay thin)
  - Added change_password view for logged-in users
  - Consistent guard pattern: role checks at the very top of protected views
"""

import csv
import time
import random
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Count
from urllib.parse import urlencode

from .models import User, Complaint, Suggestion, Notification
from .sms import send_otp_sms
from .email_service import send_otp_email
from django.contrib.auth.hashers import make_password
from .utils import (
    encrypt_aadhaar,
    decrypt_aadhaar,
    hash_aadhaar,
    reencrypt_aadhaar_if_needed,
    store_otp_in_session,
    verify_otp_value,
    is_otp_expired,
    clear_otp_session,
    OTP_SESSION_KEY,
    OTP_DATA_KEY,
    get_complaint_chart_data,
    get_suggestion_chart_data,
    get_citizen_growth_chart_data,
    get_complaint_kpis,
    invalidate_analytics_cache,
    check_upload_rate_limit,
    validate_and_compress_image,
    auto_crop_face,
)
from .services import ComplaintService
from .serializers import ComplaintSerializer, SuggestionSerializer, UserSerializer
from .image_processor import ImageProcessor

import os
from datetime import timedelta
from django.http import FileResponse, Http404

logger = logging.getLogger(__name__)


def get_submission_stats(user):
    """
    Returns counts of complaints and suggestions for today and the current month
    to enforce submission limits.
    """
    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    stats = {
        'complaints_today': Complaint.objects.filter(citizen=user, submitted_at__gte=start_of_day).count(),
        'complaints_month': Complaint.objects.filter(citizen=user, submitted_at__gte=start_of_month).count(),
        'suggestions_today': Suggestion.objects.filter(submitted_by=user, submitted_at__gte=start_of_day).count(),
        'suggestions_month': Suggestion.objects.filter(submitted_by=user, submitted_at__gte=start_of_month).count(),
    }
    return stats


# ==============================================================================
# 0a. PROTECTED MEDIA — Serve media files only to authenticated users
# ==============================================================================

def protected_media(request, file_path):
    """
    Gatekeeper view — serves media files only to logged-in users.
    Profile photos: only the owner or an admin can view.
    Complaint/Suggestion photos: any authenticated user.
    """
    if not request.user.is_authenticated:
        raise Http404("File not found.")

    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
    if not os.path.exists(full_path):
        raise Http404("File not found.")

    # Profile photos — citizens can only access their own
    if file_path.startswith('profile_photos/') or file_path.startswith('temp_profiles/'):
        if request.user.role == User.Role.CITIZEN:
            own_photo = request.user.profile_photo.name if request.user.profile_photo else None
            if own_photo != file_path:
                raise Http404("File not found.")

    return FileResponse(open(full_path, 'rb'))


# ==============================================================================
# 0. PUBLIC PAGES
# ==============================================================================

def home(request):
    # Single aggregate query for all complaint status counts instead of 3 separate ones
    status_counts = {
        row['status']: row['total']
        for row in Complaint.objects.values('status').annotate(total=Count('id'))
    }
    total_resolved_count = status_counts.get(Complaint.Status.RESOLVED, 0)
    pending_issues       = status_counts.get(Complaint.Status.PENDING, 0)
    total_complaints     = sum(status_counts.values())

    # select_related avoids N+1 if template accesses complaint.citizen fields
    recent_resolved = Complaint.objects.filter(
        status=Complaint.Status.RESOLVED
    ).select_related('citizen').order_by('-resolved_at')[:5]

    total_citizens = User.objects.filter(role=User.Role.CITIZEN).count()

    return render(request, 'home.html', {
        'recent_resolved':      recent_resolved,
        'total_resolved_count': total_resolved_count,
        'total_complaints':     total_complaints,
        'total_citizens':       total_citizens,
        'pending_issues':       pending_issues,
    })


def about(request):
    return render(request, 'about.html')


@login_required
def suggestions(request):
    if request.user.role == User.Role.ADMIN:
        messages.error(request, "Admins cannot use the suggestion box.")
        return redirect('admin_dashboard')

    stats = get_submission_stats(request.user)
    daily_suggestions_left = max(0, 1 - stats['suggestions_today'])
    monthly_suggestions_left = max(0, 5 - stats['suggestions_month'])
    can_submit = daily_suggestions_left > 0 and monthly_suggestions_left > 0

    if request.method == 'POST':
        if not can_submit:
            messages.error(request, "You have reached your submission limit for suggestions.")
            return redirect('suggestions')

        # Upload rate limit: max UPLOAD_RATE_LIMIT uploads per hour
        if not check_upload_rate_limit(request):
            messages.error(request, "You are uploading too frequently. Please wait before submitting again.")
            return redirect('suggestions')

        target_ward_number  = request.POST.get('target_ward_number')
        target_address      = request.POST.get('target_address')
        suggestion_category = request.POST.get('suggestion_category')
        description         = request.POST.get('description', '').strip()
        latitude            = request.POST.get('latitude') or None
        longitude           = request.POST.get('longitude') or None
        photo               = request.FILES.get('photo')

        if suggestion_category == 'OTHER' and not description:
            messages.error(request, "Please provide a description for your suggestion.")
            return redirect('suggestions')

        if not all([target_ward_number, target_address, suggestion_category, photo]):
            messages.error(request, "Please fill out all mandatory fields including the photo.")
            return redirect('suggestions')

        user = request.user
        
        # --- Image Validation & Compression (JPEG/JPG, no square required, 75KB) ---
        processed_photo, error = validate_and_compress_image(photo, require_square=False, max_kb=75)
        if error:
            messages.error(request, error)
            return redirect('suggestions')

        suggestion = Suggestion.objects.create(
            submitted_by=user,
            name=user.name,
            mobile_number=user.mobile_number,
            aadhaar_number=user.encrypted_aadhaar or '',
            user_ward_number=user.ward_number,
            user_address=user.address,
            target_ward_number=target_ward_number,
            target_address=target_address,
            suggestion_category=suggestion_category,
            description=description,
            latitude=latitude,
            longitude=longitude,
            photo=processed_photo,
        )
        messages.success(request, f"Thank you! Your Ticket No is {suggestion.ticket_number}")
        return redirect('suggestions')

    return render(request, 'suggestions.html', {
        'CategoryChoices': Suggestion.CategoryChoices,
        'daily_left': daily_suggestions_left,
        'monthly_left': monthly_suggestions_left,
        'can_submit': can_submit,
    })


# ==============================================================================
# 1. AUTHENTICATION VIEWS
# ==============================================================================

def citizen_register(request):
    """
    Citizen Registration — captures details, sends OTP via Fast2SMS,
    and redirects to OTP verification before creating the account.
    Aadhaar is encrypted before being stored in the session.
    """
    if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
        messages.error(request, "Admins cannot register as citizens.")
        return redirect('admin_dashboard')

    if request.method == 'POST':
        name         = request.POST.get('name', '').strip()
        email        = request.POST.get('email', '').strip() or None
        mobile       = request.POST.get('mobile_number', '').strip()
        aadhaar      = request.POST.get('aadhaar', '').strip()
        address      = request.POST.get('address', '').strip()
        ward_number  = request.POST.get('ward_number')
        password     = request.POST.get('password', '')
        retype_pw    = request.POST.get('retype_password', '')
        profile_photo = request.FILES.get('profile_photo')

        # --- Validation ---
        if not all([name, email, mobile, aadhaar, address, ward_number, password, profile_photo]):
            messages.error(request, "All fields including Email and Profile Photo are mandatory.")
            return redirect('citizen_register')

        if len(mobile) != 10 or not mobile.isdigit():
            messages.error(request, "Mobile number must be exactly 10 digits.")
            return redirect('citizen_register')

        if len(aadhaar) != 12 or not aadhaar.isdigit():
            messages.error(request, "Aadhaar number must be exactly 12 digits.")
            return redirect('citizen_register')

        if password != retype_pw:
            messages.error(request, "Passwords do not match.")
            return redirect('citizen_register')

        if User.objects.filter(mobile_number=mobile).exists():
            messages.error(request, "This mobile number is already registered.")
            return redirect('citizen_register')

        if email and User.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered.")
            return redirect('citizen_register')

        # One-Aadhaar-One-Account: check hash for duplicate
        aadhaar_hash_val = hash_aadhaar(aadhaar)
        if User.objects.filter(aadhaar_hash=aadhaar_hash_val).exists():
            messages.error(request, "An account with this Aadhaar number already exists. Each citizen may only have one account. For assistance, contact the municipality.")
            return redirect('citizen_register')

        # --- AI Face Detection, Cropping & Compression ---
        processed_photo, error = auto_crop_face(profile_photo)
        if error:
            messages.error(request, error)
            return redirect('citizen_register')

        # Encrypt Aadhaar before storing in session
        encrypted = encrypt_aadhaar(aadhaar)

        # Hash password for session security
        hashed_password = make_password(password)

        # Temporarily save profile photo for OTP session
        photo_path = default_storage.save(f"temp_profiles/{mobile}_{processed_photo.name}", processed_photo)

        # Store registration data + OTP in session
        request.session[OTP_DATA_KEY] = {
            'name': name, 'email': email, 'mobile_number': mobile,
            'aadhaar': encrypted,          # ← stored encrypted
            'aadhaar_hash': aadhaar_hash_val,  # ← stored for DB uniqueness
            'address': address, 'ward_number': ward_number, 'password': hashed_password,
            'profile_photo_path': photo_path,
        }

        otp = str(random.randint(100000, 999999))
        store_otp_in_session(request, otp)

        email_sent = send_otp_email(email, otp)
        if email_sent:
            messages.success(request, f"A 6-digit OTP has been sent to your email: {email}.")
        else:
            messages.error(request, "Email service is temporarily unavailable. Please try again in a few minutes.")
            if settings.DEBUG:
                # Dev-only: also reveal OTP so testing is not blocked
                messages.warning(request, f"[Dev Mode] Your OTP is: {otp}", extra_tags='otp-reveal')

        return redirect('verify_otp')

    return render(request, 'citizen_register.html')


def verify_otp(request):
    """
    OTP verification for citizen registration.
    Enforces expiry (OTP_EXPIRY_MINUTES from settings, default 10 min).
    """
    if OTP_DATA_KEY not in request.session or OTP_SESSION_KEY not in request.session:
        messages.error(request, "Session expired. Please register again.")
        return redirect('citizen_register')

    # Handle Resend OTP
    if request.method == 'POST' and request.POST.get('action') == 'resend':
        email = request.session[OTP_DATA_KEY]['email']
        new_otp = str(random.randint(100000, 999999))
        store_otp_in_session(request, new_otp)
        # Reset attempt counter on resend
        request.session.pop('otp_attempts', None)
        email_sent = send_otp_email(email, new_otp)
        if email_sent:
            messages.success(request, f"A new OTP has been sent to your email: {email}.")
        else:
            messages.error(request, "Email service is temporarily unavailable. Please try again.")
            if settings.DEBUG:
                messages.warning(request, f"[Dev Mode] Your OTP is: {new_otp}", extra_tags='otp-reveal')
        return redirect('verify_otp')

    if request.method == 'POST':
        # Check expiry first
        if is_otp_expired(request):
            clear_otp_session(request)
            messages.error(
                request,
                f"Your OTP has expired (valid for {settings.OTP_EXPIRY_MINUTES} minutes). "
                "Please register again."
            )
            return redirect('citizen_register')

        # --- Brute Force Protection: max 5 OTP attempts ---
        otp_attempts = request.session.get('otp_attempts', 0)
        if otp_attempts >= 5:
            clear_otp_session(request)
            messages.error(request, "Too many incorrect OTP attempts. Please register again.")
            return redirect('citizen_register')

        entered_otp = request.POST.get('otp', '').strip()

        if verify_otp_value(request, entered_otp):
            # Reset attempt counter before creating user
            request.session.pop('otp_attempts', None)
            data = request.session[OTP_DATA_KEY]
            
            # Create user object manually because password is already hashed
            user = User(
                username=data['mobile_number'],
                password=data['password'], # Already hashed in citizen_register
                name=data['name'],
                email=data['email'],
                mobile_number=data['mobile_number'],
                encrypted_aadhaar=data['aadhaar'],
                aadhaar_hash=data.get('aadhaar_hash', ''),
                address=data['address'],
                ward_number=data['ward_number'],
                role=User.Role.CITIZEN,
            )
            user.save()

            photo_path = data.get('profile_photo_path')
            if photo_path and default_storage.exists(photo_path):
                with default_storage.open(photo_path) as f:
                    user.profile_photo.save(photo_path.split('/')[-1], f, save=True)
                default_storage.delete(photo_path)
            clear_otp_session(request)
            messages.success(request, "Mobile number verified! Registration complete. Please login.")
            return redirect('citizen_login')
        else:
            # Increment attempt counter
            request.session['otp_attempts'] = otp_attempts + 1
            remaining = 5 - request.session['otp_attempts']
            if remaining > 0:
                messages.error(request, f"Invalid OTP. {remaining} attempt{'s' if remaining > 1 else ''} remaining.")
            return redirect('verify_otp')

    expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
    return render(request, 'verify_otp.html', {'expiry_minutes': expiry_minutes})


def citizen_login(request):
    if request.method == 'POST':
        # --- Brute Force Protection ---
        lockout_until = request.session.get('login_lockout_until', 0)
        if time.time() < lockout_until:
            remaining = int((lockout_until - time.time()) / 60) + 1
            messages.error(request, f"Too many failed attempts. Please wait {remaining} minute(s) before trying again.")
            return redirect('citizen_login')

        mobile   = request.POST.get('mobile_number', '')
        password = request.POST.get('password', '')
        user     = authenticate(request, username=mobile, password=password)
        if user is not None and user.role == User.Role.CITIZEN:
            # Successful login — clear counters
            request.session.pop('login_attempts', None)
            request.session.pop('login_lockout_until', None)
            login(request, user)
            # Transparently re-encrypt Aadhaar if old key is still present
            reencrypt_aadhaar_if_needed(user)
            return redirect('citizen_tracking')

        # Failed login — increment counter
        attempts = request.session.get('login_attempts', 0) + 1
        request.session['login_attempts'] = attempts
        if attempts >= 5:
            request.session['login_lockout_until'] = time.time() + (10 * 60)  # 10 min lockout
            request.session['login_attempts'] = 0
            messages.error(request, "Too many failed attempts. Your login is locked for 10 minutes.")
        else:
            remaining = 5 - attempts
            messages.error(request, f"Invalid mobile number or password. {remaining} attempt{'s' if remaining > 1 else ''} remaining.")
        return redirect('citizen_login')
    return render(request, 'citizen_login.html')


def admin_register(request):
    """
    Admin Registration.
    Phase 1 (bootstrap): first admin requires a secret key.
    Phase 2 (normal):    only a logged-in admin can create new admins.
    """
    admin_exists = User.objects.filter(role=User.Role.ADMIN, is_superuser=False).exists()

    if admin_exists and (not request.user.is_authenticated or request.user.role != User.Role.ADMIN):
        messages.error(request, "Access Denied. Only an existing Admin can register a new Admin.")
        return redirect('admin_login')

    if request.method == 'POST':
        name         = request.POST.get('name', '').strip()
        mobile       = request.POST.get('mobile_number', '').strip()
        password     = request.POST.get('password', '')
        retype_pw    = request.POST.get('retype_password', '')

        if not admin_exists:
            if request.POST.get('secret_key', '') != settings.ADMIN_REGISTRATION_SECRET:
                messages.error(request, "Invalid Registration Key. Access Denied.")
                return render(request, 'admin_register.html', {'admin_exists': admin_exists})

        if password != retype_pw:
            messages.error(request, "Passwords do not match.")
            return render(request, 'admin_register.html', {'admin_exists': admin_exists})

        admin_count         = User.objects.filter(role=User.Role.ADMIN, is_superuser=False).count()
        generated_emp_id    = f"BM-EMP-{admin_count + 1:04d}"

        User.objects.create_user(
            username=generated_emp_id,
            password=password,
            name=name,
            mobile_number=mobile,
            employee_id=generated_emp_id,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        return render(request, 'admin_register.html', {
            'admin_exists': True,
            'generated_employee_id': generated_emp_id,
            'registered_name': name,
        })

    return render(request, 'admin_register.html', {'admin_exists': admin_exists})


def admin_login(request):
    if request.method == 'POST':
        # --- Brute Force Protection (admin accounts are higher value targets) ---
        lockout_until = request.session.get('admin_lockout_until', 0)
        if time.time() < lockout_until:
            remaining = int((lockout_until - time.time()) / 60) + 1
            messages.error(request, f"Too many failed attempts. Please wait {remaining} minute(s) before trying again.")
            return redirect('admin_login')

        emp_id   = request.POST.get('employee_id', '')
        password = request.POST.get('password', '')
        user     = authenticate(request, username=emp_id, password=password)
        if user is not None and user.role == User.Role.ADMIN:
            # Successful login — clear counters
            request.session.pop('admin_attempts', None)
            request.session.pop('admin_lockout_until', None)
            login(request, user)
            reencrypt_aadhaar_if_needed(user)
            return redirect('admin_dashboard')

        # Failed login — increment counter
        attempts = request.session.get('admin_attempts', 0) + 1
        request.session['admin_attempts'] = attempts
        if attempts >= 5:
            request.session['admin_lockout_until'] = time.time() + (15 * 60)  # 15 min lockout for admins
            request.session['admin_attempts'] = 0
            messages.error(request, "Too many failed attempts. Admin login is locked for 15 minutes.")
        else:
            remaining = 5 - attempts
            messages.error(request, f"Invalid Employee ID or password. {remaining} attempt{'s' if remaining > 1 else ''} remaining.")
        return redirect('admin_login')
    return render(request, 'admin_login.html')


def user_logout(request):
    logout(request)
    return redirect('citizen_login')


# ==============================================================================
# 1b. CHANGE PASSWORD (new feature — works for both citizens and admins)
# ==============================================================================

@login_required
def change_password(request):
    """
    Allows any logged-in user to change their password.
    Uses Django's built-in password validators and re-authenticates the session
    so the user is not logged out after the change.
    """
    if request.method == 'POST':
        current_pw  = request.POST.get('current_password', '')
        new_pw      = request.POST.get('new_password', '')
        confirm_pw  = request.POST.get('confirm_password', '')

        if not request.user.check_password(current_pw):
            messages.error(request, "Current password is incorrect.")
            return redirect('change_password')

        if new_pw != confirm_pw:
            messages.error(request, "New passwords do not match.")
            return redirect('change_password')

        try:
            validate_password(new_pw, request.user)
        except ValidationError as e:
            for err in e.messages:
                messages.error(request, err)
            return redirect('change_password')

        request.user.set_password(new_pw)
        request.user.save()
        # Keep the user logged in after password change
        update_session_auth_hash(request, request.user)
        messages.success(request, "Password changed successfully.")

        # Redirect to the correct dashboard based on role
        if request.user.role == User.Role.ADMIN:
            return redirect('admin_dashboard')
        return redirect('citizen_tracking')

    return render(request, 'change_password.html')


# ==============================================================================
# 1c. CITIZEN PROFILE EDIT
# ==============================================================================

@login_required
def profile_edit(request):
    """
    Allows a logged-in citizen to update their address, ward number,
    and profile photo. Identity fields (name, mobile, Aadhaar) are locked.
    """
    if request.user.role != User.Role.CITIZEN:
        messages.error(request, "Only citizens can edit their profile.")
        return redirect('admin_dashboard')

    if request.method == 'POST':
        address     = request.POST.get('address', '').strip()
        ward_number = request.POST.get('ward_number', '').strip()
        new_photo   = request.FILES.get('profile_photo')

        if not address or not ward_number:
            messages.error(request, "Address and Ward Number are required.")
            return redirect('profile_edit')

        try:
            ward_number = int(ward_number)
            if not (1 <= ward_number <= 14):
                raise ValueError
        except ValueError:
            messages.error(request, "Ward number must be between 1 and 14.")
            return redirect('profile_edit')

        user = request.user
        user.address     = address
        user.ward_number = ward_number
        if new_photo:
            processed_photo, error = validate_and_compress_image(new_photo, require_square=True)
            if error:
                messages.error(request, error)
                return redirect('profile_edit')
                
            # Delete old photo from storage before replacing
            if user.profile_photo:
                try:
                    default_storage.delete(user.profile_photo.name)
                except Exception:
                    pass
            user.profile_photo = processed_photo
        user.save()
        messages.success(request, "Your profile has been updated successfully.")
        return redirect('citizen_tracking')

    return render(request, 'profile_edit.html', {'ward_range': range(1, 15)})



# ==============================================================================
# 2. CORE FEATURE: SUBMITTING A PROBLEM
# ==============================================================================

@login_required
def submit_problem(request):
    if request.user.role != User.Role.CITIZEN:
        messages.error(request, "Only citizens can submit complaints.")
        return redirect('admin_dashboard')

    # Gate: citizen must rate all resolved complaints before submitting a new one
    unrated_resolved = Complaint.objects.filter(
        citizen=request.user,
        status=Complaint.Status.RESOLVED,
        rating__isnull=True
    ).first()

    stats = get_submission_stats(request.user)
    daily_complaints_left = max(0, 2 - stats['complaints_today'])
    monthly_complaints_left = max(0, 10 - stats['complaints_month'])
    can_submit = daily_complaints_left > 0 and monthly_complaints_left > 0

    if request.method == 'POST':
        if unrated_resolved:
            messages.error(
                request,
                f"Please rate your resolved complaint ({unrated_resolved.problem_id}) before submitting a new report."
            )
            return redirect('citizen_tracking')
        if not can_submit:
            messages.error(request, "You have reached your submission limit for complaints.")
            return redirect('submit_problem')

        # Upload rate limit: max UPLOAD_RATE_LIMIT uploads per hour
        if not check_upload_rate_limit(request):
            messages.error(request, "You are uploading too frequently. Please wait before submitting again.")
            return redirect('submit_problem')

        category       = request.POST.get('category')
        sub_category   = request.POST.get('sub_category')
        description    = request.POST.get('description')
        target_address = request.POST.get('target_address')
        latitude       = request.POST.get('latitude')
        longitude      = request.POST.get('longitude')
        photo1 = request.FILES.get('photo1')
        photo2 = request.FILES.get('photo2')
        photo3 = request.FILES.get('photo3')
        video  = request.FILES.get('video')

        if video and video.size > 100 * 1024 * 1024:
            messages.error(request, "Video size must not exceed 100 MB.")
            return redirect('submit_problem')

        if not photo1:
            messages.error(request, "At least one photo (Photo 1) is required.")
            return redirect('submit_problem')

        lat_val = lng_val = None
        if latitude and longitude:
            try:
                lat_val = float(latitude)
                lng_val = float(longitude)
            except ValueError:
                pass

        # --- Image Validation & Compression (JPEG/JPG, no square required, 75KB) ---
        photo_fields = {'photo1': photo1, 'photo2': photo2, 'photo3': photo3}
        processed_files = {}
        for field, file in photo_fields.items():
            if file:
                processed, error = validate_and_compress_image(file, require_square=False, max_kb=75)
                if error:
                    messages.error(request, f"{field.capitalize()}: {error}")
                    return redirect('submit_problem')
                processed_files[field] = processed

        complaint = Complaint(
            citizen=request.user,
            category=category,
            sub_category=sub_category,
            description=description,
            target_address=target_address,
            latitude=lat_val,
            longitude=lng_val,
            photo1=processed_files.get('photo1'),
            photo2=processed_files.get('photo2'),
            photo3=processed_files.get('photo3'),
            video=video,
        )
        complaint.save()
        messages.success(request, f"Problem submitted! Your Tracking ID is {complaint.problem_id}")
        return redirect('citizen_tracking')

    return render(request, 'submit_problem.html', {
        'daily_left': daily_complaints_left,
        'monthly_left': monthly_complaints_left,
        'can_submit': can_submit,
        'unrated_resolved': unrated_resolved,
    })

@login_required
def check_duplicate(request):
    """AJAX endpoint to check for recently submitted similar complaints."""
    category = request.GET.get('category')
    if not category:
        return HttpResponse('{}', content_type='application/json')
    
    ward = request.user.ward_number
    if not ward:
        return HttpResponse('{}', content_type='application/json')
        
    three_days_ago = timezone.now() - timedelta(days=3)
    duplicate = Complaint.objects.filter(
        category=category,
        ward_number=ward,
        submitted_at__gte=three_days_ago
    ).exclude(status=Complaint.Status.TERMINATED).order_by('-submitted_at').first()
    
    if duplicate:
        import json
        from django.utils.timesince import timesince
        return HttpResponse(json.dumps({
            'duplicate': True,
            'message': f"A similar complaint ({duplicate.get_category_display()}) was filed in your ward {timesince(duplicate.submitted_at)} ago. Are you sure you want to submit another one?"
        }), content_type='application/json')
        
    return HttpResponse('{"duplicate": false}', content_type='application/json')


# ==============================================================================
# 3. DASHBOARDS & TRACKING
# ==============================================================================

def citizen_tracking(request):
    complaint = None
    if request.method == 'GET' and 'problem_id' in request.GET:
        pid = request.GET.get('problem_id', '').strip()
        complaint = Complaint.objects.filter(problem_id=pid).first()
        if not complaint:
            messages.error(request, "No complaint found with that Problem ID.")

    user_complaints = user_suggestions = None
    if request.user.is_authenticated and request.user.role == User.Role.CITIZEN:
        # select_related prevents N+1 queries when template reads complaint.citizen.*
        user_complaints = Complaint.objects.filter(citizen=request.user).select_related('citizen').order_by('-submitted_at')
        
        # Apply filters
        filter_status = request.GET.get('filter_status')
        filter_category = request.GET.get('filter_category')
        
        if filter_status:
            user_complaints = user_complaints.filter(status=filter_status)
        if filter_category:
            user_complaints = user_complaints.filter(category=filter_category)

        user_suggestions = Suggestion.objects.filter(
            submitted_by=request.user
        ).select_related('submitted_by').order_by('-submitted_at')

        # Pagination for complaints
        paginator_issues = Paginator(user_complaints, 10)  # 10 per page
        page_number_issues = request.GET.get('page_issues', 1)
        user_complaints = paginator_issues.get_page(page_number_issues)

        # Pagination for suggestions
        paginator_suggestions = Paginator(user_suggestions, 10)  # 10 per page
        page_number_suggestions = request.GET.get('page_suggestions', 1)
        user_suggestions = paginator_suggestions.get_page(page_number_suggestions)

    return render(request, 'citizen_tracking.html', {
        'searched_complaint': complaint,
        'user_complaints':    user_complaints,
        'user_suggestions':   user_suggestions,
        'filter_status':      request.GET.get('filter_status', ''),
        'filter_category':    request.GET.get('filter_category', ''),
        'statuses':           Complaint.Status.choices,
        'categories':         Complaint.CategoryChoices.choices,
    })


@login_required
def citizen_complaint_detail(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)
    
    # Security: Only the citizen who created it (or an admin) can view it
    if request.user.role == User.Role.CITIZEN and complaint.citizen != request.user:
        messages.error(request, "You do not have permission to view this complaint.")
        return redirect('citizen_tracking')

    return render(request, 'citizen_complaint_detail.html', {
        'complaint': complaint
    })


@login_required
def admin_dashboard(request):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access. Admins only.")
        return redirect('submit_problem')

    # Handle status update via POST
    if request.method == 'POST':
        action = request.POST.get('action')

        # ---- Bulk Status Update ------------------------------------------------
        if action == 'bulk_update':
            complaint_ids = request.POST.getlist('complaint_ids')
            bulk_status   = request.POST.get('bulk_status')
            bulk_notes    = request.POST.get('bulk_notes', '').strip()
            bulk_priority = request.POST.get('bulk_priority', '')
            bulk_photo    = request.FILES.get('bulk_resolution_photo')

            if not complaint_ids or not bulk_status:
                messages.error(request, "Please select complaints and a target status.")
                return redirect('admin_dashboard')
                

            if bulk_status == Complaint.Status.TERMINATED and not bulk_notes:
                # Check if any of the selected complaints have been appealed
                appealed_exists = Complaint.objects.filter(id__in=complaint_ids).exclude(appeal_text__isnull=True).exclude(appeal_text='').exists()
                if appealed_exists:
                    messages.error(request, "A termination reason is required when terminating complaints that have been appealed.")
                    return redirect('admin_dashboard')

            locked_statuses = [Complaint.Status.RESOLVED, Complaint.Status.TERMINATED]
            qs = Complaint.objects.filter(
                id__in=complaint_ids
            ).exclude(status__in=locked_statuses)

            # Cannot revert IN_PROGRESS → PENDING via bulk
            if bulk_status == Complaint.Status.PENDING:
                qs = qs.exclude(status=Complaint.Status.IN_PROGRESS)

            update_fields = {'status': bulk_status}
            if bulk_status in (Complaint.Status.RESOLVED, Complaint.Status.TERMINATED):
                update_fields['resolved_at'] = timezone.now()
                update_fields['resolved_by'] = request.user
                if bulk_notes:
                    update_fields['resolution_notes'] = bulk_notes
            if bulk_priority:
                update_fields['priority'] = bulk_priority

            updated = qs.update(**update_fields)

            # Handling photos via update() isn't possible (ImageField requires saving the file object),
            # so we iterate to attach the same photo to all if provided.
            # We also iterate to generate notifications.
            for comp in qs:
                if bulk_photo and bulk_status in (Complaint.Status.RESOLVED, Complaint.Status.TERMINATED):
                    comp.resolution_photo = bulk_photo
                    comp.save(update_fields=['resolution_photo'])

                # Generate Notification
                Notification.objects.create(
                    user=comp.citizen,
                    message=f"Your complaint {comp.problem_id} status has been updated to {bulk_status}."
                )

            # Invalidate analytics cache so next load reflects fresh data
            invalidate_analytics_cache()
            messages.success(request, f"{updated} complaint(s) updated to '{bulk_status}'.")
            return redirect('admin_dashboard')

        # ---- Single Complaint Update -------------------------------------------
        complaint   = get_object_or_404(Complaint, id=request.POST.get('complaint_id'))
        new_status  = request.POST.get('new_status')
        new_notes   = request.POST.get('resolution_notes', '').strip()
        new_priority = request.POST.get('priority', '').strip()
        resolution_photo = request.FILES.get('resolution_photo')

        # Capture current filters for persistent redirect
        query_params = {}
        for param in ['ward', 'status', 'category', 'priority', 'q', 'date_from', 'date_to', 'preset', 'page']:
            val = request.POST.get(param)
            if val:
                query_params[param] = val
        query_string = f"?{urlencode(query_params)}" if query_params else ""
        redirect_url = f"{reverse('admin_dashboard')}{query_string}"

        if complaint.status in (Complaint.Status.RESOLVED, Complaint.Status.TERMINATED):
            messages.error(request, f"{complaint.problem_id} is already {complaint.get_status_display()} and cannot be modified.")
            return redirect(redirect_url)
            
        if new_status == Complaint.Status.RESOLVED and not resolution_photo:
            messages.error(request, f"A resolution proof photo is required to mark {complaint.problem_id} as resolved.")
            return redirect(redirect_url)
            
        if new_status == Complaint.Status.TERMINATED and not new_notes and complaint.appeal_text:
            messages.error(request, f"A termination reason is required when terminating an appealed complaint ({complaint.problem_id}).")
            return redirect(redirect_url)

        if new_status:
            if complaint.status == Complaint.Status.IN_PROGRESS and new_status == Complaint.Status.PENDING:
                messages.error(request, f"{complaint.problem_id} is In Progress and cannot be reverted to Pending.")
                return redirect(redirect_url)
            
            complaint.status = new_status
            if new_status in (Complaint.Status.RESOLVED, Complaint.Status.TERMINATED):
                complaint.resolved_at = timezone.now()
                complaint.resolved_by = request.user

            Notification.objects.create(
                user=complaint.citizen,
                message=f"Your complaint {complaint.problem_id} status has been updated to {new_status}."
            )

        if new_notes:
            complaint.resolution_notes = new_notes
        if new_priority:
            complaint.priority = new_priority
        if resolution_photo:
            processed_photo, error = validate_and_compress_image(resolution_photo, require_square=False, max_kb=100)
            if error:
                messages.error(request, f"Photo Error: {error}")
                return redirect(redirect_url)
            complaint.resolution_photo = processed_photo
            
        complaint.save()

        # Invalidate analytics cache so next load reflects fresh data
        if new_status:
            invalidate_analytics_cache()

        msg_action = f"updated to {new_status}" if new_status else "updated"
        messages.success(request, f"{complaint.problem_id} {msg_action}.")
        return redirect(redirect_url)

    # --- Multi-field Search & Advanced Filtering via ComplaintService ---
    # Supports: q (full-text), ward, status, category, priority,
    #           date_from, date_to, preset
    complaints, active_filter_count = ComplaintService.search(request.GET)

    # Keep legacy context variables for template back-compat
    ward_filter     = request.GET.get('ward', '')
    status_filter   = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    priority_filter = request.GET.get('priority', '')
    search_query    = request.GET.get('q', '').strip()
    date_from       = request.GET.get('date_from', '')
    date_to         = request.GET.get('date_to', '')
    preset          = request.GET.get('preset', '')

    # NOTE: CSV export is handled by the dedicated export_complaints_csv view.

    paginator    = Paginator(complaints, 10)
    page_obj     = paginator.get_page(request.GET.get('page'))
    active_wards = Complaint.objects.values_list('ward_number', flat=True).distinct().order_by('ward_number')

    # Summary counts — single query per model instead of 4+2 separate count queries
    status_counts = {
        row['status']: row['cnt']
        for row in Complaint.objects.values('status').annotate(cnt=Count('id'))
    }
    solved_count      = status_counts.get(Complaint.Status.RESOLVED, 0)
    pending_count     = status_counts.get(Complaint.Status.PENDING, 0)
    in_progress_count = status_counts.get(Complaint.Status.IN_PROGRESS, 0)
    terminated_count  = status_counts.get(Complaint.Status.TERMINATED, 0)

    sug_status_counts = {
        row['status']: row['cnt']
        for row in Suggestion.objects.values('status').annotate(cnt=Count('id'))
    }
    sug_pending_count  = sug_status_counts.get(Suggestion.Status.PENDING, 0)
    sug_accepted_count = sug_status_counts.get(Suggestion.Status.ACCEPTED, 0)
    recent_suggestions = Suggestion.objects.all().order_by('-submitted_at')[:3]

    # Chart data via utility (thin view)
    chart_data = get_complaint_chart_data()

    return render(request, 'admin_dashboard.html', {
        'complaints':          page_obj,
        'page_obj':            page_obj,
        'active_wards':        active_wards,
        'selected_ward':       ward_filter,
        'selected_status':     status_filter,
        'selected_category':   category_filter,
        'selected_priority':   priority_filter,
        'search_query':        search_query,
        'date_from':           date_from,
        'date_to':             date_to,
        'selected_preset':     preset,
        'active_filter_count': active_filter_count,
        'CategoryChoices':     Complaint.CategoryChoices,
        'StatusChoices':       Complaint.Status,
        'PriorityChoices':     Complaint.Priority,
        'solved_count':        solved_count,
        'pending_count':       pending_count,
        'in_progress_count':   in_progress_count,
        'terminated_count':    terminated_count,
        'admin_name':          request.user.name,
        'admin_employee_id':   request.user.employee_id,
        'sug_pending_count':   sug_pending_count,
        'sug_accepted_count':  sug_accepted_count,
        'recent_suggestions':  recent_suggestions,
        **chart_data,
    })


@login_required
def admin_citizens_directory(request):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access. Admins only.")
        return redirect('submit_problem')
        
    search_query = request.GET.get('q', '').strip()
    ward_filter = request.GET.get('ward', '')
    
    citizens = User.objects.filter(role=User.Role.CITIZEN)
    
    if search_query:
        citizens = citizens.filter(
            Q(name__icontains=search_query) |
            Q(mobile_number__icontains=search_query) |
            Q(citizen_id__icontains=search_query)
        )
        
    if ward_filter:
        citizens = citizens.filter(ward_number=ward_filter)
        
    citizens = citizens.order_by('-date_joined')
    
    paginator = Paginator(citizens, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # Get active wards for filter dropdown
    active_wards = User.objects.filter(role=User.Role.CITIZEN, ward_number__isnull=False)\
                               .values_list('ward_number', flat=True).distinct().order_by('ward_number')
                               
    return render(request, 'admin_citizens.html', {
        'citizens': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'search_query': search_query,
        'selected_ward': ward_filter,
        'active_wards': active_wards,
        'admin_name': request.user.name,
        'admin_employee_id': request.user.employee_id,
    })


@login_required
def admin_suggestions(request):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access. Admins only.")
        return redirect('submit_problem')

    if request.method == 'POST':
        suggestion        = get_object_or_404(Suggestion, id=request.POST.get('suggestion_id'))
        suggestion.status = request.POST.get('new_status')
        suggestion.save()
        messages.success(request, f"Suggestion {suggestion.ticket_number} updated to {suggestion.status}.")
        
        # Capture current filters for persistent redirect
        query_params = {}
        for param in ['ward', 'status', 'category', 'q', 'page']:
            val = request.POST.get(param)
            if val:
                query_params[param] = val
        query_string = f"?{urlencode(query_params)}" if query_params else ""
        redirect_url = f"{reverse('admin_suggestions')}{query_string}"
        
        return redirect(redirect_url)

    status_filter   = request.GET.get('status')
    category_filter = request.GET.get('category')
    ward_filter     = request.GET.get('ward')
    search_query    = request.GET.get('q', '').strip()

    suggestions = Suggestion.objects.select_related('submitted_by').all().order_by('-submitted_at')
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)
    if category_filter:
        suggestions = suggestions.filter(suggestion_category=category_filter)
    if ward_filter:
        suggestions = suggestions.filter(target_ward_number=ward_filter)
    if search_query:
        suggestions = suggestions.filter(
            Q(ticket_number__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(mobile_number__icontains=search_query)
        )

    paginator = Paginator(suggestions, 10)
    page_obj  = paginator.get_page(request.GET.get('page'))

    active_wards = Suggestion.objects.values_list('target_ward_number', flat=True).distinct().order_by('target_ward_number')

    # Single aggregate query replaces 3 separate count() calls
    sug_status_counts = {
        row['status']: row['cnt']
        for row in Suggestion.objects.values('status').annotate(cnt=Count('id'))
    }
    accepted_count = sug_status_counts.get(Suggestion.Status.ACCEPTED, 0)
    rejected_count = sug_status_counts.get(Suggestion.Status.REJECTED, 0)
    pending_count  = sug_status_counts.get(Suggestion.Status.PENDING, 0)

    return render(request, 'admin_suggestions.html', {
        'suggestions':       page_obj,
        'page_obj':          page_obj,
        'selected_status':   status_filter,
        'selected_category': category_filter,
        'selected_ward':     ward_filter,
        'search_query':      search_query,
        'active_wards':      active_wards,
        'CategoryChoices':   Suggestion.CategoryChoices,
        'StatusChoices':     Suggestion.Status,
        'accepted_count':    accepted_count,
        'rejected_count':    rejected_count,
        'pending_count':     pending_count,
        'admin_name':        request.user.name,
        'admin_employee_id': request.user.employee_id,
    })


@login_required
def admin_analytics(request):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access.")
        return redirect('home')

    timeframe = request.GET.get('timeframe', 'all')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    ward = request.GET.get('ward', '')

    kpis         = get_complaint_kpis(timeframe, start_date, end_date, ward)
    chart_data   = get_complaint_chart_data(timeframe, start_date, end_date, ward)
    sug_charts   = get_suggestion_chart_data(timeframe, start_date, end_date, ward)
    growth_chart = get_citizen_growth_chart_data(timeframe, start_date, end_date, ward)

    total_suggestions = Suggestion.objects.count()

    return render(request, 'admin_analytics.html', {
        'admin_name':          request.user.name,
        'admin_employee_id':   request.user.employee_id,
        'total_suggestions':   total_suggestions,
        'selected_timeframe':  timeframe,
        'start_date':          start_date,
        'end_date':            end_date,
        'selected_ward':       ward,
        **kpis,
        **chart_data,
        **sug_charts,
        **growth_chart,
    })


@login_required
def admin_citizen_detail(request, user_id):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access. Admins only.")
        return redirect('home')

    citizen = get_object_or_404(User, id=user_id, role=User.Role.CITIZEN)
    
    # Decrypt Aadhaar for admin viewing
    decrypted_aadhaar = decrypt_aadhaar(citizen.encrypted_aadhaar) if citizen.encrypted_aadhaar else "N/A"
    
    complaints_list = Complaint.objects.filter(citizen=citizen).order_by('-submitted_at')
    suggestions_list = Suggestion.objects.filter(submitted_by=citizen).order_by('-submitted_at')
    
    # Pagination: 5 items per page
    c_paginator = Paginator(complaints_list, 5)
    s_paginator = Paginator(suggestions_list, 5)
    
    complaints = c_paginator.get_page(request.GET.get('c_page'))
    suggestions = s_paginator.get_page(request.GET.get('s_page'))
    
    return render(request, 'admin_citizen_detail.html', {
        'citizen': citizen,
        'decrypted_aadhaar': decrypted_aadhaar,
        'complaints': complaints,
        'suggestions': suggestions,
        'admin_name': request.user.name,
        'admin_employee_id': request.user.employee_id,
    })


# ==============================================================================
# 4. CITIZEN RATING
# ==============================================================================

@login_required
def rate_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)

    if complaint.citizen != request.user:
        messages.error(request, "You can only rate your own complaints.")
        return redirect('citizen_tracking')
    if complaint.status != Complaint.Status.RESOLVED:
        messages.error(request, "You can only rate complaints that have been resolved.")
        return redirect('citizen_tracking')
    if complaint.rating is not None:
        messages.error(request, "You have already rated this complaint.")
        return redirect('citizen_tracking')

    if request.method == 'POST':
        try:
            rating_value = int(request.POST.get('rating', 0))
        except (ValueError, TypeError):
            messages.error(request, "Invalid rating value.")
            return redirect('citizen_tracking')

        if not (1 <= rating_value <= 5):
            messages.error(request, "Rating must be between 1 and 5 stars.")
            return redirect('citizen_tracking')

        complaint.rating = rating_value
        complaint.save()
        messages.success(request, f"Thank you! You rated this resolution {rating_value}/5 stars.")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('citizen_tracking')


# ==============================================================================
# 5. EXPORT TO CSV
# ==============================================================================

@login_required
def export_complaints_csv(request):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access. Admins only.")
        return redirect('home')

    ward_filter     = request.GET.get('ward')
    status_filter   = request.GET.get('status')
    category_filter = request.GET.get('category')

    complaints = Complaint.objects.select_related('citizen', 'resolved_by').all().order_by('-submitted_at')
    if ward_filter:
        complaints = complaints.filter(ward_number=ward_filter)
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if category_filter:
        complaints = complaints.filter(category=category_filter)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bm_complaints.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Problem ID', 'Citizen Name', 'Mobile No', 'Ward No',
        'Category', 'Sub Category', 'Description',
        'Target Address', 'Latitude', 'Longitude',
        'Status', 'Submitted At', 'Resolved At', 'Resolved By', 'Rating',
    ])
    for c in complaints:
        writer.writerow([
            c.problem_id, c.citizen.name, c.citizen.mobile_number, c.ward_number,
            c.get_category_display(), c.sub_category or '', c.description or '',
            c.target_address or '', c.latitude or '', c.longitude or '',
            c.get_status_display(),
            c.submitted_at.strftime('%Y-%m-%d %H:%M') if c.submitted_at else '',
            c.resolved_at.strftime('%Y-%m-%d %H:%M') if c.resolved_at else '',
            c.resolved_by.name if c.resolved_by else '',
            c.rating or '',
        ])
    return response


@login_required
def export_suggestions_csv(request):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Unauthorized access. Admins only.")
        return redirect('home')

    ward_filter     = request.GET.get('ward')
    status_filter   = request.GET.get('status')
    category_filter = request.GET.get('category')

    suggestions = Suggestion.objects.select_related('submitted_by').all().order_by('-submitted_at')
    if ward_filter:
        suggestions = suggestions.filter(target_ward_number=ward_filter)
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)
    if category_filter:
        suggestions = suggestions.filter(suggestion_category=category_filter)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bm_suggestions.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Ticket Number', 'Citizen Name', 'Mobile No', 'Citizen Ward No',
        'Target Ward No', 'Target Address', 'Category', 'Description',
        'Latitude', 'Longitude', 'Status', 'Submitted At',
    ])
    for s in suggestions:
        writer.writerow([
            s.ticket_number, s.name, s.mobile_number, s.user_ward_number or '',
            s.target_ward_number, s.target_address or '',
            s.get_suggestion_category_display(), s.description or '',
            s.latitude or '', s.longitude or '',
            s.get_status_display(),
            s.submitted_at.strftime('%Y-%m-%d %H:%M') if s.submitted_at else '',
        ])
    return response


# ==============================================================================
# 6. CITIZEN RE-OPEN COMPLAINT
# ==============================================================================

@login_required
def reopen_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)

    if complaint.citizen_id != request.user.pk:
        messages.error(request, "You can only re-open your own complaints.")
        return redirect('citizen_tracking')
    if complaint.status != Complaint.Status.RESOLVED:
        messages.error(request, "Only resolved complaints can be re-opened.")
        return redirect('citizen_tracking')

    if complaint.reopened_at is not None:
        messages.error(request, "This complaint has already been re-opened once and cannot be re-opened again.")
        return redirect('citizen_tracking')

    # Rating gate: satisfied citizens (4-5 stars) cannot reopen, unrated cannot reopen
    if complaint.rating is None:
        messages.error(request, "You must rate the resolution before you can re-open this complaint.")
        return redirect('citizen_tracking')
    elif complaint.rating >= 4:
        messages.error(
            request,
            f"You rated this resolution {complaint.rating}/5 stars (satisfactory). "
            "This complaint cannot be re-opened. Please submit a new complaint if the issue recurs."
        )
        return redirect('citizen_tracking')

    # 7-day window check (use stored deadline or fall back to resolved_at + 7 days)
    _deadline = complaint.reopen_deadline or (
        complaint.resolved_at + timedelta(days=7) if complaint.resolved_at else None
    )
    if _deadline and timezone.now() > _deadline:
        messages.error(request, "The 7-day re-open window for this complaint has expired.")
        return redirect('citizen_tracking')

    if request.method == 'POST':
        complaint.status          = Complaint.Status.PENDING
        complaint.reopened_at     = timezone.now()
        complaint.resolved_at     = None
        complaint.resolved_by     = None
        complaint.reopen_deadline = None
        complaint.rating          = None
        complaint.save()
        messages.success(
            request,
            f"{complaint.problem_id} has been re-opened. The municipality will investigate again."
        )
        return redirect('citizen_tracking')

    return redirect('citizen_tracking')


# ==============================================================================
# 7. CITIZEN APPEAL COMPLAINT
# ==============================================================================

@login_required
def appeal_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)

    if complaint.citizen_id != request.user.pk:
        messages.error(request, "You can only appeal your own complaints.")
        return redirect('citizen_tracking')

    if complaint.status != Complaint.Status.TERMINATED:
        messages.error(request, "Only terminated complaints can be appealed.")
        return redirect('citizen_tracking')

    if complaint.appealed_at:
        messages.error(request, "You have already appealed this complaint.")
        return redirect('citizen_tracking')

    if request.method == 'POST':
        appeal_text = request.POST.get('appeal_text', '').strip()
        if not appeal_text:
            messages.error(request, "Please provide a reason for your appeal.")
            return redirect('citizen_complaint_detail', complaint_id=complaint.id)
            
        complaint.appeal_text = appeal_text
        complaint.appealed_at = timezone.now()
        complaint.status = Complaint.Status.PENDING # Revert to pending for admin review
        complaint.save(update_fields=['appeal_text', 'appealed_at', 'status'])
        messages.success(request, f"Your appeal for {complaint.problem_id} has been submitted successfully.")
        return redirect('citizen_tracking')

    return redirect('citizen_tracking')
@login_required
def print_work_order(request, complaint_id):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Access denied.")
        return redirect('home')
        
    complaint = get_object_or_404(Complaint, id=complaint_id)
    return render(request, 'print_work_order.html', {'complaint': complaint})

@login_required
def print_suggestion(request, suggestion_id):
    if request.user.role != User.Role.ADMIN:
        messages.error(request, "Access denied.")
        return redirect('home')
        
    suggestion = get_object_or_404(Suggestion, id=suggestion_id)
    return render(request, 'print_suggestion.html', {'suggestion': suggestion})

from django.http import JsonResponse

@login_required
def mark_notifications_read(request):
    # Use the Role constant instead of a bare string for consistency
    if request.method == 'POST' and request.user.role == User.Role.CITIZEN:
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)


# ==============================================================================
# CUSTOM ERROR HANDLERS
# Registered in config/urls.py as handler400/403/404/500.
# These render branded error pages without exposing stack traces.
# ==============================================================================

def error_400(request, exception=None):
    """Bad Request — malformed input or CSRF failure."""
    return render(request, 'errors/400.html', status=400)


def error_403(request, exception=None):
    """Forbidden — authentication or permission failure."""
    return render(request, 'errors/403.html', status=403)


def error_404(request, exception=None):
    """Not Found — URL does not match any pattern."""
    return render(request, 'errors/404.html', status=404)


def error_500(request):
    """Internal Server Error — unhandled exception in production."""
    return render(request, 'errors/500.html', status=500)
