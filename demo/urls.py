from django.urls import re_path

from demo import views

urlpatterns = [
    re_path(r"^receiver/(?P<mode>ok|fail|flaky|slow)/$", views.receiver, name="demo-receiver"),
]
