from django.contrib import admin
from .models import Company, Exam, Section, ExamPattern, PatternSectionRule

# Register your models here.
admin.site.register(Company)
admin.site.register(Exam)
admin.site.register(Section)
admin.site.register(ExamPattern)
admin.site.register(PatternSectionRule)
