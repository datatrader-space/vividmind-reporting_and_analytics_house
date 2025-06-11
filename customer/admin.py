from django.contrib import admin
from django_admin_relation_links import AdminChangeLinksMixin

from .models import Customer


class CustomerAdmin(AdminChangeLinksMixin,
                    admin.ModelAdmin):
    list_display = ('user_id',
                    'user_link',
                    'email_address',
                
                    )
    change_links = ('user',)

    def user_id(self, obj):
        return obj.user.id


admin.site.register(Customer, CustomerAdmin)
