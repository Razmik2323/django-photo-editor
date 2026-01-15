import json
import logging
import os
import uuid
from io import BytesIO

from django.conf import settings as django_settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from PIL import Image, ImageOps

from orders.models import Order, Photo, Settings
from orders.services import create_order, upload_temporary_photo, upload_temporary_photos_batch
from .decorators import api_key_required
from .helpers import (
    validate_image_size, convert_image_to_jpeg
)

logger = logging.getLogger('orders')


@csrf_exempt
@require_http_methods(["POST"])
@api_key_required
def convert_photo(request):
    try:
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return JsonResponse({'error': 'No file provided'}, status=400)


        size_error = validate_image_size(uploaded_file, django_settings.MAX_PHOTO_SIZE, 'Файл')
        if size_error:
            return size_error


        buffer, width, height = convert_image_to_jpeg(uploaded_file)
        if not buffer:
            return JsonResponse(
                {'error': 'Не удалось обработать файл. Убедитесь, что это изображение поддерживаемого формата.'},
                status=400
            )

        response = HttpResponse(buffer.getvalue(), content_type="image/jpeg")
        response["X-Width"] = str(width)
        response["X-Height"] = str(height)
        response["X-Converted-Format"] = "image/jpeg"

        logger.info(
            f"convert_photo: converted file '{uploaded_file.name}' ({uploaded_file.size} bytes) "
            f"to JPEG {width}x{height}"
        )
        return response

    except Exception as e:
        logger.error(f"Unexpected error in convert_photo: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_config(request):
    try:
        settings = Settings.get_settings()
        return JsonResponse({
            'api_key': settings.api_key,
            'question_link': settings.question_link or ''
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    return JsonResponse({
        'status': 'ok',
        'time': timezone.now().isoformat()
    }, status=200)


@csrf_exempt
@require_http_methods(["POST"])
@api_key_required
def create_lead(request):
    try:
        order, created_photos = create_order(request.POST, request.FILES)
        return JsonResponse({
            'success': True,
            'order_id': str(order.id),
            'photos_count': len(created_photos),
            'photos': created_photos
        }, status=201)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error creating lead: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_key_required
def upload_temp_photo(request):
    try:
        photo = upload_temporary_photo(request.POST, request.FILES)
        return JsonResponse({'success': True, 'photo_id': str(photo.id)}, status=201)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error uploading temporary photo: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_key_required
def upload_temp_photos_batch(request):
    try:
        all_photos = upload_temporary_photos_batch(request.POST, request.FILES)
        return JsonResponse({'success': True, 'photos': all_photos}, status=201)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error uploading photos batch: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_key_required
def delete_temp_photo(request, photo_id):
    try:
        try:
            photo = Photo.objects.get(id=photo_id, order=None)
        except Photo.DoesNotExist:
            return JsonResponse({'error': 'Photo not found'}, status=404)

        if photo.processed_file:
            try:
                photo.processed_file.delete(save=False)
            except Exception as e:
                logger.warning(f"Error deleting photo file: {e}")

        if photo.processed_file_no_border:
            try:
                photo.processed_file_no_border.delete(save=False)
            except Exception as e:
                logger.warning(f"Error deleting photo no-border file: {e}")

        photo.delete()

        logger.info(f"Temporary photo {photo_id} deleted")
        return JsonResponse({
            'success': True
        }, status=200)

    except Exception as e:
        logger.error(f"Error deleting temporary photo: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_key_required
def submit_order(request):
    try:
        order, _ = create_order(request.POST, request.FILES)
        return JsonResponse({
            'success': True,
            'order_id': str(order.id)
        }, status=201)
    except ValueError as e:
        logger.warning(f"Validation error in submit_order: {e}")
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error submitting order: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_key_required
def get_orders(request):
    try:
        status_filter = request.GET.get('status')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        queryset = Order.objects.all().order_by('-created_at')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        total = queryset.count()
        orders = queryset[offset:offset + limit]
        
        orders_data = []
        for order in orders:
            processed_photos = order.photos.filter(status='success')
            orders_data.append({
                'order_id': str(order.id),
                'name': order.name,
                'phone': order.phone,
                'username': order.username,
                'ratio': order.ratio,
                'status': order.status,
                'created_at': order.created_at.isoformat(),
                'photos_count': order.photos.count(),
                'processed_count': processed_photos.count()
            })
        
        return JsonResponse({
            'total': total,
            'offset': offset,
            'limit': limit,
            'orders': orders_data
        }, status=200)
        
    except Exception as e:
        logger.error(f"Error getting orders: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_key_required
def get_order_detail(request, order_id):
    try:
        order = Order.objects.get(pk=order_id)
        
        processed_photos = order.photos.filter(status='success')
        failed_photos = order.photos.filter(status='failed')
        
        processed_files = []
        for photo in processed_photos:
            if photo.processed_file and photo.processed_metadata:
                metadata = photo.processed_metadata
                processed_files.append({
                    'fileId': photo.file_id or str(photo.id),
                    'filename': photo.filename,
                    'width': metadata.get('width'),
                    'height': metadata.get('height'),
                    'aspectRatio': metadata.get('aspect_ratio')
                })
        
        order_status = 'success' if processed_photos.exists() and not failed_photos.exists() else 'failed'
        
        return JsonResponse({
            'order_id': str(order.id),
            'name': order.name,
            'phone': order.phone,
            'username': order.username,
            'ratio': order.ratio,
            'status': order_status,
            'created_at': order.created_at.isoformat(),
            'processedFiles': processed_files
        }, status=200)
        
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting order detail: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_key_required
def get_order_files(request, order_id):
    try:
        order = Order.objects.get(pk=order_id)
        
        files_data = {
            'order_id': str(order.id),
            'screenshot': None,
            'processed_photos': []
        }
        
        if order.screenshot:
            files_data['screenshot'] = {
                'url': order.screenshot.url,
                'filename': os.path.basename(order.screenshot.name)
            }
        
        for photo in order.photos.filter(status='success'):
            if photo.processed_file:
                files_data['processed_photos'].append({
                    'fileId': photo.file_id or str(photo.id),
                    'filename': photo.filename,
                    'url': photo.processed_file.url
                })
        
        return JsonResponse(files_data, status=200)
        
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting order files: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)