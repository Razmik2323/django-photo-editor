import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Синхронизация расписания beat из Django settings"""
    import django
    if not django.apps.apps.ready:
        django.setup()
    from django.conf import settings
    if hasattr(settings, 'CELERY_BEAT_SCHEDULE'):
        sender.conf.beat_schedule.update(settings.CELERY_BEAT_SCHEDULE)
