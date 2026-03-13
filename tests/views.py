from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsStudentRole
from exams.models import Exam
from questions.serializers import StudentQuestionSerializer
from .models import MockTest, SessionQuestion, SessionSectionState, TestSession
from .serializers import (
    MockSessionAnswerSerializer,
    MockSessionPaletteSerializer,
    MockSessionSectionCurrentSerializer,
    MockSessionSectionNextSerializer,
    MockSessionStartSerializer,
    MockSessionSubmitSerializer,
    MockTestResponseSerializer,
    PracticeSectionStartSerializer,
    PracticeSectionSubmitSerializer,
    PracticeTopicStartSerializer,
    StartTestSerializer,
    SubmitTestSerializer,
    WeakPracticeSessionStartSerializer,
)
from .services import (
    advance_to_next_section,
    build_session_question_palette,
    create_mock_session,
    create_practice_section_session,
    create_practice_topic_session,
    create_weak_practice_session,
    evaluate_and_submit,
    generate_mock_test,
    generate_weak_topic_practice,
    get_current_section_state,
    save_session_answer,
    submit_mock_session,
)


class StartTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exam_id = serializer.validated_data["exam_id"]

        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({"error": "Exam not found"}, status=status.HTTP_404_NOT_FOUND)

        mock_test = generate_mock_test(request.user, exam)
        response_serializer = MockTestResponseSerializer(mock_test)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SubmitTestView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = SubmitTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mock_test_id = serializer.validated_data["mock_test_id"]
        answers = serializer.validated_data["answers"]

        try:
            mock_test = MockTest.objects.get(id=mock_test_id, student=request.user)
        except MockTest.DoesNotExist:
            return Response({"error": "Mock test not found"}, status=status.HTTP_404_NOT_FOUND)

        if mock_test.is_completed:
            return Response({"error": "Test already submitted"}, status=status.HTTP_400_BAD_REQUEST)

        result = evaluate_and_submit(mock_test, answers)
        return Response({"mock_test_id": mock_test.id, **result}, status=status.HTTP_200_OK)


class TestHistoryView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        sessions = (
            TestSession.objects
            .select_related("exam")
            .filter(student=request.user, status__in=["submitted", "expired"])
            .order_by("-submitted_at", "-started_at")
        )

        payload = []
        for session in sessions:
            total_questions = session.session_questions.count()
            correct_answers = session.answers.filter(is_correct=True).count()
            accuracy_percentage = round((correct_answers / total_questions) * 100, 2) if total_questions > 0 else 0

            payload.append(
                {
                    "id": session.id,
                    "exam_title": session.exam.title if session.exam else "Practice Test",
                    "score": session.total_score,
                    "status": session.status,
                    "session_type": session.test_type,
                    "created_at": session.submitted_at or session.started_at,
                    "correct_answers": correct_answers,
                    "total_questions": total_questions,
                    "accuracy_percentage": accuracy_percentage,
                }
            )
        return Response(payload, status=status.HTTP_200_OK)


class TestResultView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request, mock_test_id):
        try:
            mock_test = MockTest.objects.get(
                id=mock_test_id,
                student=request.user,
                is_completed=True,
            )
        except MockTest.DoesNotExist:
            return Response({"error": "Test not found"}, status=status.HTTP_404_NOT_FOUND)

        test_questions = mock_test.test_questions.all()
        attempts = mock_test.answers.all()

        correct_count = attempts.filter(is_correct=True).count()
        incorrect_count = attempts.filter(is_correct=False).count()
        total_questions = test_questions.count()
        unattempted = total_questions - attempts.count()

        score = sum(attempt.question.marks for attempt in attempts if attempt.is_correct)

        question_review = []
        for tq in test_questions:
            attempt = attempts.filter(question=tq.question).first()
            question_review.append(
                {
                    "question_id": tq.question.id,
                    "text": tq.question.text,
                    "selected_option_id": attempt.selected_option_id if attempt else None,
                    "is_correct": attempt.is_correct if attempt else False,
                }
            )

        return Response(
            {
                "mock_test_id": mock_test.id,
                "exam": mock_test.exam.title if mock_test.exam else "Practice Test",
                "score": score,
                "correct_answers": correct_count,
                "incorrect_answers": incorrect_count,
                "unattempted": unattempted,
                "questions": question_review,
            }
        )


class WeakPracticeTestView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        result = generate_weak_topic_practice(request.user)

        if not result:
            return Response({"message": "No weak topics detected"}, status=status.HTTP_200_OK)

        mock_test, weak_topics = result
        test_questions = mock_test.test_questions.all()
        questions = [tq.question for tq in test_questions]

        return Response(
            {
                "mock_test_id": mock_test.id,
                "type": "weak_topic_practice",
                "topics_used": [t.name for t in weak_topics],
                "questions": StudentQuestionSerializer(questions, many=True).data,
            }
        )


class MockSessionStartView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = MockSessionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = create_mock_session(
                student=request.user,
                exam_id=serializer.validated_data.get("exam_id"),
                exam_pattern_id=serializer.validated_data.get("exam_pattern_id"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        session_questions = (
            SessionQuestion.objects
            .select_related("question")
            .filter(test_session=session)
            .order_by("display_order")
        )
        questions = [sq.question for sq in session_questions]

        return Response(
            {
                "test_session_id": session.id,
                "type": "full_mock",
                "exam_pattern_id": session.exam_pattern_id,
                "exam_id": session.exam_id,
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "questions": StudentQuestionSerializer(questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MockSessionAnswerView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = MockSessionAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            answer = save_session_answer(
                student=request.user,
                test_session_id=serializer.validated_data["test_session_id"],
                question_id=serializer.validated_data["question_id"],
                selected_option_id=serializer.validated_data["selected_option_id"],
                time_spent_sec=serializer.validated_data.get("time_spent_sec", 0),
                marked_for_review=serializer.validated_data.get("marked_for_review", False),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "test_session_id": answer.test_session_id,
                "question_id": answer.question_id,
                "saved": True,
                "marked_for_review": answer.marked_for_review,
            },
            status=status.HTTP_200_OK,
        )


class MockSessionSubmitView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = MockSessionSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = submit_mock_session(
                student=request.user,
                test_session_id=serializer.validated_data["test_session_id"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class MockSessionResultView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request, test_session_id):
        session = (
            TestSession.objects
            .select_related("exam")
            .filter(id=test_session_id, student=request.user)
            .first()
        )
        if not session:
            return Response({"error": "Test session not found"}, status=status.HTTP_404_NOT_FOUND)
        if session.status not in ["submitted", "expired"]:
            return Response({"error": "Test session is not submitted yet"}, status=status.HTTP_400_BAD_REQUEST)

        session_questions = list(
            SessionQuestion.objects.select_related("section").filter(test_session=session)
        )
        answers = list(session.answers.all())
        answered_ids = {a.question_id for a in answers}
        correct_count = sum(1 for a in answers if a.is_correct)
        incorrect_count = sum(1 for a in answers if not a.is_correct)
        total_questions = len(session_questions)
        unattempted = total_questions - len(answered_ids)
        total_time_sec = sum(a.time_spent_sec for a in answers)

        section_states = SessionSectionState.objects.filter(test_session=session).order_by("order_no")
        sections = [
            {
                "section_id": s.section_id,
                "order_no": s.order_no,
                "score": s.score,
                "attempted": s.attempted_count,
                "correct": s.correct_count,
                "incorrect": s.incorrect_count,
                "unattempted": s.unattempted_count,
            }
            for s in section_states
        ]

        return Response(
            {
                "test_session_id": session.id,
                "exam": session.exam.title if session.exam else "Practice Test",
                "status": session.status,
                "score": session.total_score,
                "total_questions": total_questions,
                "correct_answers": correct_count,
                "incorrect_answers": incorrect_count,
                "unattempted": unattempted,
                "total_time_sec": total_time_sec,
                "sections": sections,
            }
        )


class MockSessionReviewView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request, test_session_id):
        session = TestSession.objects.filter(id=test_session_id, student=request.user).first()
        if not session:
            return Response({"error": "Test session not found"}, status=status.HTTP_404_NOT_FOUND)
        if session.status not in ["submitted", "expired"]:
            return Response({"error": "Test session is not submitted yet"}, status=status.HTTP_400_BAD_REQUEST)

        session_questions = (
            SessionQuestion.objects
            .select_related("question", "section", "question__topic")
            .filter(test_session=session)
            .order_by("display_order")
        )
        answers_map = {a.question_id: a for a in session.answers.all()}

        review_items = []
        for sq in session_questions:
            answer = answers_map.get(sq.question_id)
            correct_option = sq.question.options.filter(is_correct=True).first()
            options = [
                {
                    "id": opt.id,
                    "text": opt.text,
                    "is_correct": opt.is_correct,
                }
                for opt in sq.question.options.all().order_by("id")
            ]
            review_items.append(
                {
                    "question_id": sq.question_id,
                    "display_order": sq.display_order,
                    "section_id": sq.section_id,
                    "section_name": sq.section.name,
                    "topic": sq.question.topic.name if sq.question.topic else None,
                    "question_text": sq.question.text,
                    "selected_option_id": answer.selected_option_id if answer else None,
                    "correct_option_id": correct_option.id if correct_option else None,
                    "is_correct": answer.is_correct if answer else False,
                    "time_spent_sec": answer.time_spent_sec if answer else 0,
                    "marked_for_review": answer.marked_for_review if answer else False,
                    "explanation": getattr(sq.question, "explanation", ""),
                    "options": options,
                }
            )

        return Response(
            {
                "test_session_id": session.id,
                "status": session.status,
                "questions": review_items,
            }
        )


class PracticeSessionStartView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = PracticeSectionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = create_practice_section_session(
                student=request.user,
                mode=serializer.validated_data.get("mode", "single_exam"),
                section_id=serializer.validated_data.get("section_id"),
                section_name=serializer.validated_data.get("section_name"),
                question_count=serializer.validated_data.get("question_count"),
                duration_sec=serializer.validated_data.get("duration_sec"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        session_questions = (
            SessionQuestion.objects
            .select_related("question")
            .filter(test_session=session)
            .order_by("display_order")
        )
        questions = [sq.question for sq in session_questions]

        return Response(
            {
                "test_session_id": session.id,
                "type": "practice_section",
                "mode": serializer.validated_data.get("mode", "single_exam"),
                "section_id": serializer.validated_data.get("section_id"),
                "section_name": serializer.validated_data.get("section_name"),
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "questions": StudentQuestionSerializer(questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PracticeSessionSubmitView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = PracticeSectionSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = TestSession.objects.filter(
                id=serializer.validated_data["test_session_id"],
                student=request.user,
            ).first()
            if not session or session.test_type not in ["practice_section", "practice_topic", "weak_practice"]:
                return Response({"error": "Practice session not found"}, status=status.HTTP_404_NOT_FOUND)

            result = submit_mock_session(
                student=request.user,
                test_session_id=serializer.validated_data["test_session_id"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class PracticeTopicSessionStartView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = PracticeTopicStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = create_practice_topic_session(
                student=request.user,
                mode=serializer.validated_data.get("mode", "single_exam"),
                topic_id=serializer.validated_data.get("topic_id"),
                topic_name=serializer.validated_data.get("topic_name"),
                question_count=serializer.validated_data.get("question_count"),
                duration_sec=serializer.validated_data.get("duration_sec"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        session_questions = (
            SessionQuestion.objects
            .select_related("question")
            .filter(test_session=session)
            .order_by("display_order")
        )
        questions = [sq.question for sq in session_questions]

        return Response(
            {
                "test_session_id": session.id,
                "type": "practice_topic",
                "mode": serializer.validated_data.get("mode", "single_exam"),
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "questions": StudentQuestionSerializer(questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PracticeSessionResultView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request, test_session_id):
        session = TestSession.objects.filter(id=test_session_id, student=request.user).first()
        if not session or session.test_type not in ["practice_section", "practice_topic", "weak_practice"]:
            return Response({"error": "Practice session not found"}, status=status.HTTP_404_NOT_FOUND)
        return MockSessionResultView().get(request, test_session_id)


class PracticeSessionReviewView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request, test_session_id):
        session = TestSession.objects.filter(id=test_session_id, student=request.user).first()
        if not session or session.test_type not in ["practice_section", "practice_topic", "weak_practice"]:
            return Response({"error": "Practice session not found"}, status=status.HTTP_404_NOT_FOUND)
        return MockSessionReviewView().get(request, test_session_id)


class WeakPracticeSessionStartView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = WeakPracticeSessionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session, weak_topics = create_weak_practice_session(
                student=request.user,
                questions_per_topic=serializer.validated_data["questions_per_topic"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        session_questions = (
            SessionQuestion.objects
            .select_related("question")
            .filter(test_session=session)
            .order_by("display_order")
        )
        questions = [sq.question for sq in session_questions]

        return Response(
            {
                "test_session_id": session.id,
                "type": "weak_practice",
                "topics_used": [topic.name for topic in weak_topics],
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "questions": StudentQuestionSerializer(questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MockSessionCurrentSectionView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        serializer = MockSessionSectionCurrentSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        try:
            session, current_state, allow_switch = get_current_section_state(
                student=request.user,
                test_session_id=serializer.validated_data["test_session_id"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "test_session_id": session.id,
                "section_id": current_state.section_id,
                "section_name": current_state.section.name,
                "order_no": current_state.order_no,
                "started_at": current_state.started_at,
                "expires_at": current_state.expires_at,
                "allow_section_switch": allow_switch,
            }
        )


class MockSessionNextSectionView(APIView):
    permission_classes = [IsStudentRole]

    def post(self, request):
        serializer = MockSessionSectionNextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session, next_state = advance_to_next_section(
                student=request.user,
                test_session_id=serializer.validated_data["test_session_id"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "test_session_id": session.id,
                "section_id": next_state.section_id,
                "section_name": next_state.section.name,
                "order_no": next_state.order_no,
                "started_at": next_state.started_at,
                "expires_at": next_state.expires_at,
            }
        )


class MockSessionPaletteView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        serializer = MockSessionPaletteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        try:
            payload = build_session_question_palette(
                student=request.user,
                test_session_id=serializer.validated_data["test_session_id"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload, status=status.HTTP_200_OK)
