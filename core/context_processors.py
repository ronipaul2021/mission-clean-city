from .models import Notification, User


def unread_notifications(request):
    if request.user.is_authenticated and request.user.role == User.Role.CITIZEN:
        # Single query — fetch the 10 most recent; derive unread count from a
        # separate lightweight count() so we avoid loading unneeded rows.
        notifications = list(
            Notification.objects.filter(user=request.user)
            .order_by('-created_at')[:10]
        )
        unread_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return {
            'unread_notifications_count': unread_count,
            'recent_notifications': notifications,
        }
    return {}
