from django.apps import AppConfig


class ApiMikrotikConfig(AppConfig):
    name = 'api_mikrotik'

    def ready(self):
        from . import signals  # noqa: F401
