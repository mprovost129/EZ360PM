from django.contrib import admin
from .models import Company, Client, Project, Invoice, InvoiceItem, Payment, Expense, TimeEntry, CompanyMember, CompanyInvite

admin.site.register(Company)
admin.site.register(Client)
admin.site.register(Project)
admin.site.register(Invoice)
admin.site.register(InvoiceItem)
admin.site.register(Payment)
admin.site.register(Expense)
admin.site.register(TimeEntry)


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ("company", "user", "role", "joined_at")
    list_filter = ("role", "company")
    search_fields = ("user__email", "company__name")

@admin.register(CompanyInvite)
class CompanyInviteAdmin(admin.ModelAdmin):
    list_display = ("company", "email", "role", "status", "sent_at", "accepted_at")
    list_filter = ("status", "role", "company")
    search_fields = ("email", "company__name")