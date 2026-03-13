from rest_framework import serializers
from .models import Company, Exam, Section, ExamPattern, PatternSectionRule


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = '__all__'


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = '__all__'


class PatternSectionRuleCreateSerializer(serializers.Serializer):
    section_id = serializers.IntegerField()
    order_no = serializers.IntegerField(min_value=1)
    question_count = serializers.IntegerField(min_value=1)
    section_duration_sec = serializers.IntegerField(min_value=1)
    allow_section_switch = serializers.BooleanField(default=True)


class ExamPatternCreateSerializer(serializers.ModelSerializer):
    rules = PatternSectionRuleCreateSerializer(many=True, write_only=True)

    class Meta:
        model = ExamPattern
        fields = [
            "id",
            "exam",
            "version",
            "name",
            "total_duration_sec",
            "is_active",
            "rules",
        ]

    def validate(self, attrs):
        exam = attrs["exam"]
        rules = attrs.get("rules", [])

        if not rules:
            raise serializers.ValidationError("At least one section rule is required.")

        order_values = [r["order_no"] for r in rules]
        if len(order_values) != len(set(order_values)):
            raise serializers.ValidationError("order_no must be unique within the pattern.")

        section_ids = [r["section_id"] for r in rules]
        if len(section_ids) != len(set(section_ids)):
            raise serializers.ValidationError("Each section can appear only once in a pattern.")

        valid_section_ids = set(Section.objects.filter(exam=exam).values_list("id", flat=True))
        invalid = [sid for sid in section_ids if sid not in valid_section_ids]
        if invalid:
            raise serializers.ValidationError(f"Invalid section_id for this exam: {invalid}")

        total_section_duration = sum(r["section_duration_sec"] for r in rules)
        if attrs["total_duration_sec"] < total_section_duration:
            raise serializers.ValidationError(
                "total_duration_sec must be greater than or equal to sum of section_duration_sec."
            )

        return attrs

    def create(self, validated_data):
        rules = validated_data.pop("rules")
        pattern = ExamPattern.objects.create(**validated_data)

        for rule in rules:
            PatternSectionRule.objects.create(
                exam_pattern=pattern,
                section_id=rule["section_id"],
                order_no=rule["order_no"],
                question_count=rule["question_count"],
                section_duration_sec=rule["section_duration_sec"],
                allow_section_switch=rule["allow_section_switch"],
            )

        return pattern
