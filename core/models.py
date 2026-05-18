"""
core/models.py

Models for the Birnagar Municipality civic platform.
  - User        : unified model for Citizens and Municipal Admins
  - Suggestion  : citizen improvement suggestions for the city
  - Complaint   : civic issue reports with full lifecycle tracking
"""

import io
import os
import uuid
import random
import logging
import hashlib
from datetime import timedelta

from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

logger = logging.getLogger(__name__)

# Ward choices — dynamically sourced from settings so adding a new ward only
# requires changing WARD_COUNT in settings.py (or .env), not touching model code.
_WARD_CHOICES = getattr(settings, 'WARD_CHOICES', [(i, str(i)) for i in range(1, 15)])


# ==============================================================================
# 1. USER MANAGEMENT (Citizens & Admins)
# ==============================================================================

class CustomUserManager(BaseUserManager):
    """
    Custom manager — username is Mobile Number for Citizens, Employee ID for Admins.
    """
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('A username (mobile number or employee ID) must be provided.')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('employee_id', username)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Unified User model for both Citizens and Municipal Admins.
    """
    class Role(models.TextChoices):
        CITIZEN = 'CITIZEN', 'Citizen'
        ADMIN   = 'ADMIN',   'Municipal Admin'

    username       = models.CharField(max_length=50, unique=True,
                                      help_text="Mobile Number for Citizens; Employee ID for Admins")
    role           = models.CharField(max_length=10, choices=Role.choices, default=Role.CITIZEN)

    # Common fields
    name           = models.CharField(max_length=255)
    email          = models.EmailField(unique=True, blank=True, null=True)
    mobile_number  = models.CharField(max_length=15, unique=True)

    # Citizen-specific fields
    citizen_id        = models.CharField(max_length=9, unique=True, blank=True, null=True,
                                         help_text="Unique random ID like BM-XXXXXX")
    profile_photo     = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    address           = models.TextField(blank=True, null=True,
                                         help_text="Complete address as per Aadhaar")
    # Stores Fernet-encrypted Aadhaar ciphertext (see core/utils.py)
    encrypted_aadhaar = models.CharField(max_length=512, blank=True, null=True,
                                         help_text="Fernet-encrypted Aadhaar number at rest")
    # SHA-256 hash of the plain Aadhaar — used ONLY for uniqueness checks.
    # One-way: cannot be reversed back to the Aadhaar number.
    aadhaar_hash      = models.CharField(max_length=64, unique=True, blank=True, null=True,
                                         help_text="SHA-256 hash of Aadhaar for duplicate detection")
    ward_number       = models.IntegerField(choices=_WARD_CHOICES, blank=True, null=True)

    # Admin-specific fields
    employee_id = models.CharField(max_length=50, unique=True, blank=True, null=True)

    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD  = 'username'
    REQUIRED_FIELDS = ['name', 'mobile_number']

    def save(self, *args, **kwargs):
        # Auto-generate random citizen_id for Citizens if not set
        if not self.citizen_id and self.role == self.Role.CITIZEN:
            while True:
                cid = f"BM-{random.randint(100000, 999999)}"
                if not User.objects.filter(citizen_id=cid).exists():
                    self.citizen_id = cid
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


# ==============================================================================
# 2. SUGGESTIONS SYSTEM
# ==============================================================================

class Suggestion(models.Model):
    """
    General improvement suggestions submitted by citizens.
    """
    class Status(models.TextChoices):
        PENDING  = 'PENDING',  'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'

    class CategoryChoices(models.TextChoices):
        GARBAGE      = 'GARBAGE',      'Garbage & Solid Waste Management'
        ROADS        = 'ROADS',        'Roads & Infrastructure'
        DRAINAGE     = 'DRAINAGE',     'Drainage & Waterlogging'
        STREETLIGHTS = 'STREETLIGHTS', 'Public Streetlights'
        WATER        = 'WATER',        'Drinking Water Supply'
        HEALTH       = 'HEALTH',       'Public Health & Sanitation'
        PARKS        = 'PARKS',        'Parks & Recreation'
        OTHER        = 'OTHER',        'Other'

    ticket_number  = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    submitted_by   = models.ForeignKey(User, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='suggestions')

    # Static snapshot of user info at submission time
    name           = models.CharField(max_length=255, default='Anonymous')
    mobile_number  = models.CharField(max_length=15, default='')
    aadhaar_number = models.CharField(max_length=512, default='')  # stores encrypted value
    user_ward_number = models.IntegerField(choices=_WARD_CHOICES, blank=True, null=True)
    user_address   = models.TextField(blank=True, null=True)

    # Improvement area details
    target_ward_number = models.IntegerField(choices=_WARD_CHOICES, default=1, db_index=True)
    target_address     = models.TextField(default='', help_text='Full address of the implementation area')

    # Suggestion details
    suggestion_category = models.CharField(max_length=50, choices=CategoryChoices.choices,
                                           default=CategoryChoices.OTHER)
    description = models.TextField(blank=True, null=True,
                                   help_text="Mandatory when category is 'Other'")
    photo       = models.ImageField(upload_to='suggestions_photos/', help_text='Photo of this place is mandatory')

    # Geo-coordinates
    latitude  = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            while True:
                tail = random.randint(1000, 9999)
                proposed = f"SUG-WARD{self.target_ward_number}-{tail}"
                if not Suggestion.objects.filter(ticket_number=proposed).exists():
                    self.ticket_number = proposed
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.ticket_number}] Suggestion by {self.name} on {self.submitted_at.strftime('%Y-%m-%d')}"


# ==============================================================================
# 3. NOTIFICATIONS
# ==============================================================================

class Notification(models.Model):
    """
    In-app notifications for citizens regarding their complaint status updates.
    """
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message    = models.CharField(max_length=500)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"To {self.user.username}: {self.message[:50]}"


# ==============================================================================
# 4. COMPLAINT MANAGEMENT SYSTEM (Core)
# ==============================================================================

class Complaint(models.Model):
    """
    Core model tracking civic issues reported by citizens, with full lifecycle.
    """
    class Status(models.TextChoices):
        PENDING     = 'PENDING',     'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        RESOLVED    = 'RESOLVED',    'Resolved'
        TERMINATED  = 'TERMINATED',  'Terminated'

    class Priority(models.TextChoices):
        LOW    = 'LOW',    'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH   = 'HIGH',   'High'
        URGENT = 'URGENT', 'Urgent'

    class CategoryChoices(models.TextChoices):
        GARBAGE      = 'GARBAGE',      'Garbage & Solid Waste Management'
        ROADS        = 'ROADS',        'Roads & Infrastructure'
        DRAINAGE     = 'DRAINAGE',     'Drainage & Waterlogging'
        STREETLIGHTS = 'STREETLIGHTS', 'Public Streetlights'
        WATER        = 'WATER',        'Drinking Water Supply'
        HEALTH       = 'HEALTH',       'Public Health & Sanitation'
        OTHER        = 'OTHER',        'Other'

    problem_id  = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    citizen     = models.ForeignKey(User, on_delete=models.CASCADE,
                                    related_name='complaints',
                                    limit_choices_to={'role': 'CITIZEN'})
    ward_number = models.IntegerField(choices=_WARD_CHOICES, db_index=True)

    # Issue details
    category     = models.CharField(max_length=50, choices=CategoryChoices.choices,
                                    default=CategoryChoices.OTHER, db_index=True)
    sub_category = models.CharField(max_length=255, blank=True, null=True)
    description  = models.TextField(blank=True, null=True)

    # Location
    target_address = models.TextField(blank=True, null=True)
    latitude       = models.FloatField(blank=True, null=True)
    longitude      = models.FloatField(blank=True, null=True)

    # Media proof
    photo1 = models.ImageField(upload_to='complaints_photos/', blank=True, null=True)
    photo2 = models.ImageField(upload_to='complaints_photos/', blank=True, null=True)
    photo3 = models.ImageField(upload_to='complaints_photos/', blank=True, null=True)
    video  = models.FileField(upload_to='complaints_videos/', blank=True, null=True)

    # Lifecycle tracking
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)
    resolved_by  = models.ForeignKey(User, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name='resolved_complaints',
                                     limit_choices_to={'role': 'ADMIN'})

    # Admin priority & resolution notes
    priority         = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.LOW,
        blank=True, help_text="Issue priority set by admin", db_index=True
    )
    resolution_notes = models.TextField(
        blank=True, null=True,
        help_text="Admin remarks on what action was taken at resolution"
    )
    resolution_photo = models.ImageField(
        upload_to='resolutions_photos/', blank=True, null=True,
        help_text="Proof of resolution photo uploaded by admin"
    )

    # Re-open window (citizen can reopen within 7 days of resolution)
    reopened_at     = models.DateTimeField(null=True, blank=True)
    reopen_deadline = models.DateTimeField(null=True, blank=True)

    # Appeal window (citizen can appeal if complaint is terminated)
    appeal_text = models.TextField(blank=True, null=True)
    appealed_at = models.DateTimeField(null=True, blank=True)

    # Citizen satisfaction rating (1–5, given once after resolution)
    rating = models.IntegerField(
        null=True, blank=True,
        choices=[(i, f'{i} Star{"s" if i > 1 else ""}') for i in range(1, 6)],
        help_text="Citizen satisfaction rating (1–5) after resolution"
    )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compress_image(self, image_field):
        """
        Compress an uploaded image to max 1200x1200 px, JPEG 75%.
        Uses os.path.basename() so the upload_to prefix is not doubled,
        which previously caused deeply-nested media folders.
        """
        if not image_field or not image_field.name:
            return
        try:
            img = Image.open(image_field)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            img.thumbnail((1200, 1200), Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=75, optimize=True)
            buffer.seek(0)

            base_name = os.path.splitext(os.path.basename(image_field.name))[0]
            image_field.save(f"{base_name}.jpg", ContentFile(buffer.read()), save=False)
        except Exception as exc:
            logger.warning("[Image Compression] Could not compress %s: %s", image_field.name, exc)

    # ------------------------------------------------------------------
    # Save lifecycle
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        # 1. Auto-attach ward number from citizen profile if not provided
        # BUG FIX: was checking self.citizen_id (the BM-XXXXXX string PK alias) instead
        # of self.citizen (the FK). Now correctly checks if the FK is set.
        if not self.ward_number and self.citizen_id is not None:
            try:
                self.ward_number = self.citizen.ward_number
            except Exception:
                pass

        # 2. Auto-generate a unique Problem ID on first save
        if not self.problem_id:
            while True:
                tail = random.randint(1000, 9999)
                proposed = f"BIR-WARD{self.ward_number}-{tail}"
                if not Complaint.objects.filter(problem_id=proposed).exists():
                    self.problem_id = proposed
                    break

        # 3. Set 7-day re-open deadline on first resolution
        if self.status == self.Status.RESOLVED and not self.reopen_deadline:
            self.reopen_deadline = timezone.now() + timedelta(days=7)

        super().save(*args, **kwargs)

        # 4. Compress photos after save (file paths are finalised by then)
        changed = False
        for field_name in ('photo1', 'photo2', 'photo3', 'resolution_photo'):
            field = getattr(self, field_name)
            if field and getattr(field, 'name', None) and not field.name.endswith('.jpg'):
                self._compress_image(field)
                changed = True
        if changed:
            Complaint.objects.filter(pk=self.pk).update(
                photo1=self.photo1,
                photo2=self.photo2,
                photo3=self.photo3,
                resolution_photo=self.resolution_photo,
            )

    def __str__(self):
        return f"[{self.problem_id}] Ward {self.ward_number} — {self.get_status_display()}"
