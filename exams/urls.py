from django.urls import path
from .views import (
    CompanyCreateView,
    CompanyListView,
    ExamCreateView,
    ExamListView,
    ExamPatternBulkUploadView,
    ExamPatternCreateView,
    SectionListView,
    SectionCreateView,
)

urlpatterns = [
    path('company/create/', CompanyCreateView.as_view()),
    path('company/list/', CompanyListView.as_view()),
    path('exam/create/', ExamCreateView.as_view()),
    path('section/create/', SectionCreateView.as_view()),
    path('section/list/', SectionListView.as_view()),
    path('exam/list/', ExamListView.as_view()),
    path('pattern/create/', ExamPatternCreateView.as_view()),
    path('pattern/bulk-upload/', ExamPatternBulkUploadView.as_view()),

]
