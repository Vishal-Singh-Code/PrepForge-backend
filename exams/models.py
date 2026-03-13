from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Exam(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='exams')
    title = models.CharField(max_length=255)
    total_duration = models.IntegerField(help_text="Duration in minutes")
    total_marks = models.IntegerField()

    def __str__(self):
        return f"{self.company.name} - {self.title}"


class Section(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=100)
    total_questions = models.IntegerField()
    sectional_duration = models.IntegerField(help_text="Duration in minutes")

    def __str__(self):
        return f"{self.exam.title} - {self.name}"


class ExamPattern(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='patterns')
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=255)
    total_duration_sec = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['exam', 'version'],
                name='unique_exam_pattern_version'
            )
        ]
        indexes = [
            models.Index(fields=['exam', 'is_active']),
        ]

    def __str__(self):
        return f"{self.exam.title} v{self.version} ({self.name})"


class PatternSectionRule(models.Model):
    exam_pattern = models.ForeignKey(
        ExamPattern,
        on_delete=models.CASCADE,
        related_name='section_rules'
    )
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    order_no = models.PositiveIntegerField()
    question_count = models.PositiveIntegerField()
    section_duration_sec = models.PositiveIntegerField()
    allow_section_switch = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['exam_pattern', 'order_no'],
                name='unique_section_order_per_pattern'
            ),
            models.UniqueConstraint(
                fields=['exam_pattern', 'section'],
                name='unique_section_per_pattern'
            ),
        ]
        indexes = [
            models.Index(fields=['exam_pattern', 'order_no']),
        ]

    def __str__(self):
        return f"{self.exam_pattern} - {self.section.name} ({self.order_no})"
