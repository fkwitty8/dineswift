import os
from pathlib import Path
from datetime import timedelta
import structlog
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

INSTALLED_APPS = [
    'daphne',  # Must be first for ASGI
    
    'apps.core',#must come first efor the django.contrib.admin',
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'corsheaders',
    'channels',
    'django_celery_beat',
    'django_celery_results',
    'django_filters',
    
    # Local apps
    
    'apps.menu_cache',
    'apps.order_processing',
    'apps.sync_manager',
    'apps.otp_service',
    'apps.payment',
    #'apps.billing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.LoggingMiddleware',
    'apps.core.middleware.SecurityHeadersMiddleware',
    'apps.core.middleware.MetricsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database with connection pooling
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('LOCAL_DB_NAME', 'dineswift_local_test'),
        'USER': os.getenv('LOCAL_DB_USER', 'dineswift_user'),
        'PASSWORD': os.environ['LOCAL_DB_PASSWORD'],
        'HOST': os.getenv('LOCAL_DB_HOST', 'localhost'),
        'PORT': os.getenv('LOCAL_DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000'
        },
    }
}

# Supabase Configuration
SUPABASE_CONFIG = {
    'url': os.environ['SUPABASE_URL'],
    'anon_key': os.environ['SUPABASE_ANON_KEY'],
    'service_key': os.environ['SUPABASE_SERVICE_KEY'],
    'jwt_secret': os.environ['SUPABASE_JWT_SECRET'],
}

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.SupabaseAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'apps.core.throttling.MenuRequestThrottle',
        'apps.core.throttling.OrderSubmissionThrottle',
        'apps.core.throttling.SyncOperationThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'menu_requests': '1000/hour',
        'order_submissions': '500/hour',
        'sync_operations': '100/minute',
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 50,
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

# Security Settings
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', 86400))
SESSION_SAVE_EVERY_REQUEST = True

# CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if not DEBUG:
    CORS_ALLOWED_ORIGINS.extend(os.getenv('CORS_ORIGINS', '').split(','))

CORS_ALLOW_CREDENTIALS = True

# Channels (WebSockets)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.getenv('REDIS_URL', 'redis://localhost:6379/0')],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# Caching
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            }
        },
        'KEY_PREFIX': 'dineswift',
        'TIMEOUT': 3600,
    }
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_WORKER_PREFETCH_MULTIPLIER = 4

CELERY_BEAT_SCHEDULE = {
    'sync-pending-orders': {
        'task': 'apps.sync_manager.tasks.sync_pending_orders',
        'schedule': 60.0,
    },
    'sync-menu-cache': {
        'task': 'apps.menu_cache.tasks.sync_all_restaurant_menus',
        'schedule': 300.0,
    },
    'cleanup-old-logs': {
        'task': 'apps.core.tasks.cleanup_old_logs',
        'schedule': 86400.0,
    },
    'health-check': {
        'task': 'apps.core.tasks.perform_health_check',
        'schedule': 120.0,
    },
}

# Field Encryption
FIELD_ENCRYPTION_KEY = os.environ.get('FIELD_ENCRYPTION_KEY')

# Sync Configuration
SYNC_CONFIG = {
    'batch_size': int(os.getenv('SYNC_BATCH_SIZE', 50)),
    'retry_delay': int(os.getenv('SYNC_RETRY_DELAY', 60)),
    'max_retries': int(os.getenv('SYNC_MAX_RETRIES', 5)),
    'conflict_resolution': 'last_write_wins',
}

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR.parent / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.json.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'
        },
        'console': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console' if DEBUG else 'json',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'dineswift.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'errors.log'),
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'json',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'dineswift': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# Sentry Integration
if os.getenv('SENTRY_DSN'):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    
    sentry_sdk.init(
        dsn=os.getenv('SENTRY_DSN'),
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ],
        environment=ENVIRONMENT,
        traces_sample_rate=0.1 if ENVIRONMENT == 'production' else 1.0,
        send_default_pii=False,
    )

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR.parent / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'


CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...
    
    'monitor-payments': {
        'task': 'apps.billing.tasks.monitor_pending_payments',
        'schedule': 120.0,  # Every 2 minutes
    },
    'expire-old-payments': {
        'task': 'apps.billing.tasks.expire_old_payments',
        'schedule': 600.0,  # Every 10 minutes
    },
}
"""

## 📝 **Summary: Two Payment Processing Paths**

### **Path 1: Mobile Money (MTN MoMo)**
```
Django → Supabase Edge Function → MTN MoMo API → Customer Phone
  ↓                                                     ↓
Local DB ← Sync Status ← Supabase DB ← Webhook ← Customer Confirms
```

### **Path 2: Cryptocurrency**
```
Django → Blockchain Network → Customer Wallet
  ↓              ↓
Monitors TX → Counts Confirmations → Marks Complete

"""
# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

AUTH_USER_MODEL = 'core.User'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
