import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from PIL import Image

from .models import Order, Photo

logger = logging.getLogger('orders')


@receiver(post_delete, sender=Photo)
def delete_photo_files(sender, instance, **kwargs):
    """Удаление файлов при удалении Photo (включая каскадное удаление)"""
    if instance.original_file:
        try:
            file_path = instance.original_file.path if hasattr(instance.original_file, 'path') else instance.original_file.name
            instance.original_file.delete(save=False)
            logger.info(f"Deleted original_file from disk: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete original_file: {str(e)}")
    
    if instance.processed_file:
        try:
            file_path = instance.processed_file.path if hasattr(instance.processed_file, 'path') else instance.processed_file.name
            instance.processed_file.delete(save=False)
            logger.info(f"Deleted processed_file from disk: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete processed_file: {str(e)}")

    if instance.processed_file_no_border:
        try:
            file_path = (
                instance.processed_file_no_border.path
                if hasattr(instance.processed_file_no_border, 'path')
                else instance.processed_file_no_border.name
            )
            instance.processed_file_no_border.delete(save=False)
            logger.info(f"Deleted processed_file_no_border from disk: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete processed_file_no_border: {str(e)}")

    if instance.thumbnail:
        try:
            file_path = (
                instance.thumbnail.path
                if hasattr(instance.thumbnail, 'path')
                else instance.thumbnail.name
            )
            instance.thumbnail.delete(save=False)
            logger.info(f"Deleted thumbnail from disk: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete thumbnail: {str(e)}")


@receiver(post_delete, sender=Order)
def delete_order_screenshot(sender, instance, **kwargs):
    """Удаление скриншота при удалении Order"""
    if instance.screenshot:
        try:
            file_path = instance.screenshot.path if hasattr(instance.screenshot, 'path') else instance.screenshot.name
            instance.screenshot.delete(save=False)
            logger.info(f"Deleted screenshot from disk: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete screenshot: {str(e)}")


@receiver(post_save, sender=Photo)
def generate_photo_thumbnail(sender, instance, created, **kwargs):
    """
    Генерация thumbnail 200x200 из processed_file (если он есть)
    Выполняется без Celery, в том же запросе.
    """
    # Если нет обработанного файла — нечего генерировать
    if not instance.processed_file:
        return

    # Если thumbnail уже есть и файл существует, повторно не создаём
    try:
        if instance.thumbnail and instance.thumbnail.storage.exists(instance.thumbnail.name):
            return
    except Exception:
        # Если проверка наличия не удалась, попробуем сгенерировать заново
        pass

    try:
        processed_path = (
            instance.processed_file.path
            if hasattr(instance.processed_file, 'path')
            else None
        )
        if not processed_path or not os.path.exists(processed_path):
            return

        with Image.open(processed_path) as img:
            img.convert('RGB')
            img.thumbnail((200, 200), Image.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)

            thumb_name = f"{instance.id}_thumb.jpg"
            instance.thumbnail.save(thumb_name, ContentFile(buffer.read()), save=False)

        # Сохраняем только поле thumbnail, чтобы не трогать другие
        Photo.objects.filter(pk=instance.pk).update(thumbnail=instance.thumbnail.name)
        logger.info(f"Thumbnail generated for photo {instance.id}: {instance.thumbnail.name}")
    except Exception as e:
        logger.warning(f"Failed to generate thumbnail for photo {instance.id}: {e}")

