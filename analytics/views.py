from collections import defaultdict

from django.db.models import Q, Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsStudentRole
from tests.models import SessionQuestion
from tests.models import AttemptAnswer, TestSession


def _topic_stats_for_user(user):
    rows = (
        AttemptAnswer.objects
        .select_related("question__topic")
        .filter(
            Q(test_session__student=user, test_session__status__in=["submitted", "expired"]) |
            Q(mock_test__student=user, mock_test__is_completed=True)
        )
    )

    stats = defaultdict(lambda: {"total_attempted": 0, "total_correct": 0})
    for answer in rows:
        topic = answer.question.topic
        if not topic:
            continue
        bucket = stats[topic.name]
        bucket["total_attempted"] += 1
        if answer.is_correct:
            bucket["total_correct"] += 1
    return stats


class TopicAnalyticsView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        stats = _topic_stats_for_user(request.user)
        result = []

        for topic_name, values in stats.items():
            attempted = values["total_attempted"]
            correct = values["total_correct"]
            accuracy = (correct / attempted) * 100 if attempted > 0 else 0
            result.append(
                {
                    "topic": topic_name,
                    "total_attempted": attempted,
                    "total_correct": correct,
                    "accuracy_percentage": round(accuracy, 2),
                }
            )

        result.sort(key=lambda row: row["topic"])
        return Response(result)


class PerformanceTrendView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        sessions = (
            TestSession.objects
            .filter(student=request.user, status__in=["submitted", "expired"])
            .select_related("exam")
            .order_by("submitted_at", "started_at")
        )

        max_score_by_session = {
            row["test_session_id"]: row["max_score"] or 0
            for row in (
                SessionQuestion.objects
                .filter(test_session__in=sessions)
                .values("test_session_id")
                .annotate(max_score=Sum("marks"))
            )
        }

        result = []
        for session in sessions:
            max_score = max_score_by_session.get(session.id, 0)
            score_percentage = round((session.total_score / max_score) * 100, 2) if max_score > 0 else 0
            result.append(
                {
                    # keep key name for frontend compatibility
                    "mock_test_id": session.id,
                    "exam": session.exam.title if session.exam else "Practice Test",
                    "score": score_percentage,
                    "raw_score": session.total_score,
                    "max_score": max_score,
                    "score_percentage": score_percentage,
                    "date": (session.submitted_at or session.started_at).date(),
                }
            )

        return Response(result)


class WeakTopicRecommendationView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        stats = _topic_stats_for_user(request.user)
        recommendations = []

        for topic_name, values in stats.items():
            attempted = values["total_attempted"]
            correct = values["total_correct"]
            if attempted == 0:
                continue
            accuracy = (correct / attempted) * 100

            if accuracy < 60:
                level = "Focus heavily on this topic"
            elif accuracy < 80:
                level = "Needs more practice"
            else:
                continue

            recommendations.append(
                {
                    "topic": topic_name,
                    "accuracy": round(accuracy, 2),
                    "recommendation": level,
                }
            )

        recommendations.sort(key=lambda row: row["accuracy"])
        return Response(recommendations)
