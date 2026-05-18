from django.test import TestCase, override_settings
from django.urls import reverse
from core.models import User

class ErrorViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create a test citizen
        cls.citizen = User.objects.create_user(
            username='9999999999',
            password='Password123',
            name='Test Citizen',
            mobile_number='9999999999',
            role=User.Role.CITIZEN,
            ward_number=1
        )
        # Create a test admin
        cls.admin = User.objects.create_user(
            username='BM-EMP-0001',
            password='Password123',
            name='Test Admin',
            mobile_number='8888888888',
            role=User.Role.ADMIN,
            employee_id='BM-EMP-0001'
        )

    def test_custom_404_catch_all(self):
        """Test that non-existent URLs trigger the custom 404 error page due to the catch-all pattern."""
        response = self.client.get('/invalid-page-path-123/')
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'errors/404.html')
        self.assertContains(response, 'Location Not Found', status_code=404)
        self.assertContains(response, 'Go to Homepage', status_code=404)

    def test_direct_400_rendering(self):
        """Test direct rendering of 400 Bad Request error view."""
        from core.views import error_400
        request = self.client.get('/').wsgi_request
        response = error_400(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Invalid Request', response.content)

    def test_direct_403_rendering(self):
        """Test direct rendering of 403 Forbidden error view."""
        from core.views import error_403
        request = self.client.get('/').wsgi_request
        response = error_403(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b'Access Restricted', response.content)

    def test_direct_500_rendering(self):
        """Test direct rendering of 500 Internal Server Error view."""
        from core.views import error_500
        request = self.client.get('/').wsgi_request
        response = error_500(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'System Interruption', response.content)

    def test_anonymous_redirects(self):
        """Verify that private views correctly redirect anonymous users to login."""
        protected_urls = [
            'suggestions',
            'submit_problem',
            'change_password',
            'profile_edit',
            'admin_dashboard',
            'admin_citizens_directory',
            'admin_suggestions',
            'admin_analytics',
        ]
        for url_name in protected_urls:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302, f"{url_name} did not redirect.")
            self.assertIn('login', response.url)

    def test_citizen_forbidden_admin_access(self):
        """Test that logged-in Citizen is redirected if they try to access Admin Dashboard."""
        self.client.login(username='9999999999', password='Password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('submit_problem'))

    def test_admin_forbidden_citizen_access(self):
        """Test that logged-in Admin receives branded 403 error page if they try to access Citizen-only views."""
        self.client.login(username='BM-EMP-0001', password='Password123')
        # Accessing submit_problem
        response = self.client.get(reverse('submit_problem'))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'errors/403.html')
        self.assertContains(response, 'Access Restricted', status_code=403)

    def test_public_pages_ok(self):
        """Verify that all public views load successfully with 200 OK."""
        public_urls = ['home', 'about', 'citizen_login', 'admin_login', 'citizen_register']
        for url_name in public_urls:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, f"{url_name} failed to load.")
            self.assertContains(response, 'Birnagar Municipality')

        # Since an admin already exists in the test DB, accessing admin_register anonymously redirects to admin_login.
        response = self.client.get(reverse('admin_register'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin_login'), response.url)

        # Logged-in admin should be able to access the admin registration page.
        self.client.login(username='BM-EMP-0001', password='Password123')
        response = self.client.get(reverse('admin_register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Birnagar Municipality')


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
class AnalyticsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create a test citizen
        cls.citizen = User.objects.create_user(
            username='9999999999',
            password='Password123',
            name='Test Citizen',
            mobile_number='9999999999',
            role=User.Role.CITIZEN,
            ward_number=1
        )
        # Create a test admin
        cls.admin = User.objects.create_user(
            username='BM-EMP-0001',
            password='Password123',
            name='Test Admin',
            mobile_number='8888888888',
            role=User.Role.ADMIN,
            employee_id='BM-EMP-0001'
        )
        
        # Let's create some complaints to populate analytics data
        from core.models import Complaint, Suggestion
        cls.c1 = Complaint.objects.create(
            citizen=cls.citizen,
            ward_number=1,
            category=Complaint.CategoryChoices.STREETLIGHTS,
            status=Complaint.Status.PENDING,
            description="Broken streetlight"
        )
        cls.c2 = Complaint.objects.create(
            citizen=cls.citizen,
            ward_number=2,
            category=Complaint.CategoryChoices.STREETLIGHTS,
            status=Complaint.Status.RESOLVED,
            description="Flickering light"
        )
        cls.c3 = Complaint.objects.create(
            citizen=cls.citizen,
            ward_number=1,
            category=Complaint.CategoryChoices.DRAINAGE,
            status=Complaint.Status.IN_PROGRESS,
            description="Blocked drain"
        )
        
        # Let's create some suggestions
        cls.s1 = Suggestion.objects.create(
            submitted_by=cls.citizen,
            target_ward_number=1,
            suggestion_category=Suggestion.CategoryChoices.STREETLIGHTS,
            description="Use LED lamps",
            photo="suggestions_photos/dummy.jpg"
        )

    def test_analytics_view_as_admin(self):
        """Verify that an authenticated admin can access the analytics view successfully."""
        self.client.login(username='BM-EMP-0001', password='Password123')
        response = self.client.get(reverse('admin_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin_analytics.html')
        
        # Verify basic KPI counts in the context
        self.assertEqual(response.context['total_complaints'], 3)
        self.assertEqual(response.context['resolved_complaints'], 1)
        self.assertEqual(response.context['pending_complaints'], 1)
        self.assertEqual(response.context['in_progress_count'], 1)
        self.assertEqual(response.context['top_category'], 'Public Streetlights')
        self.assertEqual(response.context['top_ward'], 1)

    def test_analytics_view_timeframe_filters(self):
        """Test timeframes on analytics page (e.g. today, weekly, monthly, custom)."""
        self.client.login(username='BM-EMP-0001', password='Password123')
        
        for timeframe in ['all', 'today', 'weekly', 'monthly', 'quarterly', 'yearly']:
            response = self.client.get(reverse('admin_analytics'), {'timeframe': timeframe})
            self.assertEqual(response.status_code, 200)

    def test_analytics_view_ward_filter(self):
        """Test ward filter in analytics."""
        self.client.login(username='BM-EMP-0001', password='Password123')
        
        response = self.client.get(reverse('admin_analytics'), {'ward': '1'})
        self.assertEqual(response.status_code, 200)
        # Ward 1 has 2 complaints (c1 and c3)
        self.assertEqual(response.context['total_complaints'], 2)
        
        response = self.client.get(reverse('admin_analytics'), {'ward': '2'})
        self.assertEqual(response.status_code, 200)
        # Ward 2 has 1 complaint (c2)
        self.assertEqual(response.context['total_complaints'], 1)

    def test_cache_invalidation_on_complaint_change(self):
        """Verify that creating/updating a complaint invalidates the analytics cache."""
        self.client.login(username='BM-EMP-0001', password='Password123')
        
        # First load should cache values
        response = self.client.get(reverse('admin_analytics'))
        self.assertEqual(response.context['total_complaints'], 3)
        
        # Create a new complaint - this should trigger cache invalidation
        from core.models import Complaint
        from core.utils import invalidate_analytics_cache
        
        Complaint.objects.create(
            citizen=self.citizen,
            ward_number=3,
            category=Complaint.CategoryChoices.GARBAGE,
            status=Complaint.Status.PENDING,
            description="Garbage piling up"
        )
        
        invalidate_analytics_cache()
        
        response = self.client.get(reverse('admin_analytics'))
        self.assertEqual(response.context['total_complaints'], 4)
