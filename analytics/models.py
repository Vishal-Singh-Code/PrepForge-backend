from django.db import models
from users.models import User
from questions.models import Topic


class TopicPerformance(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        db_index=True
    )

    total_attempted = models.IntegerField(default=0)
    total_correct = models.IntegerField(default=0)

    class Meta:
        unique_together = ('student', 'topic')
        indexes = [
            models.Index(fields=['student', 'topic']),
        ]