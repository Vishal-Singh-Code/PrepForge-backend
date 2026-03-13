from rest_framework import serializers
from .models import Question, Option, Topic


# =========================
# Admin - Creation Serializer
# =========================

class AdminOptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ['id', 'text', 'is_correct']


class AdminQuestionCreateSerializer(serializers.ModelSerializer):
    options = AdminOptionCreateSerializer(many=True)

    class Meta:
        model = Question
        fields = '__all__'

    def validate(self, data):
        options = data.get('options', [])
        correct_count = sum(1 for option in options if option.get('is_correct'))

        if correct_count == 0:
            raise serializers.ValidationError(
                "At least one option must be marked as correct."
            )

        if correct_count > 1:
            raise serializers.ValidationError(
                "Only one option can be marked as correct."
            )

        return data

    def create(self, validated_data):
        options_data = validated_data.pop('options')
        question = Question.objects.create(**validated_data)

        for option_data in options_data:
            Option.objects.create(question=question, **option_data)

        return question


# =========================
# Admin - Read Serializer
# =========================

class AdminOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ['id', 'text', 'is_correct']


class AdminQuestionSerializer(serializers.ModelSerializer):
    options = AdminOptionSerializer(many=True)

    class Meta:
        model = Question
        fields = '__all__'


# =========================
# Student Serializer
# =========================

class StudentOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ['id', 'text']  # hide is_correct


class StudentQuestionSerializer(serializers.ModelSerializer):
    options = StudentOptionSerializer(many=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True)

    class Meta:
        model = Question
        fields = [
            "id",
            "section",
            "section_name",
            "company",
            "topic",
            "topic_name",
            "text",
            "marks",
            "options",
        ]


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ['id', 'name']
