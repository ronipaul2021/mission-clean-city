"""
core/services/user_service.py

Business logic for User/Citizen operations extracted from views.py.
"""

import logging
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.conf import settings

logger = logging.getLogger(__name__)


class UserService:
    """Service class for user registration, profile management, and authentication helpers."""

    @staticmethod
    def register_citizen(form_data: dict):
        """
        Validate and create a new Citizen user.

        Args:
            form_data: Dict with keys: name, username (mobile), password,
                       aadhaar, ward_number, address, email (optional).

        Returns:
            (user, error_message) — user is None on error.
        """
        from core.models import User
        from core.utils import encrypt_aadhaar, hash_aadhaar

        mobile   = form_data.get('username', '').strip()
        name     = form_data.get('name', '').strip()
        password = form_data.get('password', '').strip()
        aadhaar  = form_data.get('aadhaar', '').strip()
        ward     = form_data.get('ward_number')
        address  = form_data.get('address', '').strip()
        email    = form_data.get('email', '').strip()

        # Validation
        if User.objects.filter(username=mobile).exists():
            return None, "A citizen with this mobile number already exists."

        aadhaar_hash = hash_aadhaar(aadhaar)
        if User.objects.filter(aadhaar_hash=aadhaar_hash).exists():
            return None, "This Aadhaar number is already registered with another account."

        try:
            user = User.objects.create(
                username=mobile,
                name=name,
                role=User.Role.CITIZEN,
                encrypted_aadhaar=encrypt_aadhaar(aadhaar),
                aadhaar_hash=aadhaar_hash,
                ward_number=int(ward) if ward else None,
                address=address,
                email=email,
                is_active=True,
            )
            user.set_password(password)
            user.save(update_fields=['password'])
            logger.info("New citizen registered: %s (ward %s)", mobile, ward)
            return user, None
        except Exception as exc:
            logger.error("Citizen registration failed: %s", exc)
            return None, f"Registration failed: {exc}"

    @staticmethod
    def update_profile(user, form_data: dict, profile_photo=None):
        """
        Update a citizen's editable profile fields.
        Returns (success, error_message).
        """
        from core.utils import auto_crop_face

        address     = form_data.get('address', '').strip()
        ward_number = form_data.get('ward_number')
        email       = form_data.get('email', '').strip()

        if address:
            user.address = address
        if ward_number:
            try:
                user.ward_number = int(ward_number)
            except ValueError:
                return False, "Invalid ward number."
        if email:
            user.email = email

        if profile_photo:
            processed, err = auto_crop_face(profile_photo)
            if err:
                return False, f"Profile photo error: {err}"
            user.profile_photo = processed

        user.save()
        logger.info("Profile updated for user %s", user.username)
        return True, None

    @staticmethod
    def change_password(user, old_password: str, new_password: str):
        """
        Validates old password and sets new password.
        Returns (success, error_message).
        """
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        if not user.check_password(old_password):
            return False, "Current password is incorrect."

        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            return False, " ".join(exc.messages)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        logger.info("Password changed for user %s", user.username)
        return True, None

    @staticmethod
    def get_citizen_summary(user):
        """
        Returns a summary dict for the citizen detail view (admin use).
        Decrypts Aadhaar for authorized admin display.
        """
        from core.models import Complaint, Suggestion
        from core.utils import decrypt_aadhaar
        from core.serializers import UserSerializer

        complaints  = Complaint.objects.filter(citizen=user).select_related('resolved_by').order_by('-submitted_at')
        suggestions = Suggestion.objects.filter(submitted_by=user).order_by('-submitted_at')

        return {
            'citizen':           user,
            'decrypted_aadhaar': decrypt_aadhaar(user.encrypted_aadhaar) if user.encrypted_aadhaar else '—',
            'complaints':        complaints,
            'suggestions':       suggestions,
            'complaint_count':   complaints.count(),
            'suggestion_count':  suggestions.count(),
            'citizen_dict':      UserSerializer.to_safe_dict(user),
        }
