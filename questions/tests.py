from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User
from exams.models import Company, Exam, Section
from questions.models import Question, Option, Topic


class QuestionBulkUploadTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="pass1234",
            role="admin",
        )
        self.client.force_authenticate(user=self.admin)

    def test_bulk_upload_csv_creates_questions_and_options(self):
        csv_content = (
            "company,exam,section,topic,question_text,marks,option1,option2,option3,option4,correct_option\n"
            "TCS,TCS NQT 2025,Quantitative Ability,Time and Work,2+2=?,1,1,2,3,4,4\n"
            "TCS,TCS NQT 2025,Quantitative Ability,Time and Work,5+5=?,1,5,10,15,20,2\n"
        )
        upload = SimpleUploadedFile(
            "test_upload.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/questions/bulk-upload/",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["inserted"], 2)

        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Exam.objects.count(), 1)
        self.assertEqual(Section.objects.count(), 1)
        self.assertEqual(Topic.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 2)
        self.assertEqual(Option.objects.count(), 8)

        for question in Question.objects.all():
            self.assertEqual(question.options.count(), 4)
            self.assertEqual(question.options.filter(is_correct=True).count(), 1)
