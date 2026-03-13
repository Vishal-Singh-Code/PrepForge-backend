from django.urls import path
from .views import TopicAnalyticsView,PerformanceTrendView,WeakTopicRecommendationView

urlpatterns = [
    path('topic/', TopicAnalyticsView.as_view()),
    path('trend/', PerformanceTrendView.as_view()),
    path('recommendations/', WeakTopicRecommendationView.as_view()),
]