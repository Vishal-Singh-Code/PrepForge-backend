import csv
from collections import defaultdict
from io import TextIOWrapper

from django.db.models import Sum
from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsAdminRole
from .models import Company, Exam, ExamPattern, PatternSectionRule, Section
from .serializers import (
    CompanySerializer,
    ExamPatternCreateSerializer,
    ExamSerializer,
    SectionSerializer,
)


class CompanyCreateView(generics.CreateAPIView):
    queryset = Company.objects.all().order_by('id')
    serializer_class = CompanySerializer
    permission_classes = [IsAdminRole]


class CompanyListView(ListAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]


class ExamCreateView(generics.CreateAPIView):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    permission_classes = [IsAdminRole]


class SectionCreateView(generics.CreateAPIView):
    queryset = Section.objects.all().order_by('id')
    serializer_class = SectionSerializer
    permission_classes = [IsAdminRole]


class ExamListView(ListAPIView):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        rows = list(serializer.data)

        exam_ids = [row["id"] for row in rows]
        if not exam_ids:
            return Response(rows)

        section_duration_map = {
            row["exam"]: row["sum_duration"] or 0
            for row in (
                Section.objects
                .filter(exam_id__in=exam_ids)
                .values("exam")
                .annotate(sum_duration=Sum("sectional_duration"))
            )
        }

        latest_active_pattern_sec = {}
        pattern_rows = (
            ExamPattern.objects
            .filter(exam_id__in=exam_ids, is_active=True)
            .order_by("exam_id", "-version")
            .values("exam_id", "total_duration_sec")
        )
        for row in pattern_rows:
            exam_id = row["exam_id"]
            if exam_id not in latest_active_pattern_sec:
                latest_active_pattern_sec[exam_id] = row["total_duration_sec"] or 0

        for row in rows:
            if (row.get("total_duration") or 0) > 0:
                continue

            exam_id = row["id"]
            pattern_sec = latest_active_pattern_sec.get(exam_id, 0)
            section_min = section_duration_map.get(exam_id, 0)

            if pattern_sec > 0:
                row["total_duration"] = max(1, round(pattern_sec / 60))
            elif section_min > 0:
                row["total_duration"] = section_min

        return Response(rows)


class SectionListView(ListAPIView):
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Section.objects.all().select_related("exam")
        exam_id = self.request.query_params.get("exam_id")
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        return queryset


class ExamPatternCreateView(generics.CreateAPIView):
    queryset = ExamPattern.objects.all()
    serializer_class = ExamPatternCreateSerializer
    permission_classes = [IsAdminRole]


class ExamPatternBulkUploadView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        decoded_file = TextIOWrapper(file.file, encoding="utf-8")
        reader = csv.DictReader(decoded_file)

        expected_headers = [
            "exam",
            "pattern_name",
            "version",
            "total_duration_sec",
            "is_active",
            "section",
            "order_no",
            "question_count",
            "section_duration_sec",
            "allow_section_switch",
        ]
        if reader.fieldnames != expected_headers:
            return Response(
                {"error": "Invalid CSV header format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = list(reader)
        if not rows:
            return Response({"error": "CSV has no data rows"}, status=status.HTTP_400_BAD_REQUEST)

        errors = []
        grouped_rows = defaultdict(list)

        def parse_bool(value):
            if value is None:
                return None
            normalized = value.strip().lower()
            if normalized in ["true", "1", "yes"]:
                return True
            if normalized in ["false", "0", "no"]:
                return False
            return None

        for index, row in enumerate(rows, start=2):
            try:
                if not row["exam"]:
                    raise ValueError("Exam missing")
                if not row["pattern_name"]:
                    raise ValueError("pattern_name missing")
                if not row["section"]:
                    raise ValueError("section missing")

                version = int(row["version"])
                total_duration_sec = int(row["total_duration_sec"])
                order_no = int(row["order_no"])
                question_count = int(row["question_count"])
                section_duration_sec = int(row["section_duration_sec"])
                is_active = parse_bool(row["is_active"])
                allow_switch = parse_bool(row["allow_section_switch"])

                if version < 1:
                    raise ValueError("version must be >= 1")
                if total_duration_sec < 1:
                    raise ValueError("total_duration_sec must be >= 1")
                if order_no < 1:
                    raise ValueError("order_no must be >= 1")
                if question_count < 1:
                    raise ValueError("question_count must be >= 1")
                if section_duration_sec < 1:
                    raise ValueError("section_duration_sec must be >= 1")
                if is_active is None:
                    raise ValueError("is_active must be true/false")
                if allow_switch is None:
                    raise ValueError("allow_section_switch must be true/false")

                grouped_key = (row["exam"].strip(), row["pattern_name"].strip(), version)
                grouped_rows[grouped_key].append(
                    {
                        "row_number": index,
                        "exam_title": row["exam"].strip(),
                        "pattern_name": row["pattern_name"].strip(),
                        "version": version,
                        "total_duration_sec": total_duration_sec,
                        "is_active": is_active,
                        "section_name": row["section"].strip(),
                        "order_no": order_no,
                        "question_count": question_count,
                        "section_duration_sec": section_duration_sec,
                        "allow_section_switch": allow_switch,
                    }
                )
            except Exception as exc:
                errors.append({"row": index, "error": str(exc)})

        if errors:
            return Response(
                {"status": "error", "total_rows": len(rows), "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inserted_patterns = 0
        inserted_rules = 0

        try:
            with transaction.atomic():
                for (exam_title, pattern_name, version), grouped in grouped_rows.items():
                    exam = Exam.objects.filter(title=exam_title).first()
                    if not exam:
                        raise ValueError(f"Exam not found: {exam_title}")

                    first_row = grouped[0]
                    total_duration_sec = first_row["total_duration_sec"]
                    is_active = first_row["is_active"]

                    for row in grouped[1:]:
                        if row["total_duration_sec"] != total_duration_sec:
                            raise ValueError(
                                f"Inconsistent total_duration_sec for pattern {pattern_name} (exam={exam_title}, version={version})"
                            )
                        if row["is_active"] != is_active:
                            raise ValueError(
                                f"Inconsistent is_active for pattern {pattern_name} (exam={exam_title}, version={version})"
                            )

                    pattern = ExamPattern.objects.create(
                        exam=exam,
                        name=pattern_name,
                        version=version,
                        total_duration_sec=total_duration_sec,
                        is_active=is_active,
                    )
                    inserted_patterns += 1

                    seen_orders = set()
                    seen_sections = set()
                    section_duration_sum = 0

                    for row in grouped:
                        section = Section.objects.filter(exam=exam, name=row["section_name"]).first()
                        if not section:
                            raise ValueError(
                                f"Section '{row['section_name']}' not found under exam '{exam_title}'"
                            )

                        if row["order_no"] in seen_orders:
                            raise ValueError(
                                f"Duplicate order_no={row['order_no']} in pattern {pattern_name}"
                            )
                        seen_orders.add(row["order_no"])

                        if section.id in seen_sections:
                            raise ValueError(
                                f"Duplicate section '{row['section_name']}' in pattern {pattern_name}"
                            )
                        seen_sections.add(section.id)

                        section_duration_sum += row["section_duration_sec"]

                        PatternSectionRule.objects.create(
                            exam_pattern=pattern,
                            section=section,
                            order_no=row["order_no"],
                            question_count=row["question_count"],
                            section_duration_sec=row["section_duration_sec"],
                            allow_section_switch=row["allow_section_switch"],
                        )
                        inserted_rules += 1

                    if section_duration_sum > pattern.total_duration_sec:
                        raise ValueError(
                            f"Sum of section_duration_sec exceeds total_duration_sec for pattern {pattern_name}"
                        )

        except IntegrityError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "status": "success",
                "total_rows": len(rows),
                "inserted_patterns": inserted_patterns,
                "inserted_rules": inserted_rules,
            }
        )
