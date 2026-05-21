let sessionId = null;
let currentQuestion = null;
let isRecording = false;

// Backend API URL — your Render backend
const BACKEND_URL = 'https://aimk-speech-bot-1.onrender.com';

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
    document.getElementById('status').innerHTML = '🔄 Connecting to AI server...';
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/start_interview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_email: email, job_description: jd })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        sessionId = data.session_id;
        currentQuestion = data.question;
        
        document.getElementById('question-display').innerHTML = currentQuestion;
        document.getElementById('status').innerHTML = '🎤 Click the microphone and speak your answer';
        speak(currentQuestion);
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('status').innerHTML = `❌ Cannot connect to backend. Error: ${error.message}`;
        alert(`Backend connection failed.\n\nMake sure your Render backend is running at:\n${BACKEND_URL}\n\nError: ${error.message}`);
    }
}

function speak(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        window.speechSynthesis.speak(utterance);
    }
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
    try {
        const response = await fetch(`${BACKEND_URL}/api/submit_answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                student_answer: answer,
                current_question: currentQuestion
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.complete) {
            document.getElementById('interview-card').style.display = 'none';
            document.getElementById('results-card').style.display = 'block';
            document.getElementById('results-content').innerHTML = data.report.replace(/\n/g, '<br>');
            document.getElementById('results-content').style.display = 'block';
            speak(`Interview complete. Your overall score is ${data.overall_score.toFixed(1)} out of 100.`);
        } else {
            currentQuestion = data.question;
            document.getElementById('question-display').innerHTML = currentQuestion;
            
            const feedbackDiv = document.getElementById('feedback');
            feedbackDiv.style.display = 'block';
            feedbackDiv.innerHTML = `📈 Previous answer: ${data.scores.communication}% clarity | ${data.scores.technical_depth}% technical<br>💡 ${data.scores.feedback}`;
            
            const progress = parseInt(data.progress.split(' ')[1].split('/')[0]) / 5 * 100;
            document.getElementById('progress-bar').style.width = `${progress}%`;
            
            document.getElementById('status').innerHTML = '🎤 Click microphone for next answer';
            setTimeout(() => speak(currentQuestion), 500);
        }
    } catch (error) {
        console.error('Submit error:', error);
        document.getElementById('status').innerHTML = `❌ Error submitting answer: ${error.message}`;
    }
}
