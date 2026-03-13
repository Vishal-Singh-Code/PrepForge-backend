from rest_framework import status
from rest_framework.test import APITestCase

from datetime import timedelta

from analytics.models import TopicPerformance
from django.utils import timezone
from exams.models import Company, Exam, ExamPattern, PatternSectionRule, Section
from questions.models import Option, Question, Topic
from tests.models import AttemptAnswer, SessionQuestion
from users.models import User


class MockSessionFlowTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            email="student1@example.com",
            password="pass1234",
            role="student",
        )
        self.client.force_authenticate(user=self.student)

        self.company = Company.objects.create(name="TCS")
        self.exam = Exam.objects.create(
            company=self.company,
            title="TCS NQT 2025",
            total_duration=60,
            total_marks=100,
        )
        self.section = Section.objects.create(
            exam=self.exam,
            name="Quantitative Ability",
            total_questions=2,
            sectional_duration=30,
        )
        self.topic = Topic.objects.create(name="Time and Work")

        q1 = Question.objects.create(
            section=self.section,
            company=self.company,
            topic=self.topic,
            text="2+2=?",
            marks=1,
        )
        Option.objects.create(question=q1, text="1", is_correct=False)
        Option.objects.create(question=q1, text="2", is_correct=False)
        Option.objects.create(question=q1, text="3", is_correct=False)
        Option.objects.create(question=q1, text="4", is_correct=True)

        q2 = Question.objects.create(
            section=self.section,
            company=self.company,
            topic=self.topic,
            text="5+5=?",
            marks=1,
        )
        Option.objects.create(question=q2, text="5", is_correct=False)
        Option.objects.create(question=q2, text="10", is_correct=True)
        Option.objects.create(question=q2, text="15", is_correct=False)
        Option.objects.create(question=q2, text="20", is_correct=False)

        self.pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="NQT Pattern v1",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=self.pattern,
            section=self.section,
            order_no=1,
            question_count=2,
            section_duration_sec=1800,
            allow_section_switch=True,
        )

    def test_mock_session_start_answer_submit(self):
        start_resp = self.client.post(
            "/tests/mock/start/",
            {"exam_id": self.exam.id},
            format="json",
        )
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(start_resp.data["status"], "active")
        self.assertEqual(len(start_resp.data["questions"]), 2)

        session_id = start_resp.data["test_session_id"]
        question_ids = [q["id"] for q in start_resp.data["questions"]]

        first_qid = question_ids[0]
        second_qid = question_ids[1]

        first_correct = Option.objects.get(question_id=first_qid, is_correct=True)
        second_wrong = Option.objects.filter(question_id=second_qid, is_correct=False).first()

        ans1 = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": first_qid,
                "selected_option_id": first_correct.id,
                "time_spent_sec": 12,
            },
            format="json",
        )
        self.assertEqual(ans1.status_code, status.HTTP_200_OK)
        self.assertTrue(ans1.data["saved"])

        ans2 = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": second_qid,
                "selected_option_id": second_wrong.id,
                "time_spent_sec": 18,
            },
            format="json",
        )
        self.assertEqual(ans2.status_code, status.HTTP_200_OK)

        submit_resp = self.client.post(
            "/tests/mock/submit/",
            {"test_session_id": session_id},
            format="json",
        )
        self.assertEqual(submit_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_resp.data["status"], "submitted")
        self.assertEqual(submit_resp.data["total_questions"], 2)
        self.assertEqual(submit_resp.data["correct_answers"], 1)
        self.assertEqual(submit_resp.data["incorrect_answers"], 1)
        self.assertEqual(submit_resp.data["unattempted"], 0)
        self.assertEqual(len(submit_resp.data["sections"]), 1)

        result_resp = self.client.get(f"/tests/mock/result/{session_id}/")
        self.assertEqual(result_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(result_resp.data["test_session_id"], session_id)
        self.assertEqual(result_resp.data["score"], submit_resp.data["score"])
        self.assertEqual(result_resp.data["correct_answers"], 1)
        self.assertEqual(result_resp.data["incorrect_answers"], 1)
        self.assertEqual(result_resp.data["unattempted"], 0)
        self.assertEqual(len(result_resp.data["sections"]), 1)

        review_resp = self.client.get(f"/tests/mock/review/{session_id}/")
        self.assertEqual(review_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(review_resp.data["test_session_id"], session_id)
        self.assertEqual(len(review_resp.data["questions"]), 2)
        first_item = review_resp.data["questions"][0]
        self.assertIn("selected_option_id", first_item)
        self.assertIn("correct_option_id", first_item)
        self.assertIn("is_correct", first_item)
        self.assertIn("time_spent_sec", first_item)

        perf = TopicPerformance.objects.get(student=self.student, topic=self.topic)
        self.assertEqual(perf.total_attempted, 2)
        self.assertEqual(perf.total_correct, 1)


class PracticeSessionFlowTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student2",
            email="student2@example.com",
            password="pass1234",
            role="student",
        )
        self.client.force_authenticate(user=self.student)

        company = Company.objects.create(name="Infosys")
        exam = Exam.objects.create(
            company=company,
            title="Infosys Test",
            total_duration=60,
            total_marks=100,
        )
        self.section = Section.objects.create(
            exam=exam,
            name="Verbal Ability",
            total_questions=5,
            sectional_duration=30,
        )
        self.topic = Topic.objects.create(name="Reading Comprehension")

        self.question = Question.objects.create(
            section=self.section,
            company=company,
            topic=self.topic,
            text="Choose synonym of quick",
            marks=1,
        )
        Option.objects.create(question=self.question, text="slow", is_correct=False)
        self.correct_option = Option.objects.create(question=self.question, text="fast", is_correct=True)
        Option.objects.create(question=self.question, text="late", is_correct=False)
        Option.objects.create(question=self.question, text="weak", is_correct=False)

    def test_practice_start_answer_submit(self):
        start_resp = self.client.post(
            "/tests/practice/start/",
            {
                "section_id": self.section.id,
                "question_count": 1,
                "duration_sec": 600,
            },
            format="json",
        )
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(start_resp.data["type"], "practice_section")
        self.assertEqual(len(start_resp.data["questions"]), 1)

        session_id = start_resp.data["test_session_id"]
        qid = start_resp.data["questions"][0]["id"]

        ans_resp = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": qid,
                "selected_option_id": self.correct_option.id,
                "time_spent_sec": 14,
                "marked_for_review": True,
            },
            format="json",
        )
        self.assertEqual(ans_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(ans_resp.data["saved"])

        submit_resp = self.client.post(
            "/tests/practice/submit/",
            {"test_session_id": session_id},
            format="json",
        )
        self.assertEqual(submit_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_resp.data["status"], "submitted")
        self.assertEqual(submit_resp.data["total_questions"], 1)
        self.assertEqual(submit_resp.data["correct_answers"], 1)
        self.assertEqual(submit_resp.data["incorrect_answers"], 0)

        result_resp = self.client.get(f"/tests/practice/result/{session_id}/")
        self.assertEqual(result_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(result_resp.data["test_session_id"], session_id)
        self.assertEqual(result_resp.data["status"], "submitted")
        self.assertEqual(result_resp.data["correct_answers"], 1)

        review_resp = self.client.get(f"/tests/practice/review/{session_id}/")
        self.assertEqual(review_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(review_resp.data["test_session_id"], session_id)
        self.assertEqual(len(review_resp.data["questions"]), 1)
        self.assertEqual(review_resp.data["questions"][0]["marked_for_review"], True)


class WeakPracticeSessionFlowTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student3",
            email="student3@example.com",
            password="pass1234",
            role="student",
        )
        self.client.force_authenticate(user=self.student)

        company = Company.objects.create(name="Wipro")
        exam = Exam.objects.create(
            company=company,
            title="Wipro Elite",
            total_duration=60,
            total_marks=100,
        )
        section = Section.objects.create(
            exam=exam,
            name="Logical Ability",
            total_questions=2,
            sectional_duration=30,
        )
        topic = Topic.objects.create(name="Series")

        q1 = Question.objects.create(
            section=section,
            company=company,
            topic=topic,
            text="2,4,6,?",
            marks=1,
        )
        Option.objects.create(question=q1, text="7", is_correct=False)
        Option.objects.create(question=q1, text="8", is_correct=True)
        Option.objects.create(question=q1, text="9", is_correct=False)
        Option.objects.create(question=q1, text="10", is_correct=False)

        q2 = Question.objects.create(
            section=section,
            company=company,
            topic=topic,
            text="1,1,2,3,5,?",
            marks=1,
        )
        Option.objects.create(question=q2, text="6", is_correct=False)
        Option.objects.create(question=q2, text="7", is_correct=False)
        Option.objects.create(question=q2, text="8", is_correct=True)
        Option.objects.create(question=q2, text="9", is_correct=False)

        TopicPerformance.objects.create(
            student=self.student,
            topic=topic,
            total_attempted=10,
            total_correct=3,
        )

    def test_weak_practice_session_start(self):
        response = self.client.post(
            "/tests/practice/weak/start/",
            {"questions_per_topic": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "weak_practice")
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(len(response.data["topics_used"]), 1)
        self.assertGreaterEqual(len(response.data["questions"]), 1)


class PracticeTopicSessionFlowTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student_topic",
            email="student_topic@example.com",
            password="pass1234",
            role="student",
        )
        self.client.force_authenticate(user=self.student)

        company = Company.objects.create(name="Practice Topic Co")
        exam = Exam.objects.create(
            company=company,
            title="Practice Topic Exam",
            total_duration=60,
            total_marks=100,
        )
        section = Section.objects.create(
            exam=exam,
            name="Quantitative Ability",
            total_questions=5,
            sectional_duration=30,
        )
        self.topic = Topic.objects.create(name="Percentages")

        q1 = Question.objects.create(
            section=section,
            company=company,
            topic=self.topic,
            text="What is 20% of 50?",
            marks=1,
        )
        Option.objects.create(question=q1, text="5", is_correct=False)
        self.correct1 = Option.objects.create(question=q1, text="10", is_correct=True)
        Option.objects.create(question=q1, text="12", is_correct=False)
        Option.objects.create(question=q1, text="15", is_correct=False)

    def test_practice_topic_start_and_submit(self):
        start_resp = self.client.post(
            "/tests/practice/topic/start/",
            {"topic_id": self.topic.id, "question_count": 1, "duration_sec": 600},
            format="json",
        )
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(start_resp.data["type"], "practice_topic")
        self.assertEqual(len(start_resp.data["questions"]), 1)

        session_id = start_resp.data["test_session_id"]
        question_id = start_resp.data["questions"][0]["id"]

        ans_resp = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": question_id,
                "selected_option_id": self.correct1.id,
                "time_spent_sec": 11,
            },
            format="json",
        )
        self.assertEqual(ans_resp.status_code, status.HTTP_200_OK)

        submit_resp = self.client.post(
            "/tests/practice/submit/",
            {"test_session_id": session_id},
            format="json",
        )
        self.assertEqual(submit_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_resp.data["status"], "submitted")


class SectionRuleEnforcementTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student4",
            email="student4@example.com",
            password="pass1234",
            role="student",
        )
        self.client.force_authenticate(user=self.student)

        self.company = Company.objects.create(name="Capgemini")
        self.exam = Exam.objects.create(
            company=self.company,
            title="Capgemini Aptitude",
            total_duration=60,
            total_marks=100,
        )
        self.section1 = Section.objects.create(
            exam=self.exam,
            name="Quant",
            total_questions=1,
            sectional_duration=30,
        )
        self.section2 = Section.objects.create(
            exam=self.exam,
            name="Verbal",
            total_questions=1,
            sectional_duration=30,
        )
        topic = Topic.objects.create(name="General")

        self.q1 = Question.objects.create(
            section=self.section1,
            company=self.company,
            topic=topic,
            text="1+1=?",
            marks=1,
        )
        Option.objects.create(question=self.q1, text="1", is_correct=False)
        self.q1_correct = Option.objects.create(question=self.q1, text="2", is_correct=True)
        Option.objects.create(question=self.q1, text="3", is_correct=False)
        Option.objects.create(question=self.q1, text="4", is_correct=False)

        self.q2 = Question.objects.create(
            section=self.section2,
            company=self.company,
            topic=topic,
            text="Synonym of large?",
            marks=1,
        )
        Option.objects.create(question=self.q2, text="tiny", is_correct=False)
        self.q2_correct = Option.objects.create(question=self.q2, text="big", is_correct=True)
        Option.objects.create(question=self.q2, text="small", is_correct=False)
        Option.objects.create(question=self.q2, text="narrow", is_correct=False)

    def test_locked_sections_block_answering_future_section(self):
        pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="Locked Pattern",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section1,
            order_no=1,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=False,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section2,
            order_no=2,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=False,
        )

        start_resp = self.client.post("/tests/mock/start/", {"exam_id": self.exam.id}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        session_id = start_resp.data["test_session_id"]

        answer_resp = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": self.q2.id,
                "selected_option_id": self.q2_correct.id,
            },
            format="json",
        )
        self.assertEqual(answer_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("section", answer_resp.data["error"].lower())

    def test_switchable_sections_allow_cross_section_answering(self):
        pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="Switchable Pattern",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section1,
            order_no=1,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section2,
            order_no=2,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=True,
        )

        start_resp = self.client.post("/tests/mock/start/", {"exam_id": self.exam.id}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        session_id = start_resp.data["test_session_id"]

        answer_resp = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": self.q2.id,
                "selected_option_id": self.q2_correct.id,
            },
            format="json",
        )
        self.assertEqual(answer_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(answer_resp.data["saved"])

    def test_section_timer_blocks_answer_after_expiry(self):
        pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="Timer Pattern",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section1,
            order_no=1,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=False,
        )

        start_resp = self.client.post("/tests/mock/start/", {"exam_id": self.exam.id}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        session_id = start_resp.data["test_session_id"]

        from tests.models import SessionSectionState
        state = SessionSectionState.objects.get(test_session_id=session_id, section=self.section1)
        state.expires_at = timezone.now() - timedelta(seconds=1)
        state.save(update_fields=["expires_at"])

        answer_resp = self.client.post(
            "/tests/mock/answer/",
            {
                "test_session_id": session_id,
                "question_id": self.q1.id,
                "selected_option_id": self.q1_correct.id,
            },
            format="json",
        )
        self.assertEqual(answer_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("section time is over", answer_resp.data["error"].lower())

    def test_current_and_next_section_endpoints_for_locked_pattern(self):
        pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="Locked Pattern Section API",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section1,
            order_no=1,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=False,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section2,
            order_no=2,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=False,
        )

        start_resp = self.client.post("/tests/mock/start/", {"exam_id": self.exam.id}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        session_id = start_resp.data["test_session_id"]

        current_resp = self.client.get(f"/tests/mock/section/current/?test_session_id={session_id}")
        self.assertEqual(current_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(current_resp.data["section_id"], self.section1.id)
        self.assertEqual(current_resp.data["allow_section_switch"], False)

        next_resp = self.client.post(
            "/tests/mock/section/next/",
            {"test_session_id": session_id},
            format="json",
        )
        self.assertEqual(next_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(next_resp.data["section_id"], self.section2.id)

    def test_next_section_blocked_for_switchable_pattern(self):
        pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="Switchable Pattern Section API",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section1,
            order_no=1,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section2,
            order_no=2,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=True,
        )

        start_resp = self.client.post("/tests/mock/start/", {"exam_id": self.exam.id}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        session_id = start_resp.data["test_session_id"]

        next_resp = self.client.post(
            "/tests/mock/section/next/",
            {"test_session_id": session_id},
            format="json",
        )
        self.assertEqual(next_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("switching is enabled", next_resp.data["error"].lower())

    def test_answer_autosave_is_idempotent_and_palette_updates(self):
        pattern = ExamPattern.objects.create(
            exam=self.exam,
            version=1,
            name="Palette Pattern",
            total_duration_sec=3600,
            is_active=True,
        )
        PatternSectionRule.objects.create(
            exam_pattern=pattern,
            section=self.section1,
            order_no=1,
            question_count=1,
            section_duration_sec=1800,
            allow_section_switch=True,
        )

        start_resp = self.client.post("/tests/mock/start/", {"exam_id": self.exam.id}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED)
        session_id = start_resp.data["test_session_id"]

        ans_payload = {
            "test_session_id": session_id,
            "question_id": self.q1.id,
            "selected_option_id": self.q1_correct.id,
            "time_spent_sec": 15,
            "marked_for_review": True,
        }
        first_save = self.client.post("/tests/mock/answer/", ans_payload, format="json")
        self.assertEqual(first_save.status_code, status.HTTP_200_OK)

        second_payload = dict(ans_payload)
        second_payload["time_spent_sec"] = 10
        second_save = self.client.post("/tests/mock/answer/", second_payload, format="json")
        self.assertEqual(second_save.status_code, status.HTTP_200_OK)

        self.assertEqual(
            AttemptAnswer.objects.filter(test_session_id=session_id, question_id=self.q1.id).count(),
            1,
        )
        answer = AttemptAnswer.objects.get(test_session_id=session_id, question_id=self.q1.id)
        self.assertEqual(answer.time_spent_sec, 15)
        self.assertTrue(answer.marked_for_review)

        sq = SessionQuestion.objects.get(test_session_id=session_id, question_id=self.q1.id)
        self.assertTrue(sq.is_answered)
        self.assertTrue(sq.is_marked_for_review)
        self.assertEqual(sq.time_spent_sec_total, 15)
        self.assertIsNotNone(sq.seen_at)
        self.assertIsNotNone(sq.last_visited_at)

        palette_resp = self.client.get(f"/tests/mock/palette/?test_session_id={session_id}")
        self.assertEqual(palette_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(palette_resp.data["counts"]["answered_marked"], 1)
        self.assertEqual(palette_resp.data["counts"]["total"], 1)
        self.assertEqual(palette_resp.data["questions"][0]["status"], "answered_marked")
