from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from analytics.models import TopicPerformance
from exams.models import Exam, ExamPattern, Section
from questions.models import Option, Question
from .models import (
    AttemptAnswer,
    MockTest,
    SessionQuestion,
    SessionSectionState,
    TestQuestion,
    TestSession,
)


def generate_mock_test(student, exam):
    mock_test = MockTest.objects.create(student=student, exam=exam)

    for section in exam.sections.all():
        questions = Question.objects.filter(section=section)
        selected_questions = questions.order_by("?")[:section.total_questions]

        for question in selected_questions:
            TestQuestion.objects.create(mock_test=mock_test, question=question)

    return mock_test


@transaction.atomic
def evaluate_and_submit(mock_test, answers_data):
    total_score = 0
    correct_count = 0
    incorrect_count = 0

    if mock_test.is_completed:
        raise ValueError("Test already submitted")

    test_questions = TestQuestion.objects.filter(mock_test=mock_test)
    total_questions = test_questions.count()
    valid_question_ids = set(test_questions.values_list("question_id", flat=True))
    answered_question_ids = set()

    for answer in answers_data:
        question_id = answer["question_id"]
        selected_option_id = answer["selected_option_id"]

        if question_id not in valid_question_ids:
            continue

        answered_question_ids.add(question_id)

        try:
            option = Option.objects.get(id=selected_option_id, question_id=question_id)
            is_correct = option.is_correct
            question = option.question
        except Option.DoesNotExist:
            continue

        if is_correct:
            total_score += question.marks
            correct_count += 1
        else:
            incorrect_count += 1

        AttemptAnswer.objects.create(
            mock_test=mock_test,
            question=question,
            selected_option_id=selected_option_id,
            is_correct=is_correct,
        )

        topic = question.topic
        if topic:
            performance, _ = TopicPerformance.objects.get_or_create(
                student=mock_test.student,
                topic=topic,
            )
            performance.total_attempted += 1
            if is_correct:
                performance.total_correct += 1
            performance.save()

    unattempted = total_questions - len(answered_question_ids)
    mock_test.score = total_score
    mock_test.is_completed = True
    mock_test.save()

    return {
        "total_questions": total_questions,
        "correct_answers": correct_count,
        "incorrect_answers": incorrect_count,
        "unattempted": unattempted,
        "score": total_score,
    }


@transaction.atomic
def generate_weak_topic_practice(student, questions_per_topic=5):
    weak_performances = TopicPerformance.objects.filter(
        student=student, total_attempted__gt=0
    ).select_related("topic")

    weak_topics = [
        perf.topic
        for perf in weak_performances
        if (perf.total_correct / perf.total_attempted) * 100 < 60
    ]

    if not weak_topics:
        return None

    last_test = MockTest.objects.filter(
        student=student, exam__isnull=False
    ).order_by("-created_at").first()
    exam = last_test.exam if last_test else None

    mock_test = MockTest.objects.create(
        student=student,
        exam=exam,
        test_type="weak_practice",
    )

    for topic in weak_topics:
        questions = Question.objects.filter(topic=topic).order_by("?")[:questions_per_topic]
        for question in questions:
            TestQuestion.objects.create(mock_test=mock_test, question=question)

    return mock_test, weak_topics


def _get_exam_pattern(exam_id=None, exam_pattern_id=None):
    if exam_pattern_id:
        return ExamPattern.objects.select_related("exam").filter(
            id=exam_pattern_id, is_active=True
        ).first()

    if not exam_id:
        return None

    return ExamPattern.objects.select_related("exam").filter(
        exam_id=exam_id, is_active=True
    ).order_by("-version").first()


@transaction.atomic
def create_mock_session(student, exam_id=None, exam_pattern_id=None):
    pattern = _get_exam_pattern(exam_id=exam_id, exam_pattern_id=exam_pattern_id)
    if not pattern:
        raise ValueError("Active exam pattern not found")

    rules = list(pattern.section_rules.select_related("section").order_by("order_no"))
    if not rules:
        raise ValueError("No section rules configured for this pattern")

    now = timezone.now()
    session = TestSession.objects.create(
        student=student,
        exam=pattern.exam,
        exam_pattern=pattern,
        test_type="full_mock",
        status="active",
        expires_at=now + timedelta(seconds=pattern.total_duration_sec),
    )

    cursor = now
    display_order = 1

    for rule in rules:
        if rule.allow_section_switch:
            # Switchable sections stay available for the full test window.
            section_start = now
            section_end = session.expires_at
        else:
            # Locked sections use strict sectional windows in order.
            section_start = cursor
            section_end = section_start + timedelta(seconds=rule.section_duration_sec)
            cursor = section_end

        SessionSectionState.objects.create(
            test_session=session,
            section=rule.section,
            order_no=rule.order_no,
            started_at=section_start,
            expires_at=section_end,
        )

        selected_questions = list(
            Question.objects.filter(section=rule.section).order_by("?")[:rule.question_count]
        )
        for question in selected_questions:
            SessionQuestion.objects.create(
                test_session=session,
                question=question,
                section=rule.section,
                display_order=display_order,
                marks=question.marks,
                negative_marks=0,
            )
            display_order += 1

    return session


@transaction.atomic
def create_practice_section_session(
    student,
    mode="single_exam",
    section_id=None,
    section_name=None,
    question_count=None,
    duration_sec=None,
):
    now = timezone.now()
    expires_at = now + timedelta(seconds=duration_sec) if duration_sec else None

    if mode == "single_exam":
        section = Section.objects.select_related("exam").filter(id=section_id).first()
        if not section:
            raise ValueError("Section not found")
        questions_qs = Question.objects.filter(section=section)
        exam = section.exam
        limit = question_count or section.total_questions
    else:
        normalized_section_name = " ".join((section_name or "").split())
        questions_qs = Question.objects.select_related("section", "section__exam").filter(
            section__name__iexact=normalized_section_name
        )
        first_question = questions_qs.first()
        if not first_question:
            raise ValueError("No questions available for this section name")
        exam = None
        limit = question_count or 10

    selected_questions = list(questions_qs.order_by("?")[:limit])
    if not selected_questions:
        raise ValueError("No questions available for this section")

    session = TestSession.objects.create(
        student=student,
        exam=exam,
        exam_pattern=None,
        test_type="practice_section",
        status="active",
        expires_at=expires_at,
    )

    section_order = {}
    for question in selected_questions:
        if question.section_id not in section_order:
            section_order[question.section_id] = {
                "section": question.section,
                "order_no": len(section_order) + 1,
            }

    for section_state in section_order.values():
        SessionSectionState.objects.create(
            test_session=session,
            section=section_state["section"],
            order_no=section_state["order_no"],
            started_at=now,
            expires_at=expires_at,
        )

    for idx, question in enumerate(selected_questions, start=1):
        SessionQuestion.objects.create(
            test_session=session,
            question=question,
            section=question.section,
            display_order=idx,
            marks=question.marks,
            negative_marks=0,
        )

    return session


@transaction.atomic
def create_practice_topic_session(
    student,
    mode="single_exam",
    topic_id=None,
    topic_name=None,
    question_count=None,
    duration_sec=None,
):
    if mode == "single_exam":
        questions_qs = Question.objects.select_related("section", "topic").filter(topic_id=topic_id)
        first_question = questions_qs.first()
        if not first_question:
            raise ValueError("Topic not found or no questions available for this topic")
        exam = first_question.section.exam if first_question.section else None
    else:
        normalized_topic_name = " ".join((topic_name or "").split())
        questions_qs = Question.objects.select_related("section", "topic").filter(
            topic__name__iexact=normalized_topic_name
        )
        first_question = questions_qs.first()
        if not first_question:
            raise ValueError("No questions available for this topic name")
        exam = None

    section = first_question.section

    now = timezone.now()
    expires_at = now + timedelta(seconds=duration_sec) if duration_sec else None
    session = TestSession.objects.create(
        student=student,
        exam=exam,
        exam_pattern=None,
        test_type="practice_topic",
        status="active",
        expires_at=expires_at,
    )

    limit = question_count or 10
    selected_questions = list(questions_qs.order_by("?")[:limit])
    if not selected_questions:
        raise ValueError("No questions available for this topic")

    section_order = {}
    for question in selected_questions:
        if question.section_id not in section_order:
            section_order[question.section_id] = {
                "section": question.section,
                "order_no": len(section_order) + 1,
            }

    for section_state in section_order.values():
        SessionSectionState.objects.create(
            test_session=session,
            section=section_state["section"],
            order_no=section_state["order_no"],
            started_at=now,
            expires_at=expires_at,
        )

    for idx, question in enumerate(selected_questions, start=1):
        SessionQuestion.objects.create(
            test_session=session,
            question=question,
            section=question.section,
            display_order=idx,
            marks=question.marks,
            negative_marks=0,
        )

    return session


@transaction.atomic
def create_weak_practice_session(student, questions_per_topic=5):
    weak_performances = TopicPerformance.objects.filter(
        student=student,
        total_attempted__gt=0,
    ).select_related("topic")

    weak_topics = [
        perf.topic
        for perf in weak_performances
        if (perf.total_correct / perf.total_attempted) * 100 < 60
    ]
    if not weak_topics:
        raise ValueError("No weak topics detected")

    latest_session = TestSession.objects.filter(
        student=student,
        exam__isnull=False,
    ).order_by("-started_at").first()
    latest_mock = MockTest.objects.filter(
        student=student,
        exam__isnull=False,
    ).order_by("-created_at").first()
    exam = latest_session.exam if latest_session else (latest_mock.exam if latest_mock else None)

    session = TestSession.objects.create(
        student=student,
        exam=exam,
        exam_pattern=None,
        test_type="weak_practice",
        status="active",
    )

    used_question_ids = set()
    selected_questions = []
    for topic in weak_topics:
        questions = list(
            Question.objects.filter(topic=topic).exclude(id__in=used_question_ids).order_by("?")[:questions_per_topic]
        )
        for q in questions:
            used_question_ids.add(q.id)
            selected_questions.append(q)

    if not selected_questions:
        raise ValueError("No questions available for weak topics")

    section_order = {}
    for question in selected_questions:
        if question.section_id not in section_order:
            section_order[question.section_id] = {
                "section": question.section,
                "order_no": len(section_order) + 1,
            }

    for section_state in section_order.values():
        SessionSectionState.objects.create(
            test_session=session,
            section=section_state["section"],
            order_no=section_state["order_no"],
            started_at=session.started_at,
            expires_at=session.expires_at,
        )

    for index, question in enumerate(selected_questions, start=1):
        SessionQuestion.objects.create(
            test_session=session,
            question=question,
            section=question.section,
            display_order=index,
            marks=question.marks,
            negative_marks=0,
        )

    return session, weak_topics


@transaction.atomic
def save_session_answer(student, test_session_id, question_id, selected_option_id, time_spent_sec=0, marked_for_review=False):
    session = TestSession.objects.filter(
        id=test_session_id,
        student=student,
    ).first()
    if not session:
        raise ValueError("Test session not found")
    if session.status != "active":
        raise ValueError("Test session is not active")
    if session.expires_at and timezone.now() > session.expires_at:
        session.status = "expired"
        session.save(update_fields=["status"])
        raise ValueError("Test session expired")

    session_question = SessionQuestion.objects.select_related("section").filter(
        test_session=session,
        question_id=question_id,
    ).first()
    if not session_question:
        raise ValueError("Question does not belong to this session")

    section_state = SessionSectionState.objects.filter(
        test_session=session,
        section_id=session_question.section_id,
    ).first()
    if not section_state:
        raise ValueError("Section state not found for this question")

    now = timezone.now()
    if section_state.started_at and now < section_state.started_at:
        raise ValueError("This section has not started yet")
    if section_state.expires_at and now > section_state.expires_at:
        raise ValueError("Section time is over")

    if session.exam_pattern_id:
        rule = session.exam_pattern.section_rules.filter(
            section_id=session_question.section_id
        ).first()
        if rule and not rule.allow_section_switch:
            active_state = (
                SessionSectionState.objects.filter(
                    test_session=session,
                    started_at__lte=now,
                    expires_at__gte=now,
                )
                .order_by("order_no")
                .first()
            )
            if not active_state:
                raise ValueError("No active section available right now")
            if active_state.section_id != session_question.section_id:
                raise ValueError("Section switching is disabled for this exam pattern")

    option = Option.objects.filter(id=selected_option_id, question_id=question_id).first()
    if not option:
        raise ValueError("Selected option is invalid for this question")

    answer, created = AttemptAnswer.objects.get_or_create(
        test_session=session,
        question_id=question_id,
        defaults={
            "mock_test": None,
            "selected_option_id": selected_option_id,
            "is_correct": option.is_correct,
            "time_spent_sec": time_spent_sec,
            "marked_for_review": marked_for_review,
        }
    )
    if not created:
        answer.selected_option_id = selected_option_id
        answer.is_correct = option.is_correct
        answer.marked_for_review = marked_for_review
        answer.time_spent_sec = max(answer.time_spent_sec, time_spent_sec)
        answer.save(update_fields=["selected_option_id", "is_correct", "marked_for_review", "time_spent_sec", "answered_at"])

    if not session_question.seen_at:
        session_question.seen_at = now
    session_question.last_visited_at = now
    session_question.is_answered = True
    session_question.is_marked_for_review = marked_for_review
    session_question.time_spent_sec_total = max(session_question.time_spent_sec_total, time_spent_sec)
    session_question.save(
        update_fields=[
            "seen_at",
            "last_visited_at",
            "is_answered",
            "is_marked_for_review",
            "time_spent_sec_total",
        ]
    )

    return answer


@transaction.atomic
def submit_mock_session(student, test_session_id):
    session = TestSession.objects.select_related("exam").filter(
        id=test_session_id,
        student=student,
    ).first()
    if not session:
        raise ValueError("Test session not found")
    if session.status != "active":
        raise ValueError("Test session already submitted or expired")

    if session.expires_at and timezone.now() > session.expires_at:
        session.status = "expired"
        session.submitted_at = timezone.now()
        session.save(update_fields=["status", "submitted_at"])
        raise ValueError("Test session expired")

    session_questions = list(
        SessionQuestion.objects.select_related("question", "section").filter(test_session=session)
    )
    answers_by_qid = {
        a.question_id: a for a in AttemptAnswer.objects.filter(test_session=session)
    }

    total_score = 0
    total_correct = 0
    total_incorrect = 0
    section_data = {}

    for sq in session_questions:
        sid = sq.section_id
        if sid not in section_data:
            section_data[sid] = {
                "section_id": sid,
                "section_name": sq.section.name,
                "score": 0,
                "attempted": 0,
                "correct": 0,
                "incorrect": 0,
                "unattempted": 0,
            }

        answer = answers_by_qid.get(sq.question_id)
        if not answer:
            section_data[sid]["unattempted"] += 1
            continue

        section_data[sid]["attempted"] += 1
        if answer.is_correct:
            total_score += sq.marks
            total_correct += 1
            section_data[sid]["correct"] += 1
            section_data[sid]["score"] += sq.marks
        else:
            total_incorrect += 1
            section_data[sid]["incorrect"] += 1

        topic = sq.question.topic
        if topic:
            performance, _ = TopicPerformance.objects.get_or_create(
                student=student,
                topic=topic,
            )
            performance.total_attempted += 1
            if answer.is_correct:
                performance.total_correct += 1
            performance.save()

    section_states = SessionSectionState.objects.filter(test_session=session)
    for state in section_states:
        stats = section_data.get(state.section_id, None)
        if not stats:
            continue
        state.score = stats["score"]
        state.attempted_count = stats["attempted"]
        state.correct_count = stats["correct"]
        state.incorrect_count = stats["incorrect"]
        state.unattempted_count = stats["unattempted"]
        state.save()

    session.total_score = total_score
    session.status = "submitted"
    session.submitted_at = timezone.now()
    session.save(update_fields=["total_score", "status", "submitted_at"])

    return {
        "test_session_id": session.id,
        "exam": session.exam.title if session.exam else None,
        "status": session.status,
        "score": total_score,
        "total_questions": len(session_questions),
        "correct_answers": total_correct,
        "incorrect_answers": total_incorrect,
        "unattempted": len(session_questions) - (total_correct + total_incorrect),
        "sections": sorted(section_data.values(), key=lambda x: x["section_id"]),
    }


def get_current_section_state(student, test_session_id):
    session = TestSession.objects.select_related("exam_pattern").filter(
        id=test_session_id,
        student=student,
    ).first()
    if not session:
        raise ValueError("Test session not found")
    if session.test_type != "full_mock":
        raise ValueError("Section navigation is only available for full mock sessions")
    if session.status != "active":
        raise ValueError("Test session is not active")

    now = timezone.now()
    current_state = (
        SessionSectionState.objects
        .select_related("section")
        .filter(
            test_session=session,
            started_at__lte=now,
            expires_at__gte=now,
        )
        .order_by("order_no")
        .first()
    )
    if not current_state:
        current_state = (
            SessionSectionState.objects
            .select_related("section")
            .filter(test_session=session, started_at__gt=now)
            .order_by("order_no")
            .first()
        )
        if not current_state:
            raise ValueError("No section available for this session")

    rule = session.exam_pattern.section_rules.filter(section_id=current_state.section_id).first()
    allow_switch = rule.allow_section_switch if rule else True

    return session, current_state, allow_switch


@transaction.atomic
def advance_to_next_section(student, test_session_id):
    session, current_state, allow_switch = get_current_section_state(student, test_session_id)
    if allow_switch:
        raise ValueError("Manual section advance is not required when section switching is enabled")

    next_state = (
        SessionSectionState.objects
        .select_related("section")
        .filter(test_session=session, order_no__gt=current_state.order_no)
        .order_by("order_no")
        .first()
    )
    if not next_state:
        raise ValueError("No next section available")

    now = timezone.now()
    duration = (
        (next_state.expires_at - next_state.started_at)
        if (next_state.started_at and next_state.expires_at)
        else timedelta(seconds=0)
    )

    current_state.expires_at = now
    current_state.save(update_fields=["expires_at"])

    next_state.started_at = now
    next_state.expires_at = now + duration
    next_state.save(update_fields=["started_at", "expires_at"])

    return session, next_state


def build_session_question_palette(student, test_session_id):
    session = TestSession.objects.filter(
        id=test_session_id,
        student=student,
    ).first()
    if not session:
        raise ValueError("Test session not found")

    questions = list(
        SessionQuestion.objects.filter(test_session=session).order_by("display_order")
    )
    palette = []
    counts = {
        "total": len(questions),
        "not_visited": 0,
        "seen": 0,
        "answered": 0,
        "marked": 0,
        "answered_marked": 0,
    }

    for sq in questions:
        seen = bool(sq.seen_at)
        answered = sq.is_answered
        marked = sq.is_marked_for_review

        if answered and marked:
            status_key = "answered_marked"
        elif marked:
            status_key = "marked"
        elif answered:
            status_key = "answered"
        elif seen:
            status_key = "seen"
        else:
            status_key = "not_visited"

        counts[status_key] += 1

        palette.append(
            {
                "question_id": sq.question_id,
                "display_order": sq.display_order,
                "section_id": sq.section_id,
                "status": status_key,
                "seen_at": sq.seen_at,
                "last_visited_at": sq.last_visited_at,
                "time_spent_sec_total": sq.time_spent_sec_total,
            }
        )

    return {
        "test_session_id": session.id,
        "status": session.status,
        "counts": counts,
        "questions": palette,
    }
