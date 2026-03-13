from rest_framework import generics
from .models import Question, Topic
from common.permissions import IsAdminRole
from .serializers import (
    AdminQuestionCreateSerializer,
    AdminQuestionSerializer,
    StudentQuestionSerializer,
    TopicSerializer,
)

class QuestionCreateView(generics.CreateAPIView):
    queryset = Question.objects.all()
    serializer_class = AdminQuestionCreateSerializer
    permission_classes = [IsAdminRole]


from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .models import Question
from .serializers import AdminQuestionSerializer, StudentQuestionSerializer
from .filters import QuestionFilter


class QuestionListView(generics.ListAPIView):
    queryset = Question.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = QuestionFilter

    def get_serializer_class(self):
        if self.request.user.role == 'admin':
            return AdminQuestionSerializer
        return StudentQuestionSerializer


class TopicListView(generics.ListAPIView):
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Topic.objects.filter(question__isnull=False)
        section_id = self.request.query_params.get("section_id")
        section_name = self.request.query_params.get("section_name")
        exam_id = self.request.query_params.get("exam_id")
        if section_id:
            queryset = queryset.filter(question__section_id=section_id)
        if section_name:
            queryset = queryset.filter(question__section__name__iexact=section_name.strip())
        if exam_id:
            queryset = queryset.filter(question__section__exam_id=exam_id)
        return queryset.distinct()


import csv
from io import TextIOWrapper
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from exams.models import Company, Exam, Section
from questions.models import Question, Option, Topic
from common.permissions import IsAdminRole


class QuestionBulkUploadView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):

        file = request.FILES.get("file")

        if not file:
            return Response(
                {"error": "No file uploaded"},
                status=status.HTTP_400_BAD_REQUEST
            )

        decoded_file = TextIOWrapper(file.file, encoding='utf-8')
        reader = csv.DictReader(decoded_file)

        expected_headers = [
            "company",
            "exam",
            "section",
            "topic",
            "question_text",
            "marks",
            "option1",
            "option2",
            "option3",
            "option4",
            "correct_option",
        ]

        if reader.fieldnames != expected_headers:
            return Response(
                {"error": "Invalid CSV header format"},
                status=status.HTTP_400_BAD_REQUEST
            )

        rows = list(reader)
        errors = []

        # ---------- VALIDATION PHASE ----------
        for index, row in enumerate(rows, start=2):  # start=2 because header is row 1

            try:
                if not row["company"]:
                    raise ValueError("Company missing")

                if not row["exam"]:
                    raise ValueError("Exam missing")

                if not row["section"]:
                    raise ValueError("Section missing")

                if not row["topic"]:
                    raise ValueError("Topic missing")

                if not row["question_text"]:
                    raise ValueError("Question text missing")

                for opt in ["option1", "option2", "option3", "option4"]:
                    if not row[opt]:
                        raise ValueError(f"{opt} missing")

                correct_option = int(row["correct_option"])
                if correct_option not in [1, 2, 3, 4]:
                    raise ValueError("correct_option must be 1,2,3,4")

                if row["marks"]:
                    int(row["marks"])  # check integer

            except Exception as e:
                errors.append({
                    "row": index,
                    "error": str(e)
                })

        if errors:
            return Response({
                "status": "error",
                "total_rows": len(rows),
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # ---------- INSERTION PHASE ----------
        touched_section_ids = set()
        with transaction.atomic():

            for row in rows:

                company, _ = Company.objects.get_or_create(
                    name=row["company"]
                )

                exam, _ = Exam.objects.get_or_create(
                    title=row["exam"],
                    company=company,
                    defaults={
                        "total_duration": 0,
                        "total_marks": 0,
                    },
                )

                section, _ = Section.objects.get_or_create(
                    name=row["section"],
                    exam=exam,
                    defaults={
                        "total_questions": 0,
                        "sectional_duration": 0,
                    },
                )
                touched_section_ids.add(section.id)

                topic, _ = Topic.objects.get_or_create(
                    name=row["topic"]
                )

                marks = int(row["marks"]) if row["marks"] else 1

                question = Question.objects.create(
                    text=row["question_text"],
                    marks=marks,
                    section=section,
                    topic=topic,
                    company=company
                )

                correct_index = int(row["correct_option"])

                options = [
                    row["option1"],
                    row["option2"],
                    row["option3"],
                    row["option4"],
                ]

                for i, option_text in enumerate(options, start=1):
                    Option.objects.create(
                        question=question,
                        text=option_text,
                        is_correct=(i == correct_index)
                    )

            # Keep section question counts in sync with actual data.
            for section_id in touched_section_ids:
                count = Question.objects.filter(section_id=section_id).count()
                Section.objects.filter(id=section_id).update(total_questions=count)

        return Response({
            "status": "success",
            "total_rows": len(rows),
            "inserted": len(rows)
        })
