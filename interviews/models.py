# interviews/models.py
from django.db import models
from django.contrib.auth.models import User


class JDSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions', null=True, blank=True)
    jd_text = models.TextField()
    detected_role = models.CharField(max_length=200, blank=True)
    detected_skills = models.TextField(blank=True)
    resume_text = models.TextField(blank=True)
    share_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.id} - {self.detected_role} ({self.user})"

    def avg_score(self):
        attempts = self.attempts.all()
        scores = [a.score for a in attempts]
        return round(sum(scores) / len(scores), 1) if scores else 0


class Question(models.Model):
    session = models.ForeignKey(JDSession, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    hint = models.TextField(blank=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:60]}"


class Attempt(models.Model):
    session = models.ForeignKey(JDSession, on_delete=models.CASCADE, related_name='attempts')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='attempts')
    user_answer = models.TextField()
    ai_feedback = models.TextField(blank=True)
    score = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)
    retry_answer = models.TextField(blank=True)
    retry_feedback = models.TextField(blank=True)
    retry_score = models.IntegerField(default=0)

    def __str__(self):
        return f"Attempt - Q{self.question.order} Score:{self.score} in Session {self.session.id}"


class FinalReport(models.Model):
    session = models.OneToOneField(JDSession, on_delete=models.CASCADE, related_name='report')
    overall_score = models.IntegerField(default=0)
    summary = models.TextField(blank=True)
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for Session {self.session.id} - Score: {self.overall_score}"


# ─── Video Interview Models ───────────────────────────────

class VideoSession(models.Model):
    DURATION_CHOICES = [
        (10, '10 Minutes'),
        (20, '20 Minutes'),
        (30, '30 Minutes'),
        (40, '40 Minutes'),
        (60, '1 Hour'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='video_sessions')
    role = models.CharField(max_length=200)
    duration_minutes = models.IntegerField(choices=DURATION_CHOICES, default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"VideoSession {self.id} - {self.role} ({self.duration_minutes}min) - {self.user}"

    def avg_score(self):
        attempts = self.video_attempts.all()
        scores = [a.score for a in attempts if a.score > 0]
        return round(sum(scores) / len(scores), 1) if scores else 0


class VideoAttempt(models.Model):
    video_session = models.ForeignKey(VideoSession, on_delete=models.CASCADE, related_name='video_attempts')
    question_text = models.TextField()
    order = models.IntegerField(default=0)
    transcript = models.TextField(blank=True)
    ai_feedback = models.TextField(blank=True)
    score = models.IntegerField(default=0)
    filler_words = models.TextField(blank=True)
    communication_tips = models.TextField(blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"VideoAttempt Q{self.order} - Session {self.video_session.id} - Score:{self.score}"