from rest_framework import serializers


class StartTestSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField()


from questions.serializers import StudentQuestionSerializer
from .models import MockTest, TestQuestion


class MockTestResponseSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = MockTest
        fields = ['id', 'exam', 'created_at', 'questions']

    def get_questions(self, obj):
        test_questions = TestQuestion.objects.filter(mock_test=obj)
        questions = [tq.question for tq in test_questions]
        return StudentQuestionSerializer(questions, many=True).data

class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_option_id = serializers.IntegerField()


class SubmitTestSerializer(serializers.Serializer):
    mock_test_id = serializers.IntegerField()
    answers = SubmitAnswerSerializer(many=True)


from .models import MockTest, AttemptAnswer


class MockTestHistorySerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)

    class Meta:
        model = MockTest
        fields = ['id', 'exam_title', 'created_at']


class DetailedResultSerializer(serializers.Serializer):
    mock_test_id = serializers.IntegerField()
    exam = serializers.CharField()
    score = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    incorrect_answers = serializers.IntegerField()
    unattempted = serializers.IntegerField()
    questions = serializers.ListField()


class MockSessionStartSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField(required=False)
    exam_pattern_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get('exam_id') and not attrs.get('exam_pattern_id'):
            raise serializers.ValidationError(
                "Either exam_id or exam_pattern_id is required."
            )
        return attrs


class MockSessionAnswerSerializer(serializers.Serializer):
    test_session_id = serializers.IntegerField()
    question_id = serializers.IntegerField()
    selected_option_id = serializers.IntegerField()
    time_spent_sec = serializers.IntegerField(required=False, min_value=0, default=0)
    marked_for_review = serializers.BooleanField(required=False, default=False)


class MockSessionSubmitSerializer(serializers.Serializer):
    test_session_id = serializers.IntegerField()


class PracticeSectionStartSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["single_exam", "cross_exam"], default="single_exam")
    exam_id = serializers.IntegerField(required=False)
    section_id = serializers.IntegerField(required=False)
    section_name = serializers.CharField(required=False, allow_blank=False)
    question_count = serializers.IntegerField(required=False, min_value=1)
    duration_sec = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        mode = attrs.get("mode", "single_exam")
        if mode == "single_exam":
            if not attrs.get("section_id"):
                raise serializers.ValidationError("section_id is required for single_exam mode")
        else:
            if not attrs.get("section_name"):
                raise serializers.ValidationError("section_name is required for cross_exam mode")
        return attrs


class PracticeSectionSubmitSerializer(serializers.Serializer):
    test_session_id = serializers.IntegerField()


class PracticeTopicStartSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["single_exam", "cross_exam"], default="single_exam")
    exam_id = serializers.IntegerField(required=False)
    topic_id = serializers.IntegerField(required=False)
    topic_name = serializers.CharField(required=False, allow_blank=False)
    question_count = serializers.IntegerField(required=False, min_value=1)
    duration_sec = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        mode = attrs.get("mode", "single_exam")
        if mode == "single_exam":
            if not attrs.get("topic_id"):
                raise serializers.ValidationError("topic_id is required for single_exam mode")
        else:
            if not attrs.get("topic_name"):
                raise serializers.ValidationError("topic_name is required for cross_exam mode")
        return attrs


class WeakPracticeSessionStartSerializer(serializers.Serializer):
    questions_per_topic = serializers.IntegerField(required=False, min_value=1, default=5)


class MockSessionSectionCurrentSerializer(serializers.Serializer):
    test_session_id = serializers.IntegerField()


class MockSessionSectionNextSerializer(serializers.Serializer):
    test_session_id = serializers.IntegerField()


class MockSessionPaletteSerializer(serializers.Serializer):
    test_session_id = serializers.IntegerField()
