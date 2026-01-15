from functools import wraps
from django.http import JsonResponse
import logging

from orders.models import Settings

logger = logging.getLogger('orders')

def api_key_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        settings = Settings.get_settings()
        received_api_key = request.headers.get('X-API-Key') or request.headers.get('x-api-key')
        
        if not received_api_key or received_api_key != settings.api_key:
            logger.warning(f"Invalid or missing API key for {view_func.__name__}")
            return JsonResponse({'error': 'Invalid or missing API key'}, status=403)
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view