"""
core/serializers.py

Lightweight dict-conversion utilities for all models.

Purpose:
  - Centralize all data-transformation logic in one place
  - Provide safe serialization that NEVER exposes encrypted Aadhaar or passwords
  - Make it easy to add a REST API later (just wrap these with DRF serializers)
  - Keep templates clean — pass .to_dict() output instead of raw model instances
    when you need flexible data structures

Usage:
    from core.serializers import ComplaintSerializer, UserSerializer, SuggestionSerializer

    data = ComplaintSerializer.to_dict(complaint)
    safe = UserSerializer.to_safe_dict(user)
"""

from django.utils import timezone


class UserSerializer:
    """Serialization helpers for the User model."""

    @staticmethod
    def to_safe_dict(user) -> dict:
        """
        Returns a safe dict of user data.
        NEVER includes: password, encrypted_aadhaar, aadhaar_hash.
        Suitable for JSON responses and template context.
        """
        return {
            'id':            user.pk,
            'citizen_id':    getattr(user, 'citizen_id', None),
            'employee_id':   getattr(user, 'employee_id', None),
            'name':          user.name,
            'username':      user.username,    # mobile number for citizens
            'mobile_number': getattr(user, 'mobile_number', user.username),
            'role':          user.role,
            'ward_number':   user.ward_number,
            'address':       getattr(user, 'address', ''),
            'email':         user.email or '',
            'is_active':     user.is_active,
            'date_joined':   user.date_joined.isoformat() if user.date_joined else None,
            'has_photo':     bool(user.profile_photo),
        }

    @staticmethod
    def to_admin_dict(user) -> dict:
        """
        Returns a richer dict for admin use.
        Still NEVER exposes encrypted_aadhaar or aadhaar_hash.
        Decrypted Aadhaar must be fetched separately via decrypt_aadhaar().
        """
        base = UserSerializer.to_safe_dict(user)
        base.update({
            'is_staff':  user.is_staff,
            'is_active': user.is_active,
        })
        return base


class ComplaintSerializer:
    """Serialization helpers for the Complaint model."""

    @staticmethod
    def to_dict(complaint, include_citizen: bool = True) -> dict:
        """
        Convert a Complaint instance to a clean dict.
        Safe for JSON responses and CSV export logic.
        """
        data = {
            'id':                complaint.id,
            'problem_id':        complaint.problem_id,
            'ward_number':       complaint.ward_number,
            'category':          complaint.category,
            'category_display':  complaint.get_category_display(),
            'sub_category':      complaint.sub_category or '',
            'description':       complaint.description or '',
            'status':            complaint.status,
            'status_display':    complaint.get_status_display(),
            'priority':          complaint.priority or '',
            'priority_display':  complaint.get_priority_display() if complaint.priority else '',
            'target_address':    complaint.target_address or '',
            'latitude':          str(complaint.latitude) if complaint.latitude else '',
            'longitude':         str(complaint.longitude) if complaint.longitude else '',
            'rating':            complaint.rating,
            'resolution_notes':  complaint.resolution_notes or '',
            'appeal_text':       complaint.appeal_text or '',
            'submitted_at':      complaint.submitted_at.isoformat() if complaint.submitted_at else None,
            'resolved_at':       complaint.resolved_at.isoformat() if complaint.resolved_at else None,
            'reopen_deadline':   complaint.reopen_deadline.isoformat() if complaint.reopen_deadline else None,
            'has_photo1':        bool(complaint.photo1),
            'has_photo2':        bool(complaint.photo2),
            'has_photo3':        bool(complaint.photo3),
            'has_video':         bool(complaint.video),
            'has_resolution_photo': bool(complaint.resolution_photo),
            'resolved_by_name':  (
                complaint.resolved_by.name
                if complaint.resolved_by else 'Unassigned'   # NULL-safe
            ),
            'resolved_by_id':    (
                complaint.resolved_by.employee_id
                if complaint.resolved_by else ''             # NULL-safe
            ),
        }
        if include_citizen and hasattr(complaint, 'citizen') and complaint.citizen:
            data['citizen'] = UserSerializer.to_safe_dict(complaint.citizen)
        return data

    @staticmethod
    def to_csv_row(complaint) -> list:
        """
        Returns a flat list suitable for csv.writer.writerow().
        Used by the CSV export view.
        """
        d = ComplaintSerializer.to_dict(complaint)
        return [
            d['problem_id'],
            d['category_display'],
            d['sub_category'],
            d['status_display'],
            d['priority_display'],
            d.get('citizen', {}).get('name', ''),
            d.get('citizen', {}).get('mobile_number', ''),
            d['ward_number'],
            d['target_address'],
            complaint.submitted_at.strftime("%Y-%m-%d %H:%M") if complaint.submitted_at else '',
            complaint.resolved_at.strftime("%Y-%m-%d %H:%M") if complaint.resolved_at else '',
            d['rating'] or '',
        ]


class SuggestionSerializer:
    """Serialization helpers for the Suggestion model."""

    @staticmethod
    def to_dict(suggestion, include_submitter: bool = True) -> dict:
        data = {
            'id':                  suggestion.id,
            'ticket_number':       suggestion.ticket_number,
            'name':                suggestion.name,
            'mobile_number':       suggestion.mobile_number,
            'suggestion_category': suggestion.suggestion_category,
            'category_display':    suggestion.get_suggestion_category_display(),
            'description':         suggestion.description,
            'target_address':      suggestion.target_address or '',
            'target_ward_number':  suggestion.target_ward_number,
            'status':              suggestion.status,
            'status_display':      suggestion.get_status_display(),
            'admin_remarks':       suggestion.admin_remarks or '',
            'submitted_at':        suggestion.submitted_at.isoformat() if suggestion.submitted_at else None,
            'has_photo':           bool(suggestion.photo),
        }
        if include_submitter and hasattr(suggestion, 'submitted_by') and suggestion.submitted_by:
            data['submitted_by'] = UserSerializer.to_safe_dict(suggestion.submitted_by)
        return data

    @staticmethod
    def to_csv_row(suggestion) -> list:
        d = SuggestionSerializer.to_dict(suggestion)
        return [
            d['ticket_number'],
            d['category_display'],
            d['description'],
            d['target_address'],
            d['target_ward_number'],
            d['status_display'],
            d['admin_remarks'],
            d.get('submitted_by', {}).get('name', d['name']),
            d.get('submitted_by', {}).get('mobile_number', d['mobile_number']),
            suggestion.submitted_at.strftime("%Y-%m-%d %H:%M") if suggestion.submitted_at else '',
        ]
