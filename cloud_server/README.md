# DineSwift Cloud Server

Django REST API backend for the DineSwift restaurant management system.

## Project Structure

```
cloud_server/
├── cloud_api/                 # Main Django app
│   ├── migrations/           # Database migrations
│   ├── models/              # Data models
│   ├── views/               # API views
│   ├── serializers/         # DRF serializers
│   ├── utils/               # Utility functions
│   ├── tests/               # Test files
│   ├── admin.py            # Django admin config
│   ├── apps.py             # App configuration
│   └── urls.py             # URL routing
├── cloud_server/            # Django project settings
├── scripts/                 # Utility scripts
├── docs/                   # Documentation
├── config/                 # Configuration files
├── manage.py              # Django management script
└── requirements.txt       # Python dependencies
```

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run migrations: `python manage.py migrate`
3. Create superuser: `python manage.py createsuperuser`
4. Start server: `python manage.py runserver`

## API Documentation

See `docs/API_DOCUMENTATION.md` for detailed API documentation.