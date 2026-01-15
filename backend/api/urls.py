from django.urls import path
from .views import (
    create_lead,
    get_config,
    health_check,
    upload_temp_photo,
    upload_temp_photos_batch,
    delete_temp_photo,
    submit_order,
    convert_photo,
    get_orders,
    get_order_detail,
    get_order_files,
)

app_name = 'api'

urlpatterns = [
    path('health', health_check, name='health_check'),
    path('config', get_config, name='get_config'),
    path('lead', create_lead, name='create_lead'),
    path('convert-photo', convert_photo, name='convert_photo'),
    path('upload-photo', upload_temp_photo, name='upload_temp_photo'),
    path('upload-photos-batch', upload_temp_photos_batch, name='upload_temp_photos_batch'),
    path('photo/<uuid:photo_id>', delete_temp_photo, name='delete_temp_photo'),
    path('submit', submit_order, name='submit_order'),
    path('orders', get_orders, name='get_orders'),
    path('orders/<uuid:order_id>', get_order_detail, name='get_order_detail'),
    path('orders/<uuid:order_id>/files', get_order_files, name='get_order_files'),
]