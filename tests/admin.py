from django.contrib import admin
from .models import (
    MockTest,
    TestQuestion,
    AttemptAnswer,
    TestSession,
    SessionSectionState,
    SessionQuestion,
)
# Register your models here.

admin.site.register(MockTest)
admin.site.register(TestQuestion)
admin.site.register(AttemptAnswer)
admin.site.register(TestSession)
admin.site.register(SessionSectionState)
admin.site.register(SessionQuestion)
