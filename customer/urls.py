from django.conf.urls import url
from django.contrib.auth import views as auth_views

from .views import customer_login, customer_signup

urlpatterns = [
    url('signup', customer_signup, name='signup'),
    url(r'^login/$', customer_login, name='login'),
    url(r'^logout/$',
        auth_views.logout,
        {
            'template_name': 'logged_out.html',
            'next_page': 'home'
        },
        name='logout'
        )
]
