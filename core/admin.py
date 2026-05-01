from django.contrib import admin
from .models import User, Complaint, Suggestion, Notification


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'name', 'role', 'mobile_number', 'employee_id', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'name', 'mobile_number', 'employee_id')


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('problem_id', 'citizen', 'ward_number', 'status', 'submitted_at')
    list_filter = ('status', 'ward_number', 'submitted_at')
    search_fields = ('problem_id', 'description')
    readonly_fields = ('problem_id', 'photo1', 'photo2', 'photo3', 'video')


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'submitted_by', 'suggestion_category', 'status', 'submitted_at')
    list_filter = ('status', 'suggestion_category', 'target_ward_number')
    # BUG FIX: 'implementation_address' was renamed to 'target_address' in migration 0007.
    # Using the correct field name prevents a Django admin crash on search.
    search_fields = ('ticket_number', 'description', 'target_address', 'name', 'mobile_number')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'user__name', 'message')
    readonly_fields = ('created_at',)
