from django.db import models
import uuid
import secrets


def generate_secure_token():
    return secrets.token_urlsafe(32)


class Order(models.Model):
    """Модель заявки от пользователя"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, blank=True, verbose_name='Имя')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Телефон')
    username = models.CharField(max_length=100, blank=True, verbose_name='Telegram username')
    screenshot = models.FileField(upload_to='screenshots/', blank=True, null=True, verbose_name='Скриншот')
    ratio = models.CharField(max_length=50, blank=True, verbose_name='Выбранный формат')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Черновик'),
            ('pending', 'Ожидает обработки'),
            ('processing', 'Обрабатывается'),
            ('completed', 'Завершено'),
            ('failed', 'Ошибка'),
        ],
        default='draft',
        verbose_name='Статус'
    )
    last_activity = models.DateTimeField(auto_now=True, verbose_name='Последняя активность')

    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='order_created_at_idx'),
            models.Index(fields=['status'], name='order_status_idx'),
        ]

    def __str__(self):
        return f'Заявка {self.id} от {self.name}'


class Photo(models.Model):
    """Модель фотографии в заявке"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='photos', null=True, blank=True, verbose_name='Заявка')
    session_token = models.CharField(max_length=100, blank=True, null=True, verbose_name='Токен сессии')
    original_file = models.FileField(
        upload_to='photos/original/',
        null=True,
        blank=True,
        verbose_name='Оригинальный файл (временный)'
    )
    processed_file = models.FileField(
        upload_to='photos/processed/',
        null=True,
        blank=True,
        verbose_name='Обработанный файл (с рамками)'
    )
    processed_file_no_border = models.FileField(
        upload_to='photos/processed_no_border/',
        null=True,
        blank=True,
        verbose_name='Обработанный файл (без рамок)'
    )
    thumbnail = models.FileField(
        upload_to='photos/thumbnails/',
        null=True,
        blank=True,
        verbose_name='Превью (thumbnail)'
    )
    filename = models.CharField(max_length=255, verbose_name='Имя файла')
    file_id = models.CharField(max_length=100, verbose_name='ID файла')
    status = models.CharField(
        max_length=20,
        choices=[
            ('valid', 'Валидно'),
            ('needToCrop', 'Требует обрезки'),
            ('operator', 'На усмотрение оператора'),
            ('processing', 'Обрабатывается'),
            ('success', 'Успешно'),
            ('failed', 'Ошибка'),
        ],
        default='valid',
        verbose_name='Статус'
    )
    crop_parameters = models.JSONField(null=True, blank=True, verbose_name='Параметры обрезки')
    metadata = models.JSONField(verbose_name='Метаданные')
    processed_metadata = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Метаданные обработанного файла'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата обработки')

    class Meta:
        verbose_name = 'Фотография'
        verbose_name_plural = 'Фотографии'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['order', 'status'], name='photo_order_status_idx'),
            models.Index(fields=['created_at'], name='photo_created_at_idx'),
            models.Index(fields=['status'], name='photo_status_idx'),
        ]

    def __str__(self):
        return f'{self.filename} ({self.order})'


class Settings(models.Model):
    """Настройки системы (Singleton)"""
    api_key = models.CharField(
        max_length=255,
        verbose_name='API Key',
        help_text='API ключ для защиты эндпоинтов',
        default=generate_secure_token
    )
    question_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Ссылка для кнопки "Задать вопрос"',
        help_text='Полный URL, на который будет вести кнопка "Задать вопрос" на финальном шаге (например, ссылка на чат или форму).'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        verbose_name = 'Настройки'
        verbose_name_plural = 'Настройки'

    def __str__(self):
        return 'Настройки системы'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def generate_token(cls):
        """Сгенерировать новый безопасный токен"""
        return generate_secure_token()

    @classmethod
    def get_settings(cls):
        """Получить настройки (создать если не существует)"""
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'api_key': cls.generate_token()
            }
        )
        return obj
