from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from supabase import create_client, Client
import requests
import json
import re
import os
import traceback

app = FastAPI()

# ============================================================
# UNIVERSAL LLM CONFIG
# ============================================================

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "openai_compatible")

DEFAULT_BASE_URL = os.environ.get(
    "LLM_BASE_URL",
    "https://api.groq.com/openai/v1"
)

DEFAULT_MODEL = os.environ.get(
    "LLM_MODEL",
    "llama-3.3-70b-versatile"
)

LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("GROQ_API_KEY", ""))

# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# SUPABASE
# ============================================================

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL", "https://dnnbctrgaigebonvosda.supabase.co"),
    os.environ.get("SUPABASE_KEY", "")
)

# ============================================================
# HELPERS
# ============================================================

def extract_json(text: str):
    """Safely extract JSON from model output."""
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            raise ValueError("No JSON found")
        return json.loads(match.group())
    except Exception as e:
        print("JSON PARSE ERROR:", text)
        raise e


def get_default_llm_config() -> dict:
    """Return server-side default LLM config."""
    return {
        "provider": DEFAULT_PROVIDER,
        "model": DEFAULT_MODEL,
        "base_url": DEFAULT_BASE_URL,
        "api_key": None
    }


def chat_completion(
    messages: list,
    llm_config: dict,
    temperature: float = 0.7
) -> str:
    """Send a chat request to the configured LLM provider."""

    provider = llm_config.get("provider", DEFAULT_PROVIDER)
    model = llm_config.get("model", DEFAULT_MODEL)
    base_url = llm_config.get("base_url", DEFAULT_BASE_URL)
    api_key = llm_config.get("api_key") or LLM_API_KEY

    # --- OLLAMA ---
    if provider.lower() == "ollama":
        response = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature}
            },
            timeout=300
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    # --- HUGGINGFACE ---
    elif provider.lower() == "huggingface":
        prompt = "\n".join(
            [f"{m['role']}: {m['content']}" for m in messages]
        )
        response = requests.post(
            f"{base_url}/models/{model}",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "inputs": prompt,
                "parameters": {
                    "temperature": temperature,
                    "max_new_tokens": 512
                }
            },
            timeout=300
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data[0]["generated_text"]
        if isinstance(data, dict):
            if "generated_text" in data:
                return data["generated_text"]
            if "error" in data:
                raise Exception(data["error"])
        return str(data)

    # --- OPENAI COMPATIBLE (Groq, Mistral, OpenRouter, etc.) ---
    else:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature
            },
            timeout=300
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

# ============================================================
# REQUEST MODELS
# ============================================================

class LLMConfig(BaseModel):
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key: Optional[str] = None


class InterviewRequest(BaseModel):
    student_email: str
    job_description: str
    question_history: List[Dict] = Field(default_factory=list)
    llm: LLMConfig = LLMConfig()


class AnswerRequest(BaseModel):
    session_id: str
    student_answer: str
    current_question: str

# ============================================================
# JOB DESCRIPTION PARSER
# ============================================================

def parse_job_description(jd_text: str, llm_config: dict):
    prompt = f"""
    Parse this job description and return JSON only.

    JOB DESCRIPTION:
    {jd_text}

    Output format:
    {{
        "role": "exact title",
        "required_skills": ["skill1", "skill2"],
        "experience_level": "entry/mid/senior"
    }}
    """
    content = chat_completion(
        messages=[{"role": "user", "content": prompt}],
        llm_config=llm_config,
        temperature=0.3
    )
    return extract_json(content)

# ============================================================
# GENERATE INTERVIEW QUESTION
# ============================================================

def generate_question(job_context: Dict, llm_config: dict, previous_answers: List = None):
    prompt = f"""
    You are a professional HR interviewer.

    Role: {job_context['role']}
    Required skills: {job_context['required_skills']}

    Generate ONE realistic and challenging interview question.

    Test:
    1. Technical competence
    2. Behavioral depth
    3. Cultural fit

    Previous answers: {previous_answers if previous_answers else "First question"}

    Requirements:
    - Professional tone
    - 1-2 sentences only
    - No bullet points
    """
    return chat_completion(
        messages=[
            {"role": "system", "content": "You are a professional HR interviewer."},
            {"role": "user", "content": prompt}
        ],
        llm_config=llm_config,
        temperature=0.7
    )

# ============================================================
# SCORE ANSWER
# ============================================================

def score_answer(question: str, answer: str, job_context: Dict, llm_config: dict):
    prompt = f"""
    Score this interview answer professionally.

    Job: {job_context['role']}
    Question: {question}
    Answer: {answer}

    Return ONLY valid JSON:
    {{
        "communication": 75,
        "behavioral_evidence": 60,
        "technical_depth": 80,
        "role_alignment": 70,
        "feedback": "1 sentence feedback",
        "weakness_detected": "specific weakness"
    }}
    """
    content = chat_completion(
        messages=[{"role": "user", "content": prompt}],
        llm_config=llm_config,
        temperature=0.3
    )
    return extract_json(content)

# ============================================================
# START INTERVIEW
# ============================================================

@app.post("/api/start_interview")
async def start_interview(request: InterviewRequest):
    try:
        # Use model_dump() for Pydantic v2 compatibility, fallback to dict()
        try:
            llm_config = request.llm.model_dump()
        except AttributeError:
            llm_config = request.llm.dict()

        # Parse JD
        job_context = parse_job_description(request.job_description, llm_config)

        # Get/Create student
        student = supabase.table("students") \
            .select("*") \
            .eq("email", request.student_email) \
            .execute()

        if not student.data:
            created = supabase.table("students") \
                .insert({"email": request.student_email}) \
                .execute()
            student_id = created.data[0]["id"]
        else:
            student_id = student.data[0]["id"]

        # Create session — only store columns that exist in the schema
        session_data = {
            "student_id": student_id,
            "role": job_context["role"],
            "job_description": request.job_description,
            "transcript": []
        }

        # Try to store extended fields (will work if columns exist)
        try:
            session = supabase.table("interview_sessions") \
                .insert({
                    **session_data,
                    "job_context": job_context,
                    "llm_config": llm_config
                }) \
                .execute()
        except Exception:
            # Fallback: store without extended columns
            session = supabase.table("interview_sessions") \
                .insert(session_data) \
                .execute()

        session_id = session.data[0]["id"]

        # Generate first question
        first_question = generate_question(job_context, llm_config)

        return {
            "session_id": session_id,
            "question": first_question,
            "job_context": job_context
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Start interview failed: {str(e)}")

# ============================================================
# SUBMIT ANSWER
# ============================================================

@app.post("/api/submit_answer")
async def submit_answer(raw_request: Request):
    body = await raw_request.json()
    print("RAW BODY:", body)

    request = AnswerRequest(**body)
    try:
        session = supabase.table("interview_sessions") \
            .select("*") \
            .eq("id", request.session_id) \
            .execute()

        if not session.data:
            raise HTTPException(404, "Session not found")

        session_data = session.data[0]

        # Get LLM config — from DB if stored, otherwise use defaults
        llm_config = session_data.get("llm_config") or get_default_llm_config()

        # Get job context — from DB if stored, otherwise re-parse
        job_context = session_data.get("job_context")
        if not job_context:
            job_context = parse_job_description(
                session_data["job_description"],
                llm_config
            )

        transcript = session_data.get("transcript") or []

        # Score answer
        scores = score_answer(
            request.current_question,
            request.student_answer,
            job_context,
            llm_config
        )

        # Append transcript
        transcript.append({
            "question": request.current_question,
            "answer": request.student_answer,
            "scores": scores
        })

        # ==== INTERVIEW COMPLETE (5 questions) ====
        if len(transcript) >= 5:

            avg_scores = {
                "communication":
                    sum(t['scores']['communication'] for t in transcript)
                    / len(transcript),
                "behavioral":
                    sum(t['scores']['behavioral_evidence'] for t in transcript)
                    / len(transcript),
                "technical":
                    sum(t['scores']['technical_depth'] for t in transcript)
                    / len(transcript),
                "alignment":
                    sum(t['scores']['role_alignment'] for t in transcript)
                    / len(transcript)
            }

            overall_score = sum(avg_scores.values()) / 4

            weaknesses = list(set([
                t['scores'].get('weakness_detected')
                for t in transcript
                if t['scores'].get('weakness_detected')
            ]))

            supabase.table("interview_sessions") \
                .update({
                    "overall_score": overall_score,
                    "communication_score": avg_scores["communication"],
                    "behavioral_score": avg_scores["behavioral"],
                    "technical_score": avg_scores["technical"],
                    "alignment_score": avg_scores["alignment"],
                    "transcript": transcript,
                    "weaknesses": weaknesses
                }) \
                .eq("id", request.session_id) \
                .execute()

            report = f"""
INTERVIEW COMPLETE

Overall Score: {overall_score:.1f}/100

Communication: {avg_scores['communication']:.1f}
Behavioral: {avg_scores['behavioral']:.1f}
Technical: {avg_scores['technical']:.1f}
Role Alignment: {avg_scores['alignment']:.1f}

Top Improvement Areas: {', '.join(weaknesses)}
"""

            return {
                "complete": True,
                "report": report,
                "scores": avg_scores,
                "overall_score": overall_score
            }

        # ==== NEXT QUESTION ====
        next_question = generate_question(job_context, llm_config, transcript)

        supabase.table("interview_sessions") \
            .update({"transcript": transcript}) \
            .eq("id", request.session_id) \
            .execute()

        return {
            "complete": False,
            "question": next_question,
            "scores": scores,
            "progress": f"Question {len(transcript)}/5"
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Submit answer failed: {str(e)}")

# ============================================================
# STUDENT PROGRESS
# ============================================================

@app.get("/api/student_progress/{student_email}")
async def get_student_progress(student_email: str):

    student = supabase.table("students") \
        .select("*") \
        .eq("email", student_email) \
        .execute()

    if not student.data:
        raise HTTPException(404, "Student not found")

    student_id = student.data[0]["id"]

    sessions = supabase.table("interview_sessions") \
        .select("*") \
        .eq("student_id", student_id) \
        .order("created_at") \
        .execute()

    scored_sessions = [
        s for s in sessions.data
        if s.get("overall_score") is not None
    ]

    scores_over_time = [
        {"date": s["created_at"], "score": s["overall_score"]}
        for s in scored_sessions
    ]

    all_weaknesses = []
    for s in sessions.data:
        if s.get("weaknesses"):
            all_weaknesses.extend(s["weaknesses"])

    weakness_freq = {}
    for w in all_weaknesses:
        weakness_freq[w] = weakness_freq.get(w, 0) + 1

    average_score = (
        sum(s["overall_score"] for s in scored_sessions)
        / len(scored_sessions)
    ) if scored_sessions else 0

    return {
        "total_sessions": len(sessions.data),
        "average_score": average_score,
        "trend": scores_over_time[-3:],
        "common_weaknesses": sorted(
            weakness_freq.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5],
        "sessions": sessions.data
    }

# ============================================================
# COHORT ANALYTICS
# ============================================================

@app.get("/api/advisor/cohort_analytics")
async def get_cohort_analytics():

    students = supabase.table("students") \
        .select("*, interview_sessions(*)") \
        .execute()

    all_scores = []
    for student in students.data:
        for session in student.get("interview_sessions", []):
            if session.get("overall_score") is not None:
                all_scores.append(session["overall_score"])

    at_risk = []
    for student in students.data:
        sessions = [
            s for s in student.get("interview_sessions", [])
            if s.get("overall_score") is not None
        ]
        if (
            len(sessions) >= 3 and
            all(s["overall_score"] < 50 for s in sessions[-3:])
        ):
            at_risk.append({
                "email": student["email"],
                "latest_score": sessions[-1]["overall_score"],
                "sessions_count": len(sessions)
            })

    return {
        "total_students": len(students.data),
        "total_interviews": len(all_scores),
        "cohort_average": (
            sum(all_scores) / len(all_scores)
        ) if all_scores else 0,
        "students_at_risk": at_risk,
        "pass_rate": (
            len([s for s in all_scores if s >= 70])
            / len(all_scores)
        ) if all_scores else 0
    }

# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
async def root():
    return {
        "status": "running",
        "model": DEFAULT_MODEL,
        "provider": DEFAULT_PROVIDER
    }