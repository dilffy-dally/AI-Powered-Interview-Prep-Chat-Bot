# ─── BUNDLE 2: Add these to interviews/views.py ───────────────────────────────
# 1. Add this import at the top with other imports:
#    import uuid
#
# 2. Add share_token field to JDSession model (see models_addition.py)
#
# 3. Add these 3 views anywhere after final_report view


# ─── Share Report Link ────────────────────────────────────────────────────────

@login_required
def share_report(request, session_id):
    """Generate a shareable token for a report and return the link."""
    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    if not session.share_token:
        session.share_token = uuid.uuid4().hex
        session.save()
    share_url = request.build_absolute_uri(f'/report/shared/{session.share_token}/')
    return JsonResponse({'url': share_url})


def shared_report(request, token):
    """Public view — anyone with the link can view this report."""
    session = get_object_or_404(JDSession, share_token=token)
    attempts = session.attempts.select_related('question').order_by('question__order')
    scores = [a.score for a in attempts]
    overall = round(sum(scores) / len(scores)) if scores else 0
    report = getattr(session, 'report', None)

    # Build skill radar data same as final_report
    skill_labels = [s.strip() for s in session.detected_skills.split(',') if s.strip()]
    skill_scores = []
    for skill in skill_labels:
        skill_lower = skill.lower()
        related = [
            a.score for a in attempts
            if skill_lower in a.question.question_text.lower()
        ]
        skill_scores.append(round(sum(related) / len(related), 1) if related else overall)

    return render(request, 'result_shared.html', {
        'session': session,
        'attempts': attempts,
        'report': report,
        'total_questions': session.questions.count(),
        'overall': overall,
        'skill_labels': json.dumps(skill_labels),
        'skill_scores': json.dumps(skill_scores),
        'is_shared': True,
    })


# ─── Leaderboard ─────────────────────────────────────────────────────────────

def leaderboard(request):
    """Global leaderboard + current user's streak."""
    from django.contrib.auth.models import User
    from django.db.models import Avg, Count
    from datetime import timedelta, date

    # Top users by avg score (min 3 sessions)
    top_users = (
        JDSession.objects
        .values('user__username')
        .annotate(
            avg=Avg('attempts__score'),
            sessions=Count('id', distinct=True),
            answers=Count('attempts'),
        )
        .filter(sessions__gte=1)
        .order_by('-avg')[:10]
    )

    # Current user streak: consecutive days with at least 1 session
    streak = 0
    best_streak = 0
    if request.user.is_authenticated:
        sessions = (
            JDSession.objects
            .filter(user=request.user)
            .values_list('created_at__date', flat=True)
            .distinct()
            .order_by('-created_at__date')
        )
        dates = list(sessions)
        if dates:
            today = date.today()
            # streak from today or yesterday
            check = today if dates[0] == today else (today - timedelta(days=1))
            for d in dates:
                if d == check:
                    streak += 1
                    check -= timedelta(days=1)
                else:
                    break

        # best streak ever
        if dates:
            run = 1
            for i in range(1, len(dates)):
                if (dates[i-1] - dates[i]).days == 1:
                    run += 1
                    best_streak = max(best_streak, run)
                else:
                    run = 1
            best_streak = max(best_streak, streak)

    return render(request, 'leaderboard.html', {
        'top_users': top_users,
        'streak': streak,
        'best_streak': best_streak,
    })


# ─── Updated final_report — add skill radar data ──────────────────────────────
# Replace the existing final_report view with this:

@login_required
def final_report(request, session_id):
    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    attempts = session.attempts.select_related('question').order_by('question__order')
    scores = [a.score for a in attempts]
    overall = round(sum(scores) / len(scores)) if scores else 0

    report, created = FinalReport.objects.get_or_create(
        session=session,
        defaults={
            'overall_score': overall,
            'summary': f"Completed {len(scores)} questions with an average score of {overall}/10."
        }
    )
    if not created and report.overall_score != overall and overall > 0:
        report.overall_score = overall
        report.save()

    # ── Skill Radar Data ──
    skill_labels = [s.strip() for s in session.detected_skills.split(',') if s.strip()]
    skill_scores = []
    for skill in skill_labels:
        skill_lower = skill.lower()
        related = [
            a.score for a in attempts
            if skill_lower in a.question.question_text.lower()
        ]
        skill_scores.append(round(sum(related) / len(related), 1) if related else overall)

    return render(request, 'result.html', {
        'session': session,
        'attempts': attempts,
        'report': report,
        'total_questions': session.questions.count(),
        'skill_labels': json.dumps(skill_labels),
        'skill_scores': json.dumps(skill_scores),
    })