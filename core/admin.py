# core/admin.py
from django.contrib import admin
from django.conf import settings

admin.site.site_header = f"{getattr(settings, 'COMPANY_NAME', 'EZ360PM')} Admin"
admin.site.site_title = getattr(settings, 'COMPANY_NAME', 'EZ360PM')
admin.site.index_title = "Administration"
admin.site.site_url = getattr(settings, 'SITE_URL', '/')
