# interviews/urls.py  — REPLACE your entire urls.py with this

from django.urls import path
from . import views

urlpatterns = [
    # ── Public ──────────────────────────────────────────
    path('', views.landing, name='landing'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # ── Core App ─────────────────────────────────────────
    path('home/', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analyze/', views.analyze_jd, name='analyze_jd'),
    path('interview/<int:session_id>/', views.interview, name='interview'),
    path('submit-answer/', views.submit_answer, name='submit_answer'),
    path('report/<int:session_id>/', views.final_report, name='final_report'),

    # ── Practice Hub (all modes handled inside one view) ─
    path('practice/', views.practice, name='practice'),
    path('practice/generate/', views.generate_questions, name='generate_questions'),
    path('practice/code/', views.code_practice, name='code_practice'),
    path('practice/mcq/', views.mcq_quiz, name='mcq_quiz'),
    path('practice/bcom/', views.bcom_practice, name='bcom_practice'),
    path('practice/bba/', views.bba_practice, name='bba_practice'),

    # ── Hints / Retry / Follow-up ────────────────────────
    path('get-hint/', views.get_hint, name='get_hint'),
    path('retry-answer/', views.retry_answer, name='retry_answer'),
    path('followup-question/', views.followup_question, name='followup_question'),

    # ── Export & Share ───────────────────────────────────
    path('report/<int:session_id>/pdf/', views.export_report_pdf, name='export_report_pdf'),
    path('report/<int:session_id>/share/', views.share_report, name='share_report'),
    path('report/shared/<str:token>/', views.shared_report, name='shared_report'),

    # ── Leaderboard ──────────────────────────────────────
    path('leaderboard/', views.leaderboard, name='leaderboard'),

    # ── Video Interview ──────────────────────────────────
    path('video/', views.video_setup, name='video_setup'),
    path('video/interview/<int:session_id>/', views.video_interview, name='video_interview'),
    path('video/submit/', views.video_submit_answer, name='video_submit_answer'),
    path('video/result/<int:session_id>/', views.video_result, name='video_result'),
]
