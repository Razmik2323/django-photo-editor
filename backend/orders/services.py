import json
import logging
import os
import uuid
from io import BytesIO

from django.conf import settings as django_settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

from .models import Order, Photo
from api.helpers import validate_image_size, generate_safe_filename, create_photo_metadata

logger = logging.getLogger('orders')


def convert_screenshot_to_jpeg(screenshot_file):
    try:
        image = Image.open(screenshot_file)
        image = ImageOps.exif_transpose(image)
        
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        
        buffer = BytesIO()
        original_name = screenshot_file.name
        base_name = os.path.splitext(original_name)[0] if original_name else 'screenshot'
        jpeg_name = f"{base_name}.jpg"
        
        image.save(buffer, format="JPEG", quality=92, optimize=True)
        buffer.seek(0)
        
        converted_file = InMemoryUploadedFile(
            buffer,
            None,
            jpeg_name,
            'image/jpeg',
            buffer.tell(),
            None
        )
        
        logger.info(
            f"convert_screenshot: converted '{original_name}' ({screenshot_file.size} bytes) "
            f"to JPEG {image.size[0]}x{image.size[1]}"
        )
        
        return converted_file
    except Exception as e:
        logger.warning(f"Unable to convert screenshot to JPEG: {e}", exc_info=True)
        return screenshot_file




def create_order(data, files):
    """
    Создает заказ и связанные с ним фотографии из данных запроса.
    Может работать как с прямой загрузкой файлов, так и с временными фото через session_token.
    """
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip() or None
    username = data.get('username', '').strip()
    ratio = data.get('ratio', '').strip()
    screenshot = files.get('screenshot')
    session_token = data.get('session_token')

    if not all([name, username, ratio, screenshot]):
        raise ValueError('Missing required fields: name, username, ratio, screenshot')

    if not (files.getlist('photos') or session_token):
        raise ValueError('Either photos or session_token must be provided')

    size_error = validate_image_size(screenshot, django_settings.MAX_SCREENSHOT_SIZE, 'Скриншот')
    if size_error:
        raise ValueError(size_error.content.decode())

    screenshot_name_lower = (screenshot.name or '').lower()
    is_heic = screenshot_name_lower.endswith(('.heic', '.heif')) or 'heic' in (screenshot.content_type or '').lower()
    if is_heic:
        screenshot = convert_screenshot_to_jpeg(screenshot)

    try:
        photos_meta = json.loads(data.get('photos_meta', '[]'))
    except json.JSONDecodeError:
        raise ValueError('Invalid photos_meta JSON')

    with transaction.atomic():
        order = Order.objects.create(
            name=name, phone=phone, username=username, ratio=ratio,
            screenshot=screenshot, status='pending'
        )
        logger.info(f"Order {order.id} created for {name}")

        created_photos = []
        if session_token:
            # Логика для временных фото
            valid_file_ids = {meta.get('fileId') for meta in photos_meta if meta.get('fileId')}
            if valid_file_ids:
                photos_to_update = Photo.objects.filter(session_token=session_token, order=None, file_id__in=valid_file_ids)
                photos_meta_dict = {meta.get('fileId'): meta for meta in photos_meta}
                for photo in photos_to_update:
                    meta = photos_meta_dict.get(photo.file_id, {})
                    photo.order = order
                    photo.status = meta.get('status', photo.status)
                    photo.save()
                    created_photos.append({'id': str(photo.id), 'filename': photo.filename, 'status': photo.status})
                
                # Удаляем неиспользованные временные фото для этой сессии
                Photo.objects.filter(session_token=session_token, order=None).delete()

        else:
            # Логика для прямой загрузки
            photo_files = files.getlist('photos')
            if len(photo_files) != len(photos_meta):
                raise ValueError(f'Mismatch: {len(photo_files)} files but {len(photos_meta)} metadata entries')

            photos_to_create = []
            for photo_file, meta in zip(photo_files, photos_meta):
                if size_error := validate_image_size(photo_file, django_settings.MAX_PHOTO_SIZE, 'Фото'):
                    raise ValueError(size_error.content.decode())

                original_filename = meta.get('filename', photo_file.name)
                photo_file.name = generate_safe_filename(original_filename)
                photo_meta, processed_meta = create_photo_metadata(meta)
                photos_to_create.append(Photo(
                    order=order, processed_file=photo_file, filename=original_filename,
                    file_id=meta.get('fileId', ''), status='success', metadata=photo_meta,
                    processed_metadata=processed_meta, processed_at=timezone.now()
                ))

            if photos_to_create:
                created_batch = Photo.objects.bulk_create(photos_to_create, batch_size=100)
                created_photos = [{'id': str(p.id), 'filename': p.filename, 'status': p.status} for p in created_batch]

    logger.info(f"Order {order.id} processed, {len(created_photos)} photos saved")
    return order, created_photos


def upload_temporary_photo(data, files):
    """
    Загружает временное фото.
    """
    photo_file = files.get('photo')
    if not photo_file:
        raise ValueError('No photo file provided')

    if size_error := validate_image_size(photo_file, django_settings.MAX_PHOTO_SIZE, 'Фото'):
        raise ValueError(size_error.content.decode())

    session_token = data.get('session_token')
    if not session_token:
        raise ValueError('Session token required')

    try:
        meta = json.loads(data.get('meta', '{}'))
    except json.JSONDecodeError:
        meta = {}

    file_id = meta.get('fileId', '')
    if file_id:
        if existing_photo := Photo.objects.filter(session_token=session_token, file_id=file_id).first():
            logger.info(f"Photo with file_id {file_id} already exists.")
            return existing_photo

    original_filename = meta.get('filename', photo_file.name)
    photo_file.name = generate_safe_filename(original_filename)
    photo_meta, processed_meta = create_photo_metadata(meta)

    photo_file_no_border = files.get('photo_noborder')
    if photo_file_no_border:
        photo_file_no_border.name = generate_safe_filename(original_filename, prefix="photo_nb")

    photo = Photo.objects.create(
        session_token=session_token,
        processed_file=photo_file,
        processed_file_no_border=photo_file_no_border,
        filename=original_filename,
        file_id=file_id,
        status=meta.get('status', 'success'),
        crop_parameters=meta.get('parameters'),
        metadata=photo_meta,
        processed_metadata=processed_meta,
        processed_at=timezone.now()
    )
    logger.info(f"Temporary photo {photo.id} uploaded with session {session_token}")
    return photo


def upload_temporary_photos_batch(data, files):
    """
    Загружает пачку временных фото.
    """
    session_token = data.get('session_token')
    if not session_token:
        raise ValueError('Session token required')

    try:
        photos_meta = json.loads(data.get('photos_meta', '[]'))
    except json.JSONDecodeError:
        raise ValueError('Invalid photos_meta JSON')

    photo_files = files.getlist('photos')
    if len(photo_files) != len(photos_meta):
        raise ValueError('Mismatch between files and metadata')

    photos_to_create, existing_photos_data = [], []
    file_id_to_meta = {m['fileId']: m for m in photos_meta if 'fileId' in m}

    if file_id_to_meta:
        existing_photos = Photo.objects.filter(session_token=session_token, file_id__in=file_id_to_meta.keys())
        for p in existing_photos:
            existing_photos_data.append({'file_id': p.file_id, 'photo_id': str(p.id)})
            file_id_to_meta.pop(p.file_id, None)

    photo_files_map = {meta.get('filename'): file for meta, file in zip(photos_meta, photo_files)}
    photo_files_no_border_map = {meta.get('filename'): file for meta, file in zip(photos_meta, files.getlist('photos_noborder'))}

    for file_id, meta in file_id_to_meta.items():
        original_filename = meta.get('filename')
        photo_file = photo_files_map.get(original_filename)
        if not photo_file:
            continue

        if size_error := validate_image_size(photo_file, django_settings.MAX_PHOTO_SIZE, 'Фото'):
            logger.warning(f"Skipping large file in batch: {original_filename}")
            continue

        photo_file.name = generate_safe_filename(original_filename)
        photo_meta, processed_meta = create_photo_metadata(meta)

        photo_file_no_border = photo_files_no_border_map.get(original_filename)
        if photo_file_no_border:
            photo_file_no_border.name = generate_safe_filename(original_filename, prefix="photo_nb")

        photos_to_create.append(Photo(
            session_token=session_token,
            processed_file=photo_file,
            processed_file_no_border=photo_file_no_border,
            filename=original_filename,
            file_id=file_id,
            status=meta.get('status', 'success'),
            crop_parameters=meta.get('parameters'),
            metadata=photo_meta,
            processed_metadata=processed_meta,
            processed_at=timezone.now()
        ))

    created_photos_data = []
    if photos_to_create:
        created_batch = Photo.objects.bulk_create(photos_to_create, batch_size=100)
        created_photos_data = [{'file_id': p.file_id, 'photo_id': str(p.id)} for p in created_batch]

    all_photos = existing_photos_data + created_photos_data
    logger.info(f"Batch uploaded {len(all_photos)} photos for session {session_token}")
    return all_photos