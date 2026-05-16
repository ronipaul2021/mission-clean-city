from django.urls import path
from . import views

urlpatterns = [
    # 0. Public pages
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('suggestions/', views.suggestions, name='suggestions'),

    # 1. Authentication
    path('register/citizen/', views.citizen_register, name='citizen_register'),
    path('register/citizen/verify-otp/', views.verify_otp, name='verify_otp'),
    path('login/citizen/', views.citizen_login, name='citizen_login'),
    path('register/admin/', views.admin_register, name='admin_register'),
    path('register/admin/verify-otp/', views.verify_admin_otp, name='verify_admin_otp'),
    path('login/admin/', views.admin_login, name='admin_login'),
    path('logout/', views.user_logout, name='logout'),

    # 1b. Change/Reset password
    path('change-password/', views.change_password, name='change_password'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('forgot-password/verify-otp/', views.forgot_password_verify_otp, name='forgot_password_verify_otp'),
    path('forgot-password/reset-password/', views.forgot_password_reset, name='forgot_password_reset'),
    
    # 1d. Admin Forgot Password
    path('admin-forgot-password/', views.admin_forgot_password, name='admin_forgot_password'),
    path('admin-forgot-password/verify/', views.admin_forgot_password_verify_otp, name='admin_forgot_password_verify_otp'),
    path('admin-forgot-password/reset/', views.admin_forgot_password_reset, name='admin_forgot_password_reset'),

    # 1c. Profile edit
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/edit/verify-email/', views.verify_email_update, name='verify_email_update'),
    path('admin-profile/edit/', views.admin_profile_edit, name='admin_profile_edit'),
    path('admin-profile/edit/verify/', views.admin_verify_email_update, name='admin_verify_email_update'),


    # 2. Submit problem
    path('submit-problem/', views.submit_problem, name='submit_problem'),
    path('submit-problem/check-duplicate/', views.check_duplicate, name='check_duplicate'),
    path('submit-problem/ai-assist/', views.ai_assist_description, name='ai_assist_description'),

    # 3. Dashboards & tracking
    path('track/', views.citizen_tracking, name='citizen_tracking'),
    path('complaint/<int:complaint_id>/', views.citizen_complaint_detail, name='citizen_complaint_detail'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/citizen/<int:user_id>/', views.admin_citizen_detail, name='admin_citizen_detail'),
    path('admin-citizens/', views.admin_citizens_directory, name='admin_citizens_directory'),
    path('admin-suggestions/', views.admin_suggestions, name='admin_suggestions'),
    path('admin-analytics/', views.admin_analytics, name='admin_analytics'),

    # 4. Citizen rating
    path('rate-complaint/<int:complaint_id>/', views.rate_complaint, name='rate_complaint'),

    # 5. CSV export & Printing
    path('admin-dashboard/export-csv/', views.export_complaints_csv, name='export_complaints_csv'),
    path('admin-suggestions/export-csv/', views.export_suggestions_csv, name='export_suggestions_csv'),
    path('admin-dashboard/print/<int:complaint_id>/', views.print_work_order, name='print_work_order'),
    path('admin-suggestions/print/<int:suggestion_id>/', views.print_suggestion, name='print_suggestion'),

    # 6. Reopen complaint
    path('reopen-complaint/<int:complaint_id>/', views.reopen_complaint, name='reopen_complaint'),

    # 7. Appeal complaint
    path('appeal-complaint/<int:complaint_id>/', views.appeal_complaint, name='appeal_complaint'),
    # 8. Notifications
    path('mark-notifications-read/', views.mark_notifications_read, name='mark_notifications_read'),
    # 9. AI Chatbot
    path('chatbot-query/', views.chatbot_query, name='chatbot_query'),
]
