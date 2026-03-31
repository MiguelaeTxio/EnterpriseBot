/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_live/static/test_live/js/probe.js */
class WalkieTalkie {
    constructor() {
        this.btnInit = document.getElementById('btn-init');
        this.btnTalk = document.getElementById('btn-talk');
        this.led = document.getElementById('status-led');
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.init();
    }

    init() {
        this.btnInit.addEventListener('click', () => this.startSession());
        this.btnTalk.addEventListener('mousedown', () => this.startRecording());
        this.btnTalk.addEventListener('touchstart', (e) => { e.preventDefault(); this.startRecording(); });
        this.btnTalk.addEventListener('mouseup', () => this.stopRecording());
        this.btnTalk.addEventListener('touchend', (e) => { e.preventDefault(); this.stopRecording(); });
    }

    async startSession() {
        this.led.className = 'status-indicator waiting';
        // In a real scenario, this would initiate the websocket. Here we prepare the UI.
        this.led.className = 'status-indicator ready';
        this.btnTalk.disabled = false;
        console.log("Sonda vinculada y lista.");
    }

    async startRecording() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream);
        this.audioChunks = [];
        this.mediaRecorder.ondataavailable = e => this.audioChunks.push(e.data);
        this.mediaRecorder.start();
        this.btnTalk.textContent = "GRABANDO...";
    }

    async stopRecording() {
        this.mediaRecorder.stop();
        this.btnTalk.textContent = "PROCESANDO...";
        this.mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', audioBlob);
            formData.append('session_id', 'WT-' + Date.now());

            const response = await fetch('/test/process-audio/', {
                method: 'POST',
                body: formData,
                headers: { 'X-CSRFToken': this.getCsrfToken() }
            });
            const result = await response.json();
            console.log("Resultado Sonda:", result);
            this.btnTalk.textContent = "HABLAR (Mantener)";
        };
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
}
new WalkieTalkie();
