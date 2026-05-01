from .models import Notification

def unread_notifications(request):
    if request.user.is_authenticated and request.user.role == 'CITIZEN':
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
        return {
            'unread_notifications_count': count,
            'recent_notifications': notifications
        }
    return {}
