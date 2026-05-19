class NoCacheSecureMiddleware:
    """
    Middleware to completely prevent browser caching on secure (authenticated) pages.
    Adds Cache-Control, Pragma, and Expires headers to HTTP responses for authenticated requests.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Apply cache prevention to all authenticated pages to protect sensitive user data.
        if hasattr(request, 'user') and request.user.is_authenticated:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
        return response
