let mediaRecorder;
let audioChunks = [];
let sessionId = null;
let currentQuestion = null;
let isRecording = false;

// Web Speech API for free STT (no API key needed)
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById('status').innerHTML = `📝 You said: "${transcript}"<br>🤖 AI is analyzing...`;
        submitAnswer(transcript);
    };
    
    recognition.onerror = (event) => {
        document.getElementById('status').innerHTML = '❌ Error capturing voice. Please try again.';
        toggleRecording();
    };
}

async function startInterview() {
    const email = document.getElementById('student-email').value;
    const jd = document.getElementById('job-description').value;
    
    if (!email || !jd) {
        alert('Please enter email and job description');
        return;
    }
    
    document.getElementById('setup-card').style.display = 'none';
    document.getElementById('interview-card').style.display = 'block';
    
    const response = await fetch('https://YOUR-BACKEND-URL.onrender.com/api/start_interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_email: email, job_description: jd })
    });
    
    const data = await response.json();
    sessionId = data.session_id;
    currentQuestion = data.question;
    
    document.getElementById('question-display').innerHTML = currentQuestion;
    document.getElementById('status').innerHTML = '🎤 Click the microphone and speak your answer clearly';
    
    // Text-to-speech for the question (free, browser native)
    speak(currentQuestion);
}

function speak(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 1;
    utterance.voice = speechSynthesis.getVoices().find(v => v.lang === 'en-US');
    speechSynthesis.speak(utterance);
}

function toggleRecording() {
    if (!recognition) {
        alert('Your browser does not support speech recognition. Please use Chrome or Edge.');
        return;
    }
    
    if (isRecording) {
        recognition.stop();
        document.getElementById('record-btn').classList.remove('recording');
        document.getElementById('record-btn').innerHTML = '🎤 Click to Speak';
        isRecording = false;
    } else {
        recognition.start();
        document.getElementById('record-btn').classList.add('recording');
        document.getElementById('record-btn').innerHTML = '🔴 Recording... Click to Stop';
        document.getElementById('status').innerHTML = '🎙️ Listening... Speak clearly';
        isRecording = true;
    }
}

async function submitAnswer(answer) {
    const response = await fetch('https://YOUR-BACKEND-URL.onrender.com/api/submit_answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            student_answer: answer,
            current_question: currentQuestion
        })
    });
    
    const data = await response.json();
    
    if (data.complete) {
        // Interview complete - show results
        document.getElementById('interview-card').style.display = 'none';
        document.getElementById('results-card').style.display = 'block';
        document.getElementById('results-content').innerHTML = data.report.replace(/\n/g, '<br>');
        document.getElementById('results-content').style.display = 'block';
        
        // Speak results summary
        speak(`Interview complete. Your overall score is ${data.overall_score.toFixed(1)} out of 100. ${data.scores.feedback || 'Check your results for details.'}`);
    } else {
        // Next question
        currentQuestion = data.question;
        document.getElementById('question-display').innerHTML = currentQuestion;
        
        // Show score for previous answer
        const feedbackDiv = document.getElementById('feedback');
        feedbackDiv.style.display = 'block';
        feedbackDiv.innerHTML = `📈 Previous answer: ${data.scores.communication}% clarity | ${data.scores.technical_depth}% technical<br>💡 ${data.scores.feedback}`;
        
        // Update progress
        const progress = parseInt(data.progress.split(' ')[1].split('/')[0]) / 5 * 100;
        document.getElementById('progress-bar').style.width = `${progress}%`;
        
        document.getElementById('status').innerHTML = '🎤 Click microphone for next answer';
        
        // Speak the next question
        setTimeout(() => speak(currentQuestion), 500);
    }
}