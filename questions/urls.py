from django.urls import path
from .views import QuestionCreateView, QuestionListView, QuestionBulkUploadView, TopicListView

urlpatterns = [
    path('create/', QuestionCreateView.as_view()),
    path('list/', QuestionListView.as_view()),
    path('topic/list/', TopicListView.as_view()),
    path('bulk-upload/', QuestionBulkUploadView.as_view()),

]
