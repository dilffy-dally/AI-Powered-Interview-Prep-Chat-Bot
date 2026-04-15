# interviews/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import JDSession, Question, Attempt, FinalReport, VideoSession, VideoAttempt
import json
import requests
import io
import uuid
import re


# ─── Groq API ─────────────────────────────────────────────
GROQ_API_KEY = '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'

def call_ai(prompt, system="You are an expert technical interviewer. Always respond with valid JSON only."):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            timeout=30
        )
        data = response.json()
        if "error" in data:
            raise Exception(f"Groq API error: {data['error']['message']}")
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        raise Exception("AI request timed out. Please try again.")
    except Exception as e:
        raise Exception(f"AI call failed: {str(e)}")


def clean_json(raw):
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()
    json_start = -1
    for i, ch in enumerate(raw):
        if ch in ('{', '['):
            json_start = i
            break
    if json_start > 0:
        raw = raw[json_start:]
    json_end = max(raw.rfind('}'), raw.rfind(']'))
    if json_end != -1:
        raw = raw[:json_end + 1]
    return raw.strip()


# ─── Auth Views ───────────────────────────────────────────

def landing(request):
    if request.user.is_authenticated:
        return redirect('home')  # skip landing if already logged in
    return render(request, 'landing.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        if not username or not password1:
            error = 'Username and password are required.'
        elif password1 != password2:
            error = 'Passwords do not match.'
        elif len(password1) < 6:
            error = 'Password must be at least 6 characters.'
        else:
            from django.contrib.auth.models import User
            if User.objects.filter(username=username).exists():
                error = 'Username already taken.'
            else:
                user = User.objects.create_user(username=username, password=password1)
                login(request, user)
                return redirect('home')
    return render(request, 'register.html', {'error': error})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get('next', 'home'))
        else:
            error = 'Invalid username or password.'
    return render(request, 'login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('landing')


# ─── Core App Views ───────────────────────────────────────

@login_required
def home(request):
    recent_sessions = JDSession.objects.filter(user=request.user).order_by('-created_at')[:3]
    return render(request, 'home.html', {'recent_sessions': recent_sessions})


@login_required
def dashboard(request):
    sessions = JDSession.objects.filter(user=request.user).order_by('-created_at')
    all_attempts = Attempt.objects.filter(session__user=request.user)
    scores = [a.score for a in all_attempts]

    chart_data = []
    for s in sessions[:10]:
        s_attempts = s.attempts.all()
        s_scores = [a.score for a in s_attempts]
        if s_scores:
            chart_data.append({
                'label': s.detected_role or f'Session {s.id}',
                'score': round(sum(s_scores) / len(s_scores), 1),
                'date': s.created_at.strftime('%b %d'),
            })
    chart_data.reverse()

    return render(request, 'dashboard.html', {
        'sessions': sessions,
        'total_sessions': sessions.count(),
        'total_answers': len(scores),
        'avg_score': round(sum(scores) / len(scores), 1) if scores else 0,
        'best_score': max(scores) if scores else 0,
        'chart_data': json.dumps(chart_data),
    })


# ─── Resume Parsing ───────────────────────────────────────

def extract_text_from_pdf(file_bytes):
    text = ""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(io.BytesIO(file_bytes))
        return text.strip()
    except ImportError:
        pass
    return ""


def extract_text_from_docx(file_bytes):
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception:
        return ""


# ─── Analyze JD / Resume ─────────────────────────────────

@login_required
@csrf_exempt
def analyze_jd(request):
    if request.method != 'POST':
        return redirect('home')

    jd_text = request.POST.get('jd_text', '').strip()
    resume_file = request.FILES.get('resume')

    if not resume_file and not jd_text:
        return render(request, 'home.html', {'error': 'Please upload a resume or enter a job description.'})

    if not resume_file and len(jd_text) < 10:
        return render(request, 'home.html', {'error': 'Please enter a job description.'})

    resume_text = ""
    if resume_file:
        try:
            file_bytes = resume_file.read()
            name = resume_file.name.lower()
            if name.endswith('.pdf'):
                resume_text = extract_text_from_pdf(file_bytes)
            elif name.endswith('.docx') or name.endswith('.doc'):
                resume_text = extract_text_from_docx(file_bytes)
            elif name.endswith('.txt'):
                resume_text = file_bytes.decode('utf-8', errors='ignore')
            else:
                resume_text = file_bytes.decode('utf-8', errors='ignore')
        except Exception:
            resume_text = ""

    if resume_text and jd_text:
        prompt = f"""Analyze this job description AND the candidate resume. Return ONLY a JSON object with:
- "role": the job title (string)
- "skills": list of 5-8 key technical skills from the JD (array of strings)
- "questions": list of exactly 8 tailored interview questions (array of strings)

Job Description:
{jd_text}

Candidate Resume:
{resume_text[:3000]}

Return ONLY valid JSON. No explanation."""

    elif resume_text:
        prompt = f"""Analyze the candidate resume below. Return ONLY a JSON object with:
- "role": the most suitable job title based on their background (string)
- "skills": list of 5-8 key skills found in their resume (array of strings)
- "questions": list of exactly 8 tailored interview questions based on their experience (array of strings)

Candidate Resume:
{resume_text[:3000]}

Return ONLY valid JSON. No explanation."""

    else:
        prompt = f"""Analyze this job description and return ONLY a JSON object with:
- "role": the job title (string)
- "skills": list of 5-8 key technical skills (array of strings)
- "questions": list of exactly 8 interview questions tailored to this JD (array of strings)

Job Description:
{jd_text}

Return ONLY valid JSON. No explanation."""

    try:
        result = call_ai(prompt)
        data = json.loads(clean_json(result))

        session = JDSession.objects.create(
            user=request.user,
            jd_text=jd_text,
            detected_role=data.get('role', 'Software Engineer'),
            detected_skills=', '.join(data.get('skills', [])),
            resume_text=resume_text,
        )

        for i, q in enumerate(data.get('questions', [])[:8]):
            Question.objects.create(session=session, question_text=q, order=i + 1)

        return redirect('interview', session_id=session.id)

    except json.JSONDecodeError:
        return render(request, 'home.html', {'error': 'AI returned invalid response. Please try again.'})
    except Exception as e:
        return render(request, 'home.html', {'error': str(e)})


# ─── Interview ────────────────────────────────────────────

@login_required
def interview(request, session_id):
    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    questions = session.questions.all().order_by('order')
    answered_ids = list(session.attempts.values_list('question_id', flat=True))
    return render(request, 'interview.html', {
        'session': session,
        'questions': questions,
        'answered_ids': answered_ids,
        'total': questions.count(),
    })


@login_required
@csrf_exempt
def submit_answer(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    session_id = data.get('session_id')
    question_id = data.get('question_id')
    answer = data.get('answer', '').strip()

    if not answer:
        return JsonResponse({'error': 'Answer cannot be empty'}, status=400)

    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    question = get_object_or_404(Question, id=question_id, session=session)

    existing = Attempt.objects.filter(session=session, question=question).first()
    if existing:
        return JsonResponse({
            'score': existing.score,
            'feedback': existing.ai_feedback,
            'good_points': 'Already answered.',
            'improve': '',
        })

    prompt = f"""You are interviewing a candidate for the role: {session.detected_role}

Question: {question.question_text}
Answer: {answer}

Evaluate the answer and return ONLY a JSON object with these exact keys:
{{
  "score": <integer from 1 to 10>,
  "feedback": "<2-3 sentence constructive feedback>",
  "good_points": "<what they got right>",
  "improve": "<specific improvement suggestion>"
}}

Be honest and specific. Return ONLY valid JSON."""

    try:
        result = call_ai(prompt)
        feedback_data = json.loads(clean_json(result))

        score = int(feedback_data.get('score', 5))
        score = max(1, min(10, score))

        Attempt.objects.create(
            session=session,
            question=question,
            user_answer=answer,
            ai_feedback=feedback_data.get('feedback', ''),
            score=score
        )

        return JsonResponse({
            'score': score,
            'feedback': feedback_data.get('feedback', ''),
            'good_points': feedback_data.get('good_points', ''),
            'improve': feedback_data.get('improve', ''),
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI returned invalid response. Try again.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Final Report ─────────────────────────────────────────

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

    skill_labels = [s.strip() for s in session.detected_skills.split(',') if s.strip()]
    skill_scores = []
    for skill in skill_labels:
        related = [a.score for a in attempts if skill.lower() in a.question.question_text.lower()]
        skill_scores.append(round(sum(related) / len(related), 1) if related else overall)

    return render(request, 'result.html', {
        'session': session,
        'attempts': attempts,
        'report': report,
        'total_questions': session.questions.count(),
        'skill_labels': json.dumps(skill_labels),
        'skill_scores': json.dumps(skill_scores),
    })


# ─── Practice ─────────────────────────────────────────────

@login_required
@csrf_exempt
def practice(request):
    if request.method == 'POST':
        content_type = request.content_type or ''

        if 'application/json' in content_type:
            try:
                body = json.loads(request.body)

                if body.get('eval'):
                    question = body.get('question', '')
                    answer   = body.get('answer', '')
                    domain   = body.get('domain', '')
                    prompt = f"""Evaluate this answer for an interview/practice question.
Domain: {domain}
Question: {question}
Answer: {answer}
Return ONLY JSON: {{"score": <1-10>, "feedback": "2-3 sentences", "good_points": "what was good", "improve": "one specific improvement"}}"""
                    result = call_ai(prompt)
                    return JsonResponse(json.loads(clean_json(result)))

                if body.get('code_eval'):
                    code    = body.get('code', '')
                    title   = body.get('problem_title', '')
                    desc    = body.get('problem_desc', '')
                    lang    = body.get('language', 'python')
                    prompt = f"""Evaluate this {lang} solution for the coding problem: {title}
Problem: {desc}
Code submitted:
{code}

Return ONLY JSON:
{{"score": <1-10>, "correct": <true/false>, "feedback": "2-3 sentence evaluation", "improve": "one specific suggestion"}}"""
                    result = call_ai(prompt)
                    return JsonResponse(json.loads(clean_json(result)))

                if body.get('code_mode'):
                    language   = body.get('language', 'Python')
                    topic      = body.get('topic', 'Arrays')
                    difficulty = body.get('difficulty', 'Easy')
                    prompt = f"""Generate a {difficulty} LeetCode-style coding problem on {topic} in {language}.

Return ONLY a JSON object:
{{
  "title": "Problem title",
  "difficulty": "{difficulty}",
  "description": "Clear problem statement with constraints",
  "example_input": "nums = [2,7,11,15], target = 9",
  "example_output": "[0,1]",
  "hint": "A helpful hint without giving away the solution",
  "starter_code": "Starter code template in {language}"
}}
Return ONLY valid JSON."""
                    result = call_ai(prompt, system="You are an expert competitive programming coach. Return only valid JSON.")
                    data = json.loads(clean_json(result))
                    return JsonResponse(data)

                if body.get('mcq_mode'):
                    subject    = body.get('subject', 'Python')
                    difficulty = body.get('difficulty', 'Easy')
                    count      = int(body.get('count', 20))
                    prompt = f"""Generate exactly {count} MCQ questions on {subject} at {difficulty} difficulty.

Return ONLY a JSON object:
{{"questions": [
  {{"question": "Question text?", "options": ["A) option1", "B) option2", "C) option3", "D) option4"], "answer": "A) option1"}},
  ...
]}}

No extra text. Only valid JSON."""
                    result = call_ai(prompt, system="You are an expert quiz maker. Return only valid JSON.")
                    data = json.loads(clean_json(result))
                    if isinstance(data, list):
                        data = {"questions": data}
                    return JsonResponse(data)

                if body.get('bcom_mode'):
                    track      = body.get('track', 'Excel Formulas')
                    difficulty = body.get('difficulty', 'Beginner')
                    count      = int(body.get('count', 20))
                    prompt = f"""Generate exactly {count} practice questions on the topic: {track} at {difficulty} level for BCom/Finance students.

Return ONLY a JSON object:
{{"questions": ["Question 1?", "Question 2?", ...]}}

No extra text. Only valid JSON."""
                    result = call_ai(prompt, system="You are an expert BCom and finance educator. Return only valid JSON.")
                    data = json.loads(clean_json(result))
                    if isinstance(data, list):
                        data = {"questions": data}
                    return JsonResponse(data)

                if body.get('bba_mode'):
                    track  = body.get('track', 'Marketing Strategy')
                    qtype  = body.get('qtype', 'Written answer')
                    count  = int(body.get('count', 20))
                    prompt = f"""Generate exactly {count} {qtype} practice questions on: {track} for BBA/Marketing students.

Return ONLY a JSON object:
{{"questions": ["Question 1?", "Question 2?", ...]}}

No extra text. Only valid JSON."""
                    result = call_ai(prompt, system="You are an expert BBA and marketing educator. Return only valid JSON.")
                    data = json.loads(clean_json(result))
                    if isinstance(data, list):
                        data = {"questions": data}
                    return JsonResponse(data)

                stream = body.get('stream', 'Engineering')
                domain = body.get('domain', 'DSA & Algorithms')
                qtype  = body.get('qtype', 'Technical')
                count  = int(body.get('count', 20))

                prompt = f"""Generate exactly {count} {qtype} interview questions for someone applying in the {domain} domain within {stream}.

Return ONLY a JSON object:
{{"questions": ["Question 1?", "Question 2?", ...]}}

No extra text, no numbering, just the JSON object."""
                result = call_ai(prompt, system="You are an expert interview coach. Return only valid JSON.")
                data = json.loads(clean_json(result))
                if isinstance(data, list):
                    data = {"questions": data}
                return JsonResponse(data)

            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

    return render(request, 'practice.html')


@login_required
@csrf_exempt
def generate_questions(request):
    return practice(request)

@login_required
@csrf_exempt
def code_practice(request):
    return practice(request)

@login_required
@csrf_exempt
def mcq_quiz(request):
    return practice(request)

@login_required
@csrf_exempt
def bcom_practice(request):
    return practice(request)

@login_required
@csrf_exempt
def bba_practice(request):
    return practice(request)


# ─── Hint ─────────────────────────────────────────────────

@login_required
@csrf_exempt
def get_hint(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    question_id = data.get('question_id')
    session_id = data.get('session_id')

    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    question = get_object_or_404(Question, id=question_id, session=session)

    if question.hint:
        return JsonResponse({'hint': question.hint})

    prompt = f"""You are a senior interviewer for the role: {session.detected_role}

Write a model answer for this interview question that would score 9-10/10.

Question: {question.question_text}

Return ONLY a JSON object:
{{
  "hint": "<A well-structured 3-5 sentence model answer.>",
  "key_points": "<2-3 bullet points separated by |>"
}}

Return ONLY valid JSON."""

    try:
        result = call_ai(prompt)
        hint_data = json.loads(clean_json(result))
        hint_text = hint_data.get('hint', '')
        key_points = hint_data.get('key_points', '')
        if hint_text:
            question.hint = hint_text
            question.save()
        return JsonResponse({'hint': hint_text, 'key_points': key_points})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI returned invalid response.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Retry Answer ─────────────────────────────────────────

@login_required
@csrf_exempt
def retry_answer(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    session_id = data.get('session_id')
    question_id = data.get('question_id')
    retry_ans = data.get('answer', '').strip()

    if not retry_ans or len(retry_ans) < 5:
        return JsonResponse({'error': 'Please provide a proper retry answer.'}, status=400)

    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    question = get_object_or_404(Question, id=question_id, session=session)
    attempt = get_object_or_404(Attempt, session=session, question=question)

    prompt = f"""You are interviewing a candidate for the role: {session.detected_role}

Question: {question.question_text}

Original Answer (Score: {attempt.score}/10):
{attempt.user_answer}

Improved Retry Answer:
{retry_ans}

Compare both answers and evaluate the retry. Return ONLY JSON:
{{
  "score": <integer 1-10>,
  "feedback": "<2-3 sentence feedback on the retry answer>",
  "improvement": "<what improved compared to the original>",
  "still_missing": "<what could still be better>"
}}

Be specific and honest. Return ONLY valid JSON."""

    try:
        result = call_ai(prompt)
        retry_data = json.loads(clean_json(result))
        score = int(retry_data.get('score', 5))
        score = max(1, min(10, score))
        attempt.retry_answer = retry_ans
        attempt.retry_feedback = retry_data.get('feedback', '')
        attempt.retry_score = score
        attempt.save()
        return JsonResponse({
            'score': score,
            'original_score': attempt.score,
            'feedback': retry_data.get('feedback', ''),
            'improvement': retry_data.get('improvement', ''),
            'still_missing': retry_data.get('still_missing', ''),
            'improved': score > attempt.score,
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI returned invalid response.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Follow-up Questions ──────────────────────────────────

@login_required
@csrf_exempt
def followup_question(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    session_id = data.get('session_id')
    question_id = data.get('question_id')
    user_answer = data.get('answer', '').strip()

    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    question = get_object_or_404(Question, id=question_id, session=session)

    prompt = f"""You are a real interviewer for the role: {session.detected_role}

The candidate just answered this interview question:
Question: {question.question_text}
Their Answer: {user_answer}

Generate 2 natural follow-up questions a real interviewer would ask.

Return ONLY a JSON object:
{{
  "followups": ["<follow-up question 1>", "<follow-up question 2>"]
}}

Return ONLY valid JSON."""

    try:
        result = call_ai(prompt)
        fu_data = json.loads(clean_json(result))
        followups = fu_data.get('followups', [])
        if not isinstance(followups, list):
            followups = []
        return JsonResponse({'followups': followups[:2]})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI returned invalid response.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Export PDF ───────────────────────────────────────────

@login_required
def export_report_pdf(request, session_id):
    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    attempts = session.attempts.select_related('question').order_by('question__order')
    scores = [a.score for a in attempts]
    overall = round(sum(scores) / len(scores)) if scores else 0
    report = getattr(session, 'report', None)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

        styles = getSampleStyleSheet()
        purple = colors.HexColor('#7C6FFF')
        dark   = colors.HexColor('#1a1a2e')
        muted  = colors.HexColor('#6b7280')
        green  = colors.HexColor('#2DCE89')
        red    = colors.HexColor('#FF6B8A')

        title_style = ParagraphStyle('Title', parent=styles['Title'],
            fontSize=24, textColor=dark, spaceAfter=6, alignment=TA_CENTER, fontName='Helvetica-Bold')
        subtitle_style = ParagraphStyle('Sub', parent=styles['Normal'],
            fontSize=11, textColor=muted, alignment=TA_CENTER, spaceAfter=20)
        heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
            fontSize=13, textColor=purple, spaceBefore=16, spaceAfter=8, fontName='Helvetica-Bold')
        body_style = ParagraphStyle('Body', parent=styles['Normal'],
            fontSize=10, textColor=dark, spaceAfter=6, leading=15)
        label_style = ParagraphStyle('Label', parent=styles['Normal'],
            fontSize=9, textColor=muted, spaceAfter=2, fontName='Helvetica-Bold')

        story = []
        story.append(Paragraph("PrepAI Interview Report", title_style))
        story.append(Paragraph(f"{session.detected_role}  •  {session.created_at.strftime('%B %d, %Y')}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=purple, spaceAfter=16))

        score_color = green if overall >= 7 else (colors.HexColor('#11CDEF') if overall >= 5 else red)
        summary_data = [
            ['Overall Score', 'Questions Answered', 'Total Questions', 'Candidate'],
            [f"{overall}/10", str(len(scores)), str(session.questions.count()), request.user.username],
        ]
        summary_table = Table(summary_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f3f0ff')),
            ('TEXTCOLOR', (0,0), (-1,0), purple),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTSIZE', (0,1), (-1,1), 14),
            ('FONTNAME', (0,1), (0,1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0,1), (0,1), score_color),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,1), [colors.white]),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e5e7eb')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.4*cm))

        if report and report.summary:
            story.append(Paragraph("Summary", heading_style))
            story.append(Paragraph(report.summary, body_style))

        if session.detected_skills:
            story.append(Paragraph("Skills Assessed", heading_style))
            story.append(Paragraph(session.detected_skills, body_style))

        story.append(Paragraph("Question-by-Question Breakdown", heading_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e5e7eb'), spaceAfter=10))

        for i, attempt in enumerate(attempts):
            s = attempt.score
            s_color = green if s >= 7 else (colors.HexColor('#11CDEF') if s >= 5 else red)

            q_data = [[
                Paragraph(f"Q{i+1}", ParagraphStyle('QNum', parent=styles['Normal'],
                    fontSize=11, textColor=purple, fontName='Helvetica-Bold')),
                Paragraph(attempt.question.question_text, ParagraphStyle('QText', parent=styles['Normal'],
                    fontSize=10, textColor=dark, leading=14)),
                Paragraph(f"{s}/10", ParagraphStyle('Score', parent=styles['Normal'],
                    fontSize=13, textColor=s_color, fontName='Helvetica-Bold', alignment=TA_CENTER)),
            ]]
            q_table = Table(q_data, colWidths=[1*cm, 13*cm, 2.5*cm])
            q_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fafafa')),
                ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e5e7eb')),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
            ]))
            story.append(q_table)

            story.append(Paragraph("Your Answer:", label_style))
            story.append(Paragraph(attempt.user_answer[:500] + ('...' if len(attempt.user_answer) > 500 else ''), body_style))

            if attempt.ai_feedback:
                story.append(Paragraph("AI Feedback:", label_style))
                story.append(Paragraph(attempt.ai_feedback, body_style))

            if attempt.retry_answer:
                story.append(Paragraph(f"Retry Answer (Score: {attempt.retry_score}/10):", label_style))
                story.append(Paragraph(attempt.retry_answer[:400], body_style))
                if attempt.retry_feedback:
                    story.append(Paragraph(attempt.retry_feedback, body_style))

            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#f3f4f6'), spaceAfter=8))

        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"Generated by PrepAI  •  {request.user.username}  •  {session.created_at.strftime('%Y-%m-%d')}",
            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=muted, alignment=TA_CENTER)
        ))

        doc.build(story)
        buffer.seek(0)

        filename = f"PrepAI_Report_{session.detected_role.replace(' ', '_')}_{session.id}.pdf"
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        return render(request, 'report_print.html', {
            'session': session,
            'attempts': attempts,
            'report': report,
            'overall': overall,
            'total_questions': session.questions.count(),
            'user': request.user,
        })


# ─── Share Report ─────────────────────────────────────────

@login_required
def share_report(request, session_id):
    session = get_object_or_404(JDSession, id=session_id, user=request.user)
    if not session.share_token:
        session.share_token = uuid.uuid4().hex
        session.save()
    share_url = request.build_absolute_uri(f'/report/shared/{session.share_token}/')
    return JsonResponse({'url': share_url})


def shared_report(request, token):
    session = get_object_or_404(JDSession, share_token=token)
    attempts = session.attempts.select_related('question').order_by('question__order')
    scores = [a.score for a in attempts]
    overall = round(sum(scores) / len(scores)) if scores else 0
    report = getattr(session, 'report', None)
    skill_labels = [s.strip() for s in session.detected_skills.split(',') if s.strip()]
    skill_scores = []
    for skill in skill_labels:
        related = [a.score for a in attempts if skill.lower() in a.question.question_text.lower()]
        skill_scores.append(round(sum(related) / len(related), 1) if related else overall)
    return render(request, 'result_shared.html', {
        'session': session,
        'attempts': attempts,
        'report': report,
        'total_questions': session.questions.count(),
        'overall': overall,
        'skill_labels': json.dumps(skill_labels),
        'skill_scores': json.dumps(skill_scores),
    })


# ─── Leaderboard ─────────────────────────────────────────

def leaderboard(request):
    from django.db.models import Avg, Count
    from datetime import timedelta, date

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

    streak = 0
    best_streak = 0
    if request.user.is_authenticated:
        dates = list(
            JDSession.objects.filter(user=request.user)
            .values_list('created_at__date', flat=True)
            .distinct().order_by('-created_at__date')
        )
        if dates:
            check = date.today() if dates[0] == date.today() else (date.today() - timedelta(days=1))
            for d in dates:
                if d == check:
                    streak += 1
                    check -= timedelta(days=1)
                else:
                    break
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


# ─── Video Interview ──────────────────────────────────────

QUESTION_COUNTS = {10: 6, 20: 15, 30: 20, 40: 25, 60: 40}


@login_required
def video_setup(request):
    if request.method == 'POST':
        role = request.POST.get('role', '').strip()
        duration = int(request.POST.get('duration', 10))
        if not role:
            return render(request, 'video_setup.html', {'error': 'Please enter a role.'})

        q_count = QUESTION_COUNTS.get(duration, 6)

        prompt = f"""Generate exactly {q_count} interview questions for the role: {role}

Mix: technical skills, problem solving, behavioural, situational questions.
Make them progressively harder.

Return ONLY a JSON array of exactly {q_count} question strings:
["Question 1?", "Question 2?", ...]

No numbering. ONLY valid JSON array."""

        try:
            result = call_ai(prompt, system="You are an expert interviewer. Return only valid JSON arrays.")
            questions = json.loads(clean_json(result))
            if not isinstance(questions, list):
                raise ValueError("Not a list")

            video_session = VideoSession.objects.create(
                user=request.user,
                role=role,
                duration_minutes=duration,
            )

            for i, q in enumerate(questions[:q_count]):
                VideoAttempt.objects.create(
                    video_session=video_session,
                    question_text=q,
                    order=i + 1,
                )

            return redirect('video_interview', session_id=video_session.id)

        except Exception as e:
            return render(request, 'video_setup.html', {'error': f'Failed to generate questions: {str(e)}'})

    return render(request, 'video_setup.html')


@login_required
def video_interview(request, session_id):
    video_session = get_object_or_404(VideoSession, id=session_id, user=request.user)
    attempts = video_session.video_attempts.order_by('order')
    unanswered = attempts.filter(transcript='').first()

    if not unanswered:
        video_session.completed = True
        video_session.save()
        return redirect('video_result', session_id=video_session.id)

    return render(request, 'video_interview.html', {
        'video_session': video_session,
        'current_attempt': unanswered,
        'total': attempts.count(),
        'answered_count': attempts.exclude(transcript='').count(),
        'duration_seconds': video_session.duration_minutes * 60,
    })


@login_required
@csrf_exempt
def video_submit_answer(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    attempt_id = request.POST.get('attempt_id')
    audio_file = request.FILES.get('audio')

    if not attempt_id or not audio_file:
        return JsonResponse({'error': 'Missing attempt_id or audio'}, status=400)

    attempt = get_object_or_404(VideoAttempt, id=attempt_id, video_session__user=request.user)

    try:
        audio_bytes = audio_file.read()
        transcribe_response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"model": "whisper-large-v3-turbo", "response_format": "text"},
            timeout=60,
        )
        transcript = transcribe_response.text.strip() if transcribe_response.status_code == 200 else "[Transcription failed]"
    except Exception:
        transcript = "[Transcription failed]"

    if not transcript or transcript == "[Transcription failed]":
        attempt.transcript = "[No answer recorded]"
        attempt.score = 0
        attempt.ai_feedback = "No answer was recorded or transcribed."
        attempt.save()
        return JsonResponse({
            'transcript': attempt.transcript,
            'score': 0,
            'feedback': attempt.ai_feedback,
            'filler_words': [],
            'communication_tips': '',
        })

    prompt = f"""You are evaluating a spoken interview answer for the role: {attempt.video_session.role}

Question: {attempt.question_text}

Spoken Answer (transcribed):
{transcript}

Evaluate and return ONLY a JSON object:
{{
  "score": <integer 1-10>,
  "feedback": "<2-3 sentence feedback on content quality>",
  "filler_words": ["um", "uh", "like", "you know"],
  "communication_tips": "<1-2 tips on delivery and clarity>",
  "good_points": "<what was strong>",
  "improve": "<specific improvement>"
}}

List only filler words actually found in the transcript. Return ONLY valid JSON."""

    try:
        result = call_ai(prompt)
        eval_data = json.loads(clean_json(result))
        score = max(1, min(10, int(eval_data.get('score', 5))))

        attempt.transcript = transcript
        attempt.score = score
        attempt.ai_feedback = eval_data.get('feedback', '')
        attempt.filler_words = json.dumps(eval_data.get('filler_words', []))
        attempt.communication_tips = eval_data.get('communication_tips', '')
        attempt.save()

        return JsonResponse({
            'transcript': transcript,
            'score': score,
            'feedback': eval_data.get('feedback', ''),
            'filler_words': eval_data.get('filler_words', []),
            'communication_tips': eval_data.get('communication_tips', ''),
            'good_points': eval_data.get('good_points', ''),
            'improve': eval_data.get('improve', ''),
        })

    except Exception as e:
        attempt.transcript = transcript
        attempt.score = 5
        attempt.ai_feedback = "Evaluation failed."
        attempt.save()
        return JsonResponse({
            'transcript': transcript,
            'score': 5,
            'feedback': 'Evaluation failed.',
            'filler_words': [],
            'communication_tips': '',
        })


@login_required
def video_result(request, session_id):
    video_session = get_object_or_404(VideoSession, id=session_id, user=request.user)
    attempts = video_session.video_attempts.order_by('order')
    scores = [a.score for a in attempts if a.score > 0]
    overall = round(sum(scores) / len(scores)) if scores else 0

    attempts_data = []
    for a in attempts:
        try:
            fillers = json.loads(a.filler_words) if a.filler_words else []
        except Exception:
            fillers = []
        attempts_data.append({'attempt': a, 'fillers': fillers})

    return render(request, 'video_result.html', {
        'video_session': video_session,
        'attempts_data': attempts_data,
        'overall': overall,
        'total': attempts.count(),
        'answered': attempts.exclude(transcript='').count(),
    })