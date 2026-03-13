from django.contrib import admin
from .models import Topic, Question, Option
# Register your models here.
admin.site.register(Topic)
admin.site.register(Question)
admin.site.register(Option)