from django.http import HttpResponse


class TelegramCorsMiddleware:
    """Middleware для добавления CORS заголовков для Telegram Mini App"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'OPTIONS':
            response = HttpResponse()
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-API-Key'
            response['Access-Control-Max-Age'] = '86400'
            return response
        
        response = self.get_response(request)
        
        response['X-Frame-Options'] = 'ALLOWALL'
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-API-Key'
        response['Access-Control-Max-Age'] = '86400'
        
        return response

