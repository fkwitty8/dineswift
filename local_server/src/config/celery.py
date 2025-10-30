import os
from celery import Celery
from celery.signals import task_failure, task_success
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('dineswift')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    from apps.core.models import ActivityLog
    ActivityLog.objects.create(
        level='ERROR',
        module='CELERY',
        action='TASK_FAILED',
        details={
            'task_id': task_id,
            'task_name': sender.name,
            'error': str(exception),
        }
    )

@task_success.connect
def handle_task_success(sender=None, result=None, **kwargs):
    if hasattr(sender, 'request') and sender.request.id:
        from apps.core.models import ActivityLog
        ActivityLog.objects.create(
            level='INFO',
            module='CELERY',
            action='TASK_COMPLETED',
            details={
                'task_id': sender.request.id,
                'task_name': sender.name,
            }
        )