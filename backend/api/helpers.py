import logging
import os
import uuid
from io import BytesIO

from django.conf import settings as django_settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.http import JsonResponse
from PIL import Image, ImageOps

logger = logging.getLogger('orders')


def validate_image_size(uploaded_file, max_size, error_message_prefix):
    """
    Проверяет размер загруженного файла и возвращает ошибку, если он превышает лимит.
    """
    if uploaded_file.size > max_size:
        max_size_mb = max_size // (1024 * 1024)
        file_size_mb = uploaded_file.size // (1024 * 1024)
        error_msg = f'{error_message_prefix} "{uploaded_file.name}" слишком большой ({file_size_mb} МБ). Максимальный размер: {max_size_mb} МБ'
        logger.warning(
            f"File too large: {file_size_mb}MB (max {max_size_mb}MB), name={uploaded_file.name}"
        )
        return JsonResponse({'error': error_msg}, status=400)
    return None


def convert_image_to_jpeg(uploaded_file):
    """
    Конвертирует изображение в формат JPEG.
    """
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=92, optimize=True)
        buffer.seek(0)
        
        width, height = image.size
        
        return buffer, width, height
    except Exception as e:
        logger.warning(f"Unable to convert image to JPEG: {e}", exc_info=True)
        return None, None, None


def generate_safe_filename(original_name, prefix="photo"):
    """
    Генерирует безопасное и уникальное имя файла.
    """
    name = os.path.splitext(original_name)[0] or prefix
    safe_name = "".join(c for c in name if c.isalnum() or c in ('-', '_'))[:50]
    return f"{uuid.uuid4()}_{safe_name}_processed.jpg"


def create_photo_metadata(meta):
    """
    Создает словари с основной и обработанной метаинформацией для фото.
    """
    photo_meta = meta.get('metadata', {})
    width = photo_meta.get('width')
    height = photo_meta.get('height')

    processed_meta = {
        'width': width,
        'height': height,
        'aspect_ratio': round(width / height, 4) if width and height else None
    }
    return photo_meta, processed_meta
