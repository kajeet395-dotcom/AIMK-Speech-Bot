from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import groq
from supabase import create_client, Client
import json
import re

app = FastAPI()

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Groq (free)
groq_client = groq.Groq(api_key="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")  # Get from console.groq.com

# Initialize Supabase (free)
supabase: Client = create_client(
    "https://dnnbctrgaigebonvosda.supabase.co/rest/v1/",
    "sb_secret_GLuTMuG3THOiISEVRKWPOA_OZpqRzB-"
)

# Interview request model
class InterviewRequest(BaseModel):
    student_email: str
    job_description: str
    question_history: List[Dict] = []

class AnswerRequest(BaseModel):
    session_id: str
    student_answer: str
    current_question: str

# Job parser - extracts role and skills from JD
def parse_job_description(jd_text: str):
    prompt = f"""
    Parse this job description and return JSON:
    {jd_text}
    
    Output format: {{"role": "exact title", "required_skills": ["skill1","skill2"], "experience_level": "entry/mid/senior"}}
    """
    
    response = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    
    return json.loads(response.choices[0].message.content)

# Generate next interview question
def generate_question(job_context: Dict, previous_answers: List = None):
    prompt = f"""
You are a professional interviewer representing a top-tier company.

Role being interviewed for:
{job_context['role']}

Required skills:
{job_context['required_skills']}

Interview history:
{previous_answers if previous_answers else "No previous questions or answers yet."}

Your objective is to conduct a structured, conversational interview that efficiently evaluates the candidate across multiple dimensions while keeping the experience low-pressure, natural, and exploratory.

INTERVIEW DESIGN

- The interview should contain a maximum of 10 questions and preferably conclude within 8-10 questions.
- Ask only ONE question at a time.
- Use previous responses to guide future questions.
- The conversation should feel like a thoughtful discussion rather than a formal interrogation.
- Prioritize depth over breadth when a candidate reveals something interesting or important.
- Maintain a professional, respectful, and curious tone.
- Start the first question with a ward welcome and greeting, showing professional but friendly interest in the candidate's background and motivations.

AREAS TO ASSESS

Across the interview, gather evidence about:

1. Technical competence
   - Core knowledge required for the role
   - Practical application of skills
   - Problem-solving ability
   - Tradeoff analysis and decision-making
   - Real-world experience

2. Work style and execution
   - Ownership
   - Prioritization
   - Collaboration
   - Communication
   - Adaptability
   - Learning approach

3. Team and organizational fit
   - Working with stakeholders
   - Handling ambiguity
   - Receiving and giving feedback
   - Alignment with healthy team behaviors
   - Motivation and career goals

4. Self-awareness
   - Reflection on successes and failures
   - Recognition of limitations
   - Growth mindset
   - Decision rationale

QUESTION GENERATION RULES

When generating the next question:

- Consider the full interview history.
- Avoid repeating topics already covered unless deeper exploration is warranted.
- Prefer questions that reveal multiple dimensions of the candidate at once.
- Ask open-ended questions that encourage detailed responses.
- Avoid yes/no questions.
- Avoid leading questions that imply a desired answer.
- Avoid excessive hypothetical puzzles unless directly relevant to the role.
- Favor questions grounded in the candidate's experience, decisions, reasoning, and judgment.

FOLLOW-UP BEHAVIOR

Occasionally generate follow-up questions based on previous answers.

Good reasons to ask a follow-up include:

- A claim lacks supporting detail.
- The candidate mentions an interesting project or achievement.
- A decision involved meaningful tradeoffs.
- There appears to be a contradiction or inconsistency.
- The candidate uses vague language that could be clarified.
- A deeper understanding would improve assessment accuracy.

Follow-ups should feel naturally curious rather than adversarial.

Examples of useful follow-up patterns:

- "What led you to choose that approach?"
- "What alternatives did you consider?"
- "How did you measure success?"
- "Looking back, would you do anything differently?"
- "Can you walk me through your thinking at the time?"
- "What was the most difficult aspect of that situation?"

Occasional "gotcha" questions are allowed, but they should be constructive and evidence-seeking rather than confrontational. Their purpose is to validate understanding, uncover assumptions, or explore tradeoffs.

INTERVIEW COVERAGE LOGIC

Track which competency areas have already been explored.

Ensure the interview collectively covers:
- Technical expertise
- Execution and delivery
- Collaboration and communication
- Problem solving
- Learning and growth
- Motivation and career alignment
- Team and organizational fit

Do not spend multiple consecutive questions on the same competency unless the candidate's answer justifies deeper exploration.

QUESTION STYLE

Questions should be:

- Professional
- Specific
- Conversational
- Open-ended
- Low-pressure
- Information-dense

The goal is to maximize signal from limited interaction.

OUTPUT RULES

Return ONLY the next interview question.

Do not provide:
- Analysis
- Explanations
- Scores
- Evaluation
- Competency labels
- Multiple questions at once

Generate exactly one question that best advances the interview given the current conversation state.
"""
    
    response = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "system", "content": "You are a professional HR interviewer."},
                  {"role": "user", "content": prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content

# Score the answer (professional rubric)
def score_answer(question: str, answer: str, job_context: Dict):
    prompt = f"""
You are an expert hiring assessor and interview evaluator.

JOB CONTEXT

Role:
{job_context['role']}

Required Skills:
{job_context['required_skills']}

Resume:
Currently Unavailable

Interview History:
Currently Unavailable (Ignore the firstt question greetings, generate all questions assuming the candidate has answered all previous questions)

Current Question:
{question}

Candidate Answer:
{answer}

OBJECTIVE

Evaluate the candidate's answer in the context of:

- The target role
- The required skills
- Their resume and prior experience
- Their previous interview responses
- Evidence demonstrated throughout the interview

Do not evaluate based on keywords alone.

Reward:
- Clear reasoning
- Demonstrated experience
- Good judgment
- Self-awareness
- Practical problem solving
- Communication effectiveness
- Relevant expertise

Avoid rewarding:
- Empty buzzwords
- Unsupported claims
- Excessive vagueness
- Overconfidence without evidence

SCORING FRAMEWORK

Score every category from 0-100.

COMMUNICATION

Evaluate:

- Confidence
- Clarity
- Grammar and language quality
- Complexity of thought
- Ease of understanding
- Structure and organization
- Ability to explain concepts
- Demonstration of foundational knowledge

TECHNICAL_COMPETENCE

Evaluate:

- Technical accuracy
- Depth of knowledge
- Practical application
- Tradeoff awareness
- Problem-solving ability
- Role-specific expertise

EXECUTION_AND_OWNERSHIP

Evaluate:

- Initiative
- Accountability
- Decision making
- Prioritization
- Delivery mindset

COLLABORATION

Evaluate:

- Teamwork
- Stakeholder management
- Communication with others
- Conflict handling
- Cross-functional effectiveness

ADAPTABILITY_AND_LEARNING

Evaluate:

- Curiosity
- Growth mindset
- Ability to learn
- Handling ambiguity
- Incorporating feedback

ROLE_ALIGNMENT

Evaluate:

- Fit for the target role
- Fit for seniority level
- Relevance of experience
- Alignment with required skills

RESUME_ALIGNMENT

Evaluate:

- Consistency with resume claims
- Evidence supporting resume experience
- Credibility of stated achievements
- Match between interview performance and resume

PSYCHOLOGICAL PROFILE

Infer likely tendencies from the answer and interview context.

Estimate:

- Communication style
- Decision-making style
- Working style
- Leadership tendency
- Risk tolerance
- Analytical vs intuitive orientation
- Collaboration preference

Choose the closest personality archetype:

- Builder
- Operator
- Analyst
- Strategist
- Innovator
- Collaborator
- Specialist
- Generalist

Provide:
- Confidence score for the archetype
- Role fit assessment
- Strengths implied by the profile
- Potential risks implied by the profile

RADAR CHART FRAMEWORK

Always use the exact same dimensions for consistency.

Radar dimensions:

1. Communication
2. Technical Competence
3. Problem Solving
4. Ownership
5. Collaboration
6. Adaptability
7. Leadership Potential
8. Role Alignment

SCORING GUIDELINES

90-100 = Exceptional evidence
80-89 = Strong evidence
70-79 = Solid evidence
60-69 = Adequate evidence
50-59 = Weak evidence
0-49 = Insufficient evidence

OUTPUT

Return ONLY valid JSON.

{
    "scores": {
        "communication": 0,
        "technical_competence": 0,
        "problem_solving": 0,
        "execution_and_ownership": 0,
        "collaboration": 0,
        "adaptability_and_learning": 0,
        "leadership_potential": 0,
        "role_alignment": 0,
        "resume_alignment": 0
    },

    "psychological_profile": {
        "archetype": "",
        "confidence": 0,
        "communication_style": "",
        "decision_style": "",
        "working_style": "",
        "leadership_tendency": "",
        "risk_tolerance": "",
        "analytical_vs_intuitive": "",
        "role_fit_assessment": "",
        "strengths": [],
        "risks": []
    },

    "evidence_summary": {
        "strongest_signals": [],
        "weakest_signals": [],
        "missing_evidence": []
    },

    "feedback": {
        "summary": "",
        "top_strength": "",
        "top_improvement_area": "",
        "next_focus_area": ""
    },

    "radar_chart": {
        "labels": [
            "Communication",
            "Technical Competence",
            "Problem Solving",
            "Ownership",
            "Collaboration",
            "Adaptability",
            "Leadership Potential",
            "Role Alignment"
        ],
        "values": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0
        ]
    }
}
"""
    
    response = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    
    return json.loads(response.choices[0].message.content)

# API Endpoints
@app.post("/api/start_interview")
async def start_interview(request: InterviewRequest):
    # Parse job description
    job_context = parse_job_description(request.job_description)
    
    # Get or create student
    student = supabase.table("students").select("*").eq("email", request.student_email).execute()
    if not student.data:
        student = supabase.table("students").insert({"email": request.student_email}).execute()
        student_id = student.data[0]['id']
    else:
        student_id = student.data[0]['id']
    
    # Create session
    session = supabase.table("interview_sessions").insert({
        "student_id": student_id,
        "role": job_context['role'],
        "job_description": request.job_description
    }).execute()
    
    session_id = session.data[0]['id']
    
    # Generate first question
    first_question = generate_question(job_context)
    
    return {
        "session_id": session_id,
        "question": first_question,
        "job_context": job_context
    }

@app.post("/api/submit_answer")
async def submit_answer(request: AnswerRequest):
    # Get session data
    session = supabase.table("interview_sessions").select("*").eq("id", request.session_id).execute()
    job_description = session.data[0]['job_description']
    job_context = parse_job_description(job_description)
    
    # Score the answer
    scores = score_answer(request.current_question, request.student_answer, job_context)
    
    # Update session with scores (running average)
    # For MVP, store individual scores
    
    # Generate next question (or end if 5+ questions)
    transcript = session.data[0].get('transcript', [])
    transcript.append({
        "question": request.current_question,
        "answer": request.student_answer,
        "scores": scores
    })
    
    if len(transcript) >= 5:  # 5 questions max for MVP
        # Calculate final scores
        avg_scores = {
            "communication": sum(t['scores']['communication'] for t in transcript) / len(transcript),
            "behavioral": sum(t['scores']['behavioral_evidence'] for t in transcript) / len(transcript),
            "technical": sum(t['scores']['technical_depth'] for t in transcript) / len(transcript),
            "alignment": sum(t['scores']['role_alignment'] for t in transcript) / len(transcript)
        }
        
        overall_score = sum(avg_scores.values()) / 4
        
        # Update session with final scores
        supabase.table("interview_sessions").update({
            "overall_score": overall_score,
            "communication_score": avg_scores['communication'],
            "behavioral_score": avg_scores['behavioral'],
            "technical_score": avg_scores['technical'],
            "alignment_score": avg_scores['alignment'],
            "transcript": transcript,
            "weaknesses": [t['scores']['weakness_detected'] for t in transcript if t['scores'].get('weakness_detected')]
        }).eq("id", request.session_id).execute()
        
        # Generate final report
        report = f"""
        INTERVIEW COMPLETE - FINAL REPORT
        Overall Score: {overall_score:.1f}/100
        Communication: {avg_scores['communication']:.1f}
        Behavioral (STAR): {avg_scores['behavioral']:.1f}
        Technical Depth: {avg_scores['technical']:.1f}
        Role Alignment: {avg_scores['alignment']:.1f}
        
        Top Improvement Areas: {', '.join(set([t['scores']['weakness_detected'] for t in transcript if t['scores'].get('weakness_detected')]))}
        """
        
        return {
            "complete": True,
            "report": report,
            "scores": avg_scores,
            "overall_score": overall_score
        }
    else:
        # Generate next question
        next_question = generate_question(job_context, transcript)
        
        # Update transcript
        supabase.table("interview_sessions").update({
            "transcript": transcript
        }).eq("id", request.session_id).execute()
        
        return {
            "complete": False,
            "question": next_question,
            "scores": scores,
            "progress": f"Question {len(transcript)}/5"
        }

@app.get("/api/student_progress/{student_email}")
async def get_student_progress(student_email: str):
    # Get student
    student = supabase.table("students").select("*").eq("email", student_email).execute()
    if not student.data:
        raise HTTPException(404, "Student not found")
    
    student_id = student.data[0]['id']
    
    # Get all sessions
    sessions = supabase.table("interview_sessions").select("*").eq("student_id", student_id).order("created_at").execute()
    
    # Calculate trends
    scores_over_time = [
        {"date": s['created_at'], "score": s['overall_score']}
        for s in sessions.data if s['overall_score']
    ]
    
    # Get weaknesses
    all_weaknesses = []
    for s in sessions.data:
        if s.get('weaknesses'):
            all_weaknesses.extend(s['weaknesses'])
    
    weakness_freq = {}
    for w in all_weaknesses:
        weakness_freq[w] = weakness_freq.get(w, 0) + 1
    
    return {
        "total_sessions": len(sessions.data),
        "average_score": sum(s['overall_score'] for s in sessions.data if s['overall_score']) / len([s for s in sessions.data if s['overall_score']]) if sessions.data else 0,
        "trend": scores_over_time[-3:] if len(scores_over_time) >= 3 else scores_over_time,
        "common_weaknesses": sorted(weakness_freq.items(), key=lambda x: x[1], reverse=True)[:5],
        "sessions": sessions.data
    }

@app.get("/api/advisor/cohort_analytics")
async def get_cohort_analytics():
    # Get all students with sessions
    students = supabase.table("students").select("*, interview_sessions(*)").execute()
    
    # Calculate aggregate metrics
    all_scores = []
    for student in students.data:
        for session in student.get('interview_sessions', []):
            if session.get('overall_score'):
                all_scores.append(session['overall_score'])
    
    # Students needing intervention (below 50 after 3+ attempts)
    at_risk = []
    for student in students.data:
        sessions = [s for s in student.get('interview_sessions', []) if s.get('overall_score')]
        if len(sessions) >= 3 and all(s['overall_score'] < 50 for s in sessions[-3:]):
            at_risk.append({
                "email": student['email'],
                "latest_score": sessions[-1]['overall_score'],
                "sessions_count": len(sessions)
            })
    
    return {
        "total_students": len(students.data),
        "total_interviews": len(all_scores),
        "cohort_average": sum(all_scores) / len(all_scores) if all_scores else 0,
        "students_at_risk": at_risk,
        "pass_rate": len([s for s in all_scores if s >= 70]) / len(all_scores) if all_scores else 0
    }
