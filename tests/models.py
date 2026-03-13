from django.db import models
from users.models import User
from exams.models import Exam, ExamPattern, Section
from questions.models import Question



class MockTest(models.Model):
    TEST_TYPE_CHOICES = (
        ('full', 'Full Test'),
        ('weak_practice', 'Weak Topic Practice'),
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mock_tests',
        db_index=True
    )

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_completed = models.BooleanField(default=False)
    score = models.IntegerField(default=0)

    test_type = models.CharField(
        max_length=20,
        choices=TEST_TYPE_CHOICES,
        default='full'
    )

    class Meta:
        indexes = [
            models.Index(fields=['student', 'created_at']),
        ]


class TestQuestion(models.Model):
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='test_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.mock_test.id} - {self.question.id}"


class AttemptAnswer(models.Model):
    mock_test = models.ForeignKey(
        MockTest,
        on_delete=models.CASCADE,
        related_name='answers',
        db_index=True,
        null=True,
        blank=True
    )
    test_session = models.ForeignKey(
        'TestSession',
        on_delete=models.CASCADE,
        related_name='answers',
        db_index=True,
        null=True,
        blank=True
    )

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        db_index=True
    )

    selected_option_id = models.IntegerField()
    is_correct = models.BooleanField(default=False)
    time_spent_sec = models.IntegerField(default=0)
    marked_for_review = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['mock_test', 'question']),
            models.Index(fields=['test_session', 'question']),
        ]


class TestSession(models.Model):
    TEST_TYPE_CHOICES = (
        ('full_mock', 'Full Mock'),
        ('practice_section', 'Practice Section'),
        ('practice_topic', 'Practice Topic'),
        ('weak_practice', 'Weak Topic Practice'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('submitted', 'Submitted'),
        ('expired', 'Expired'),
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='test_sessions',
        db_index=True
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    exam_pattern = models.ForeignKey(
        ExamPattern,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions'
    )
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    total_score = models.IntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['student', 'started_at']),
        ]


class SessionSectionState(models.Model):
    test_session = models.ForeignKey(
        TestSession,
        on_delete=models.CASCADE,
        related_name='section_states'
    )
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    order_no = models.PositiveIntegerField()
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(default=0)
    attempted_count = models.IntegerField(default=0)
    correct_count = models.IntegerField(default=0)
    incorrect_count = models.IntegerField(default=0)
    unattempted_count = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['test_session', 'order_no'],
                name='unique_order_per_test_session'
            ),
            models.UniqueConstraint(
                fields=['test_session', 'section'],
                name='unique_section_per_test_session'
            ),
        ]
        indexes = [
            models.Index(fields=['test_session', 'order_no']),
        ]


class SessionQuestion(models.Model):
    test_session = models.ForeignKey(
        TestSession,
        on_delete=models.CASCADE,
        related_name='session_questions'
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    display_order = models.PositiveIntegerField()
    marks = models.IntegerField(default=1)
    negative_marks = models.IntegerField(default=0)
    seen_at = models.DateTimeField(null=True, blank=True)
    last_visited_at = models.DateTimeField(null=True, blank=True)
    is_answered = models.BooleanField(default=False)
    is_marked_for_review = models.BooleanField(default=False)
    time_spent_sec_total = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['test_session', 'question'],
                name='unique_question_per_test_session'
            ),
            models.UniqueConstraint(
                fields=['test_session', 'display_order'],
                name='unique_display_order_per_test_session'
            ),
        ]
        indexes = [
            models.Index(fields=['test_session', 'section']),
            models.Index(fields=['test_session', 'display_order']),
        ]
