# interviews/admin.py
from django.contrib import admin
from .models import JDSession, Question, Attempt, FinalReport


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ('order', 'question_text', 'hint')


class AttemptInline(admin.TabularInline):
    model = Attempt
    extra = 0
    readonly_fields = ('question', 'user_answer', 'ai_feedback', 'score', 'answered_at')


@admin.register(JDSession)
class JDSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'detected_role', 'created_at', 'question_count', 'attempt_count')
    list_filter = ('created_at', 'detected_role')
    search_fields = ('user__username', 'detected_role', 'detected_skills')
    readonly_fields = ('created_at',)
    inlines = [QuestionInline, AttemptInline]

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'

    def attempt_count(self, obj):
        return obj.attempts.count()
    attempt_count.short_description = 'Answers'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'session', 'question_text')
    list_filter = ('session__detected_role',)
    search_fields = ('question_text',)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'question', 'score', 'answered_at')
    list_filter = ('score', 'answered_at')
    search_fields = ('user_answer', 'ai_feedback', 'session__user__username')
    readonly_fields = ('answered_at',)


@admin.register(FinalReport)
class FinalReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'overall_score', 'created_at')
    list_filter = ('overall_score',)
    search_fields = ('session__user__username', 'session__detected_role')