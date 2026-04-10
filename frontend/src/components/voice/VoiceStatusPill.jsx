function getRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition;
}

export default function VoiceStatusPill({ voice, pending, draft, onDraftChange, onVoiceStateChange, onError }) {
  async function toggleSpeech() {
    await onVoiceStateChange({ speech_enabled: !voice?.speech_enabled });
  }

  async function startListening() {
    const Recognition = getRecognition();
    if (!Recognition) {
      await onVoiceStateChange({ listening: false });
      onError?.("Voice input is not available in this browser.");
      return;
    }

    const recognition = new Recognition();
    recognition.lang = "en-GB";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = async () => {
      await onVoiceStateChange({ listening: true });
    };

    recognition.onerror = async () => {
      await onVoiceStateChange({ listening: false });
    };

    recognition.onend = async () => {
      await onVoiceStateChange({ listening: false });
    };

    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript;
      if (transcript) {
        onDraftChange(draft ? `${draft}\n${transcript}` : transcript);
      }
    };

    recognition.start();
  }

  function stopSpeaking() {
    window.speechSynthesis?.cancel();
    onVoiceStateChange({ speaking: false });
  }

  return (
    <section className="voice-banner panel">
      <div>
        <p className="eyebrow">Voice Control / Audio Loop</p>
        <h2>Speech Input / Output</h2>
      </div>
      <div className="voice-banner__meta">
        <span>{pending ? "Thinking" : voice?.listening ? "Listening" : voice?.speaking ? "Speaking" : "Standby"}</span>
        <span>{voice?.stt_provider ?? "STT unavailable"}</span>
        <span>{voice?.tts_provider ?? "TTS unavailable"}</span>
      </div>
      <div className="button-row">
        <button type="button" className="panel-button" onClick={startListening}>Mic</button>
        <button type="button" className="panel-button" onClick={toggleSpeech}>
          {voice?.speech_enabled ? "Speech On" : "Speech Off"}
        </button>
        <button type="button" className="panel-button" onClick={stopSpeaking}>Stop Voice</button>
      </div>
    </section>
  );
}
