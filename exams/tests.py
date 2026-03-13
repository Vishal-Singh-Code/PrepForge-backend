from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User
from .models import Company, Exam, ExamPattern, PatternSectionRule, Section


class ExamPatternApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_exams",
            email="admin_exams@example.com",
            password="pass1234",
            role="admin",
        )
        self.client.force_authenticate(user=self.admin)

        self.company = Company.objects.create(name="Pattern Co")
        self.exam = Exam.objects.create(
            company=self.company,
            title="Pattern Exam 2026",
            total_duration=60,
            total_marks=100,
        )
        self.section1 = Section.objects.create(
            exam=self.exam,
            name="Quant",
            total_questions=20,
            sectional_duration=30,
        )
        self.section2 = Section.objects.create(
            exam=self.exam,
            name="Verbal",
            total_questions=20,
            sectional_duration=30,
        )

    def test_create_pattern_with_rules_json(self):
        payload = {
            "exam": self.exam.id,
            "version": 1,
            "name": "Mock Pattern v1",
            "total_duration_sec": 3600,
            "is_active": True,
            "rules": [
                {
                    "section_id": self.section1.id,
                    "order_no": 1,
                    "question_count": 10,
                    "section_duration_sec": 1200,
                    "allow_section_switch": False,
                },
                {
                    "section_id": self.section2.id,
                    "order_no": 2,
                    "question_count": 10,
                    "section_duration_sec": 1200,
                    "allow_section_switch": False,
                },
            ],
        }

        response = self.client.post("/exams/pattern/create/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ExamPattern.objects.count(), 1)
        self.assertEqual(PatternSectionRule.objects.count(), 2)

    def test_bulk_upload_pattern_csv(self):
        csv_content = (
            "exam,pattern_name,version,total_duration_sec,is_active,section,order_no,question_count,section_duration_sec,allow_section_switch\n"
            "Pattern Exam 2026,Mock Pattern CSV,1,3600,true,Quant,1,10,1200,false\n"
            "Pattern Exam 2026,Mock Pattern CSV,1,3600,true,Verbal,2,10,1200,false\n"
        )
        upload = SimpleUploadedFile(
            "patterns.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/exams/pattern/bulk-upload/",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["inserted_patterns"], 1)
        self.assertEqual(response.data["inserted_rules"], 2)
        self.assertEqual(ExamPattern.objects.count(), 1)
        self.assertEqual(PatternSectionRule.objects.count(), 2)
