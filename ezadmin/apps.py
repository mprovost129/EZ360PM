from django.apps import AppConfig


class EzAdminConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ezadmin"
    verbose_name = "EZ360PM Admin"

    def ready(self):
        # Clone registrations from default Django admin into our two custom sites.
        # This runs after app loading/autodiscover, so all `admin.py` modules
        # should already be imported and registered against `admin.site`.
        from .sites import register_from_default_admin

        register_from_default_admin()
