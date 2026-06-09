import { useRef, useState } from "react";
import { synthesizeSpeech, transcribeAudio } from "../../lib/api";
import WaveformVisualizer from "./WaveformVisualizer";

export default function VoiceStatusPill({ voice, pending, draft, onDraftChange, onVoiceStateChange, onError }) {
  const [stream, setStream] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  async function toggleSpeech() {
    await onVoiceStateChange({ speech_enabled: !voice?.speech_enabled });
  }

  async function startListening() {
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      setStream(mic);
      await onVoiceStateChange({ listening: true });

      const preferredTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
      const mimeType = preferredTypes.find((t) => MediaRecorder.isTypeSupported(t)) || "";
      const recorder = mimeType ? new MediaRecorder(mic, { mimeType }) : new MediaRecorder(mic);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        mic.getTracks().forEach((t) => t.stop());
        setStream(null);
        await onVoiceStateChange({ listening: false });
        const actualMime = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: actualMime });
        try {
          const result = await transcribeAudio(blob, actualMime);
          if (result.text) {
            onDraftChange(draft ? `${draft}\n${result.text}` : result.text);
          }
        } catch (err) {
          onError?.(`Transcription failed: ${err.message}`);
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
    } catch (err) {
      await onVoiceStateChange({ listening: false });
      onError?.(`Mic access denied: ${err.message}`);
    }
  }

  function stopListening() {
    mediaRecorderRef.current?.stop();
  }

  async function speakText(text) {
    if (!text) return;
    await onVoiceStateChange({ speaking: true });
    try {
      const buffer = await synthesizeSpeech(text);
      const ctx = new AudioContext();
      const decoded = await ctx.decodeAudioData(buffer);
      const src = ctx.createBufferSource();
      src.buffer = decoded;
      src.connect(ctx.destination);
      src.onended = () => {
        ctx.close();
        onVoiceStateChange({ speaking: false });
      };
      src.start();
    } catch (err) {
      await onVoiceStateChange({ speaking: false });
      onError?.(`TTS failed: ${err.message}`);
    }
  }

  function stopSpeaking() {
    onVoiceStateChange({ speaking: false });
  }

  const isListening = voice?.listening;
  const isSpeaking = voice?.speaking;
  const stateLabel = pending ? "Thinking" : isListening ? "Listening" : isSpeaking ? "Speaking" : "Standby";

  return (
    <section className="voice-banner panel">
      <div>
        <p className="eyebrow">Voice Control / Audio Loop</p>
        <h2>Speech Input / Output</h2>
      </div>
      <div className="voice-banner__meta">
        <span>{stateLabel}</span>
        <span>{voice?.stt_provider ?? "STT unavailable"}</span>
        <span>{voice?.tts_provider ?? "TTS unavailable"}</span>
      </div>
      <WaveformVisualizer stream={stream} active={isListening} />
      <div className="button-row">
        {isListening ? (
          <button type="button" className="panel-button" onClick={stopListening}>Stop</button>
        ) : (
          <button type="button" className="panel-button" onClick={startListening}>Mic</button>
        )}
        <button type="button" className="panel-button" onClick={() => speakText(draft)}>
          Speak
        </button>
        <button type="button" className="panel-button" onClick={toggleSpeech}>
          {voice?.speech_enabled ? "Speech On" : "Speech Off"}
        </button>
        <button type="button" className="panel-button" onClick={stopSpeaking}>Stop Voice</button>
      </div>
    </section>
  );
}
