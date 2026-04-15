// static/interviews/voice.js
// Voice input using Web Speech API — no extra libraries needed

class VoiceInput {
  constructor() {
    this.recognition = null;
    this.isListening = false;
    this.activeTextarea = null;
    this.activeBtn = null;
    this.init();
  }

  init() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('Speech recognition not supported in this browser.');
      document.querySelectorAll('.voice-btn').forEach(btn => btn.style.display = 'none');
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = 'en-US';

    this.recognition.onresult = (event) => {
      if (!this.activeTextarea) return;
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript + ' ';
        } else {
          interim += transcript;
        }
      }

      // Append final transcript to textarea
      if (final) {
        this.activeTextarea.value += final;
        this.activeTextarea.dispatchEvent(new Event('input'));
      }

      // Show interim in placeholder style
      if (interim && this.activeTextarea.dataset.placeholder !== undefined) {
        this.activeTextarea.setAttribute('placeholder', '🎤 ' + interim + '...');
      }
    };

    this.recognition.onerror = (event) => {
      console.error('Speech error:', event.error);
      this.stopListening();
      if (event.error === 'not-allowed') {
        alert('Microphone access denied. Please allow microphone access and try again.');
      }
    };

    this.recognition.onend = () => {
      if (this.isListening) {
        // Auto restart if still in listening mode
        try { this.recognition.start(); } catch(e) {}
      }
    };
  }

  startListening(textarea, btn) {
    if (!this.recognition) return;
    this.activeTextarea = textarea;
    this.activeBtn = btn;
    this.isListening = true;

    try {
      this.recognition.start();
      btn.classList.add('recording');
      btn.innerHTML = `<span class="mic-pulse"></span> Stop`;
      btn.title = 'Click to stop recording';
    } catch(e) {
      console.error('Could not start recognition:', e);
    }
  }

  stopListening() {
    this.isListening = false;
    try { this.recognition.stop(); } catch(e) {}

    if (this.activeBtn) {
      this.activeBtn.classList.remove('recording');
      this.activeBtn.innerHTML = `🎤 Voice`;
      this.activeBtn.title = 'Click to speak your answer';
    }

    if (this.activeTextarea) {
      // Restore original placeholder
      this.activeTextarea.setAttribute('placeholder', 'Type your answer here...');
    }

    this.activeTextarea = null;
    this.activeBtn = null;
  }

  toggle(textarea, btn) {
    if (this.isListening && this.activeTextarea === textarea) {
      this.stopListening();
    } else {
      if (this.isListening) this.stopListening();
      this.startListening(textarea, btn);
    }
  }
}

// Initialize voice input
const voiceInput = new VoiceInput();

// Inject voice buttons next to each answer textarea
document.addEventListener('DOMContentLoaded', () => {
  // Inject CSS
  const style = document.createElement('style');
  style.textContent = `
    .voice-btn {
      background: rgba(108,99,255,0.1);
      border: 1.5px solid rgba(108,99,255,0.3);
      color: #6C63FF;
      padding: 8px 18px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
      font-family: 'Satoshi', sans-serif;
    }
    .voice-btn:hover {
      background: rgba(108,99,255,0.2);
      transform: translateY(-1px);
    }
    .voice-btn.recording {
      background: rgba(255,101,132,0.15);
      border-color: #FF6584;
      color: #FF6584;
      animation: pulse-btn 1.5s infinite;
    }
    @keyframes pulse-btn {
      0%,100% { box-shadow: 0 0 0 0 rgba(255,101,132,0.4); }
      50% { box-shadow: 0 0 0 8px rgba(255,101,132,0); }
    }
    .mic-pulse {
      width: 8px;
      height: 8px;
      background: #FF6584;
      border-radius: 50%;
      animation: blink 0.8s infinite;
      display: inline-block;
    }
    @keyframes blink {
      0%,100% { opacity: 1; }
      50% { opacity: 0.2; }
    }
    .voice-not-supported {
      font-size: 12px;
      color: #9CA3AF;
      padding: 6px 10px;
    }
  `;
  document.head.appendChild(style);

  // Add voice button to each answer textarea
  document.querySelectorAll('textarea.answer').forEach(textarea => {
    const qid = textarea.id.replace('ans-', '');
    const actionsRow = document.getElementById('wc-' + qid)?.parentElement;
    if (!actionsRow) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      const note = document.createElement('span');
      note.className = 'voice-not-supported';
      note.textContent = '🎤 Voice not supported in this browser';
      actionsRow.insertBefore(note, actionsRow.firstChild);
      return;
    }

    const btn = document.createElement('button');
    btn.className = 'voice-btn';
    btn.innerHTML = '🎤 Voice';
    btn.title = 'Click to speak your answer';
    btn.type = 'button';

    btn.addEventListener('click', () => {
      voiceInput.toggle(textarea, btn);
    });

    // Insert before word count
    const wcEl = document.getElementById('wc-' + qid);
    actionsRow.insertBefore(btn, wcEl);
  });
});