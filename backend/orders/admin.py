from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html
from django.urls import reverse
from django.http import FileResponse
from django.utils import timezone
import zipfile
import os
import tempfile
from PIL import Image
from .models import Order, Photo, Settings


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    readonly_fields = [
        'id',
        'filename',
        'status_display',
        'processed_file_preview',
        'processed_file_link',
        'processed_file_no_border_link',
        'created_at',
    ]
    fields = [
        'id',
        'filename',
        'status_display',
        'processed_file_preview',
        'processed_file_link',
        'processed_file_no_border_link',
        'created_at',
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = 'Статус'

    def processed_file_link(self, obj):
        if obj.processed_file:
            return format_html('<a href="{}" target="_blank">Открыть</a>', obj.processed_file.url)
        return '-'
    processed_file_link.short_description = 'Обработанный файл'

    def processed_file_no_border_link(self, obj):
        if obj.processed_file_no_border:
            return format_html('<a href="{}" target="_blank">Открыть</a>', obj.processed_file_no_border.url)
        return '-'
    processed_file_no_border_link.short_description = 'Файл без рамок'

    def processed_file_preview(self, obj):
        file_field = obj.thumbnail or obj.processed_file
        if file_field:
            return format_html(
                '<img src="{}" loading="lazy" style="max-width: 100px; max-height: 100px;" />',
                file_field.url
            )
        return '-'
    processed_file_preview.short_description = 'Превью'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'phone', 'username', 'ratio', 'status', 'photos_count', 'created_at']
    list_filter = ['status', 'ratio', 'created_at']
    search_fields = ['name', 'phone', 'username']
    actions = ['delete_selected_with_files']
    readonly_fields = ['id', 'created_at', 'photos_count', 'screenshot_preview', 'action_buttons']
    fields = ['id', 'name', 'phone', 'username', 'ratio', 'status', 'screenshot_preview', 'photos_count', 'created_at', 'action_buttons']
    date_hierarchy = 'created_at'
    inlines = [PhotoInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(status='draft')

    def action_buttons(self, obj):
        """Кнопки действий для заявки"""
        if obj:
            download_url = reverse('admin:orders_order_download', args=[obj.pk])
            delete_url = reverse('admin:orders_order_delete_with_files', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" style="margin-right: 10px;">📥 Скачать ZIP</a>'
                '<a class="button" href="{}" onclick="return confirm(\'Вы уверены, что хотите удалить заявку и все связанные файлы? Это действие нельзя отменить!\');" style="background-color: #ba2121; color: white;">🗑️ Удалить</a>',
                download_url, delete_url
            )
        return '-'
    action_buttons.short_description = 'Действия'

    def screenshot_preview(self, obj):
        """Превью скриншота"""
        if obj.screenshot:
            return format_html('<img src="{}" style="max-width: 300px; max-height: 300px;" />', obj.screenshot.url)
        return '-'
    screenshot_preview.short_description = 'Скриншот'

    def delete_queryset(self, request, queryset):
        """Удаление множественных объектов с файлами"""
        for obj in queryset:
            self._delete_order_files(obj)
        super().delete_queryset(request, queryset)

    def delete_model(self, request, obj):
        """Удаление объекта с файлами"""
        self._delete_order_files(obj)
        super().delete_model(request, obj)

    def _delete_order_files(self, obj):
        """Удаление всех файлов заявки"""
        for photo in obj.photos.all():
            if photo.original_file:
                try:
                    photo.original_file.delete(save=False)
                except Exception as e:
                    logger.warning(f"Error deleting original file for photo {photo.id}: {e}")
            if photo.processed_file:
                try:
                    photo.processed_file.delete(save=False)
                except Exception as e:
                    logger.warning(f"Error deleting processed file for photo {photo.id}: {e}")
            if photo.processed_file_no_border:
                try:
                    photo.processed_file_no_border.delete(save=False)
                except Exception as e:
                    logger.warning(f"Error deleting processed_file_no_border for photo {photo.id}: {e}")
        if obj.screenshot:
            try:
                obj.screenshot.delete(save=False)
            except Exception as e:
                logger.warning(f"Error deleting screenshot for order {obj.id}: {e}")

    def photos_count(self, obj):
        return obj.photos.count()
    photos_count.short_description = 'Фото'

    def delete_selected_with_files(self, request, queryset):
        """
        Массовое удаление выбранных заявок вместе со всеми файлами.
        """
        for obj in queryset:
            self._delete_order_files(obj)
        queryset.delete()
    delete_selected_with_files.short_description = 'Удалить выбранные заявки (с файлами)'

    def get_actions(self, request):
        """
        Убираем стандартное действие "Delete selected ..." и оставляем наше.
        """
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/download/',
                self.admin_site.admin_view(self.download_order_view),
                name='orders_order_download',
            ),
            path(
                '<path:object_id>/delete-with-files/',
                self.admin_site.admin_view(self.delete_order_with_files_view),
                name='orders_order_delete_with_files',
            ),
        ]
        return custom_urls + urls

    def _write_jpg_to_zip(self, zip_file, arcname, image_path, quality=95):
        """
        Конвертирует изображение в JPG и пишет сразу в ZIP, без промежуточных больших буферов в памяти.
        """
        try:
            with zip_file.open(arcname, 'w') as dest:
                img = Image.open(image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(dest, format='JPEG', quality=quality)
            return True
        except Exception:
            return False

    def _get_jpg_filename(self, original_filename):
        """Возвращает имя файла с расширением .jpg, слегка санитизируя имя"""
        name_without_ext = os.path.splitext(original_filename)[0]
        safe = "".join(c for c in name_without_ext if c.isalnum() or c in ('-', '_', ' '))[:80]
        safe = safe or "photo"
        return f'{safe}.jpg'

    def download_order_view(self, request, object_id):
        """Скачивание заявки в виде ZIP архива"""
        try:
            order = Order.objects.get(pk=object_id)
            zip_buffer = tempfile.SpooledTemporaryFile(max_size=200 * 1024 * 1024)
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:

                user_data = f"""Данные заявки
================

ID заявки: {order.id}
Имя: {order.name}
Телефон: {order.phone or 'Не указан'}
Telegram: {order.username}
Формат: {order.ratio}
Статус: {order.get_status_display()}
Дата создания: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}

Количество фотографий: {order.photos.count()}
"""
                zip_file.writestr('order_info.txt', user_data.encode('utf-8'))
                
                if order.screenshot and order.screenshot.name:
                    try:
                        screenshot_path = order.screenshot.path
                        if os.path.exists(screenshot_path):
                            screenshot_name = self._get_jpg_filename(os.path.basename(order.screenshot.name))
                            self._write_jpg_to_zip(zip_file, f'screenshot/{screenshot_name}', screenshot_path)
                    except Exception as e:
                        logger.warning(f"Could not add screenshot to zip for order {order.id}: {e}")
                
                for idx, photo in enumerate(order.photos.all(), start=1):
                    if photo.processed_file and photo.processed_file.name:
                        try:
                            photo_path = photo.processed_file.path
                            if os.path.exists(photo_path):
                                base_name = f"{order.id}_{idx}_{photo.id}_{photo.filename}"
                                photo_name = self._get_jpg_filename(base_name)
                                self._write_jpg_to_zip(zip_file, f'photos/{photo_name}', photo_path)
                        except Exception as e:
                            logger.warning(f"Could not add photo {photo.id} to zip for order {order.id}: {e}")
            
            zip_buffer.seek(0)
            
            filename = f'order_{order.id}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.zip'
            
            return FileResponse(zip_buffer, as_attachment=True, filename=filename, content_type='application/zip')
            
        except Order.DoesNotExist:
            self.message_user(request, 'Заявка не найдена', level='error')
            return redirect('admin:orders_order_changelist')

    def delete_order_with_files_view(self, request, object_id):
        """Удаление заявки со всеми файлами"""
        try:
            order = Order.objects.get(pk=object_id)
            self._delete_order_files(order)
            order.delete()
            self.message_user(request, f'Заявка {order.id} и все связанные файлы успешно удалены.')
            return redirect('admin:orders_order_changelist')
        except Order.DoesNotExist:
            self.message_user(request, 'Заявка не найдена', level='error')
            return redirect('admin:orders_order_changelist')

    class Media:
        css = {
            'all': ('orders/admin.css',)
        }


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    readonly_fields = ['api_key', 'updated_at', 'api_key_actions']
    fields = ['api_key', 'api_key_actions', 'question_link', 'updated_at']

    def has_add_permission(self, request):
        return not Settings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def api_key_actions(self, obj):
        """Кнопка для генерации нового API ключа"""
        if obj:
            url = reverse('admin:orders_settings_regenerate_api_key', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}">Сгенерировать новый API ключ</a>',
                url
            )
        return '-'
    api_key_actions.short_description = 'Действия'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/regenerate-api-key/',
                self.admin_site.admin_view(self.regenerate_api_key_view),
                name='orders_settings_regenerate_api_key',
            ),
        ]
        return custom_urls + urls

    def regenerate_api_key_view(self, request, object_id):
        """Обработчик генерации нового API ключа"""
        obj = Settings.get_settings()
        obj.api_key = Settings.generate_token()
        obj.save()
        self.message_user(request, 'Новый API ключ успешно сгенерирован!')
        return redirect('admin:orders_settings_change', object_id)
