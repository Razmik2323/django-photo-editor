import logging
from celery import shared_task
from django.core import management
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('orders')


@shared_task
def cleanup_sessions():
    logger.info("Running Django clearsessions...")
    management.call_command('clearsessions')
    logger.info("Django sessions cleanup completed.")


@shared_task
def cleanup_temp_photos():
    from orders.models import Photo
    
    cutoff_time = timezone.now() - timedelta(hours=1)
    temp_photos = Photo.objects.filter(
        order=None,
        created_at__lt=cutoff_time
    )
    
    count = temp_photos.count()
    for photo in temp_photos:
        if photo.original_file:
            try:
                photo.original_file.delete(save=False)
            except Exception as e:
                logger.warning(f"Error deleting temp original_file: {e}")
        if photo.processed_file:
            try:
                photo.processed_file.delete(save=False)
            except Exception as e:
                logger.warning(f"Error deleting temp photo file: {e}")
        if photo.processed_file_no_border:
            try:
                photo.processed_file_no_border.delete(save=False)
            except Exception as e:
                logger.warning(f"Error deleting temp no-border photo file: {e}")
        photo.delete()
    
    if count > 0:
        logger.info(f"Cleaned up {count} temporary photos")

