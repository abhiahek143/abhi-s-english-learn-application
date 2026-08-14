import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, Volume2, LayoutDashboard, MessageSquare, RotateCcw, Loader2, AlertCircle } from 'lucide-react';

const USER_ID = 'abhi';

const ERROR_TYPES = {
  grammar: { label: 'Grammar', color: '#C4453B' },
  tense: { label: 'Tense', color: '#B8763A' },
  vocabulary: { label: 'Vocabulary', color: '#7A5FB8' },
  pronunciation: { label: 'Pronunciation', color: '#3D7EA6' },
  other: { label: 'Other', color: '#6B6558' },
};

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function MarkedText({ original, mistakes }) {
  let parts = [original];
  mistakes.forEach((m) => {
    const next = [];
    parts.forEach((part) => {
      if (typeof part !== 'string' || !m.incorrect_phrase) {
        next.push(part);
        return;
      }
      const idx = part.toLowerCase().indexOf(m.incorrect_phrase.toLowerCase());
      if (idx === -1) {
        next.push(part);
        return;
      }
      next.push(part.slice(0, idx));
      next.push(
        <span key={Math.random()} className="asl-mistake-tag">
          {part.slice(idx, idx + m.incorrect_phrase.length)}
        </span>
      );
      next.push(part.slice(idx + m.incorrect_phrase.length));
    });
    parts = next;
  });
  return <span>{parts}</span>;
}

export default function App() {
  const [view, setView] = useState('practice');
  const [messages, setMessages] = useState([]);
  const [mistakes, setMistakes] = useState([]);
  const [stats, setStats] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [mode, setMode] = useState('daily');
  const [micSupported, setMicSupported] = useState(true);
  const [error, setError] = useState(null);
  const [ttsAvailable, setTtsAvailable] = useState(null);
  const [ttsChecking, setTtsChecking] = useState(false);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordingStartRef = useRef(0);
  const repeatTargetRef = useRef(null);
  const chatEndRef = useRef(null);
  const audioRef = useRef(null);

  // --- MediaRecorder → Groq Whisper STT ---
  useEffect(() => {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setMicSupported(false);
      return;
    }
    recognitionRef.current = null;
  }, []);

  const loadMistakes = async () => {
    try {
      const res = await fetch(`/api/mistakes?user_id=${USER_ID}`);
      if (!res.ok) throw new Error('failed to load mistakes');
      const data = await res.json();
      setMistakes(data.mistakes || []);
      setStats(data.stats || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadMistakes();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  useEffect(() => {
    // check TTS availability on load
    checkTtsStatus();
  }, []);

  const checkTtsStatus = async () => {
    setTtsChecking(true);
    try {
      const res = await fetch('/api/tts-status');
      const j = await res.json();
      setTtsAvailable(Boolean(j.available));
    } catch (e) {
      console.error(e);
      setTtsAvailable(false);
    } finally {
      setTtsChecking(false);
    }
  };

  const enableHumanVoice = () => {
    // open Groq Console Orpheus page for user to accept terms, then poll
    window.open('https://console.groq.com/models/canopylabs/orpheus-v1-english', '_blank');
    setTtsChecking(true);
    const start = Date.now();
    const poll = async () => {
      try {
        const res = await fetch('/api/tts-status');
        const j = await res.json();
        if (j.available) {
          setTtsAvailable(true);
          setTtsChecking(false);
          return;
        }
      } catch (_) {}
      if (Date.now() - start < 60000) {
        setTimeout(poll, 3000);
      } else {
        setTtsChecking(false);
      }
    };
    setTimeout(poll, 2000);
  };

  const handleUserSpeech = async (transcript, duration_seconds = 0) => {
    if (!transcript || !transcript.trim()) return;
    setError(null);
    const userMsg = { id: uid(), role: 'user', text: transcript };
    setMessages((prev) => [...prev, userMsg]);
    setIsProcessing(true);
    try {
      const res = await fetch('/api/correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: transcript, user_id: USER_ID, mode, duration_seconds }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Server error ${res.status}`);
      }
      const result = await res.json();
      const aiMsg = {
        id: uid(),
        role: 'ai',
        original: transcript,
        reply: result.reply || '',
        corrected: result.corrected,
        mistakeList: result.mistakes || [],
        feedback: result.feedback || '',
      };
      setMessages((prev) => [...prev, aiMsg]);
      speak(result.reply || result.corrected);
      if (result.mistakes && result.mistakes.length > 0) {
        loadMistakes();
      }
    } catch (e) {
      setError(e.message || 'Could not reach the coach. Try again.');
      setMessages((prev) => [...prev, { id: uid(), role: 'error', text: 'Something went wrong grading that sentence.' }]);
    } finally {
      setIsProcessing(false);
    }
  };

  const toggleRecording = async () => {
    if (!micSupported) return;
    setError(null);
    if (isRecording) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      mr.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) audioChunksRef.current.push(ev.data);
      };
      mr.onstart = () => {
        recordingStartRef.current = Date.now();
        setIsRecording(true);
      };
      mr.onstop = async () => {
        try {
          const stopTime = Date.now();
          const duration_seconds = Math.round((stopTime - recordingStartRef.current) / 1000);
          const blob = new Blob(audioChunksRef.current, { type: audioChunksRef.current[0]?.type || 'audio/webm' });
          setIsProcessing(true);
          if (repeatTargetRef.current) {
            try {
              const fd = new FormData();
              fd.append('file', blob, 'speech.webm');
              fd.append('expected', repeatTargetRef.current);
              fd.append('user_id', USER_ID);
              fd.append('mode', mode);
              const r = await fetch('/api/repeat', { method: 'POST', body: fd });
              if (!r.ok) {
                const body = await r.json().catch(() => ({}));
                throw new Error(body.detail || `Repeat eval failed ${r.status}`);
              }
              const jr = await r.json();
              const userTranscript = jr.transcript || '';
              setMessages((prev) => [...prev, { id: uid(), role: 'user', text: userTranscript }]);
              setMessages((prev) => [...prev, { id: uid(), role: 'ai', reply: `Repeat score ${jr.score}%`, corrected: repeatTargetRef.current, mistakeList: [], feedback: jr.feedback }]);
            } finally {
              repeatTargetRef.current = null;
            }
          } else {
            const resp = await fetch('/api/transcribe', {
              method: 'POST',
              headers: { 'Content-Type': blob.type || 'audio/webm' },
              body: blob,
            });
            if (!resp.ok) {
              const body = await resp.json().catch(() => ({}));
              throw new Error(body.detail || `Transcription failed ${resp.status}`);
            }
            const json = await resp.json();
            const transcript = json.text || '';
            await handleUserSpeech(transcript, duration_seconds);
          }
        } catch (e) {
          console.error(e);
          setError(e.message || 'Transcription failed');
        } finally {
          setIsProcessing(false);
          try { mediaRecorderRef.current?.stream?.getTracks()?.forEach(t => t.stop()); } catch (_) {}
        }
      };

      mr.start();
      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') mediaRecorderRef.current.stop();
      }, 12000);
    } catch (e) {
      console.error(e);
      setError('Microphone permission denied or not available');
    }
  };

  const browserSpeak = (text) => {
    if (!window.speechSynthesis || !text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'en-US';
    utter.rate = 0.92;
    utter.pitch = 1.02;
    const voices = window.speechSynthesis.getVoices();
    const enVoice = voices.find((v) => /samantha|natural|premium|enhanced/i.test(v.name))
      || voices.find((v) => v.lang === 'en-US')
      || voices.find((v) => v.lang && v.lang.startsWith('en'));
    if (enVoice) utter.voice = enVoice;
    window.speechSynthesis.speak(utter);
  };

  // --- Groq Orpheus text-to-speech, with browser TTS fallback ---
  const speak = async (text) => {
    const clean = (text || '').trim();
    if (!clean) return;
    try {
      // If TTS explicitly marked unavailable, use browser TTS directly.
      if (ttsAvailable === false) {
        browserSpeak(clean);
        return;
      }

      window.speechSynthesis?.cancel();
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const res = await fetch('/api/speech', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || 'Groq speech failed');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => URL.revokeObjectURL(url);
      audio.onerror = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (e) {
      console.error(e);
      if (/terms acceptance|model_terms_required/i.test(e.message || '')) {
        setError('Accept Orpheus TTS terms in Groq Console to enable human voice. Browser voice is playing for now.');
      }
      browserSpeak(clean);
    }
  };

  const resetPractice = () => setMessages([]);

  const clearMistakes = async () => {
    try {
      await fetch(`/api/mistakes?user_id=${USER_ID}`, { method: 'DELETE' });
      setMistakes([]);
      setStats([]);
    } catch (e) {
      console.error(e);
    }
  };

  // --- Repeat-after-me helper: play corrected text then prompt user to record a repeat ---
  const handleRepeat = async (corrected) => {
    if (!corrected) return;
    try {
      repeatTargetRef.current = corrected;
      await speak(corrected);
      setTimeout(() => {
        toggleRecording();
      }, 450);
    } catch (e) {
      console.error(e);
    }
  };

  const errorCounts = stats.reduce((acc, s) => {
    acc[s.error_type] = s.count;
    return acc;
  }, {});
  const maxCount = Math.max(1, ...Object.values(errorCounts));

  return (
    <div className="asl-root">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500..700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
        .asl-root {
          --bg: #101B2B; --bg-soft: #16233A; --paper: #F7F3EA; --paper-line: #E4DCC8;
          --ink: #221D14; --ink-soft: #6B6558; --accent: #E8A33D; --accent-soft: rgba(232,163,61,0.15);
          --mistake: #C4453B; --mistake-soft: rgba(196,69,59,0.12);
          --correct: #4B8B6F; --correct-soft: rgba(75,139,111,0.14); --cream-text: #F2EFE6;
          font-family: 'Inter', sans-serif; background: var(--bg); color: var(--cream-text);
          min-height: 100vh; width: 100%; display: flex; flex-direction: column; box-sizing: border-box;
        }
        .asl-root * { box-sizing: border-box; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .asl-header { padding: 22px 20px 14px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(242,239,230,0.08); flex-wrap: wrap; gap: 10px; }
        .asl-logo { font-family: 'Fraunces', serif; font-size: 21px; font-weight: 600; letter-spacing: -0.01em; }
        .asl-logo span { color: var(--accent); }
        .asl-tabs { display: flex; gap: 6px; background: var(--bg-soft); padding: 4px; border-radius: 10px; }
        .asl-tab { border: none; background: transparent; color: var(--cream-text); opacity: 0.6; padding: 8px 14px; border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; font-family: 'Inter', sans-serif; transition: all 0.15s ease; }
        .asl-tab.active { background: var(--accent); color: #1A1206; opacity: 1; }
        .asl-body { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 18px 20px 20px; }
        .asl-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; opacity: 0.55; gap: 10px; padding: 30px; }
        .asl-chat { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; padding: 4px 2px 10px; }
        .asl-bubble-row { display: flex; }
        .asl-bubble-row.user { justify-content: flex-end; }
        .asl-bubble-row.ai { justify-content: flex-start; }
        .asl-bubble { max-width: 78%; padding: 12px 14px; border-radius: 14px; font-size: 14.5px; line-height: 1.5; }
        .asl-bubble.user-bubble { background: var(--bg-soft); border: 1px solid rgba(242,239,230,0.1); border-bottom-right-radius: 4px; }
        .asl-bubble.ai-bubble { background: var(--paper); color: var(--ink); border-bottom-left-radius: 4px; }
        .asl-mistake-tag { text-decoration: line-through; color: var(--mistake); background: var(--mistake-soft); padding: 1px 4px; border-radius: 4px; }
        .asl-reply-line { display: flex; align-items: flex-start; gap: 8px; }
        .asl-reply-text { color: var(--ink); font-weight: 600; flex: 1; }
        .asl-correction-label { margin-top: 9px; padding-top: 8px; border-top: 1px dashed var(--paper-line); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ink-soft); font-weight: 700; }
        .asl-original-line { margin-top: 4px; color: var(--ink-soft); }
        .asl-correct-line { display: flex; align-items: flex-start; gap: 8px; margin-top: 6px; }
        .asl-correct-text { color: var(--correct); font-weight: 600; flex: 1; }
        .asl-speak-btn { border: none; background: var(--correct-soft); color: var(--correct); width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
        .asl-feedback { margin-top: 6px; font-size: 12.5px; color: var(--ink-soft); font-style: italic; }
        .asl-mistake-chip { font-size: 11px; background: var(--accent-soft); color: #A9670F; padding: 2px 7px; border-radius: 999px; margin-right: 5px; margin-top: 6px; display: inline-block; font-weight: 600; }
        .asl-controls { display: flex; flex-direction: column; align-items: center; gap: 10px; padding-top: 16px; }
        .asl-waveform { display: flex; align-items: center; gap: 3px; height: 24px; }
        .asl-bar { width: 3px; background: var(--accent); border-radius: 2px; animation: asl-wave 0.9s ease-in-out infinite; }
        @keyframes asl-wave { 0%,100% { height: 6px; } 50% { height: 22px; } }
        .asl-mic-btn { width: 66px; height: 66px; border-radius: 50%; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; background: var(--accent); color: #1A1206; box-shadow: 0 0 0 6px var(--accent-soft); transition: transform 0.15s ease; }
        .asl-mic-btn:active { transform: scale(0.95); }
        .asl-mic-btn.recording { background: var(--mistake); box-shadow: 0 0 0 6px var(--mistake-soft); }
        .asl-mic-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .asl-hint { font-size: 12px; opacity: 0.5; }
        .asl-reset { border: none; background: none; color: var(--cream-text); opacity: 0.45; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 4px; }
        .asl-error-banner { background: var(--mistake-soft); color: #F0A199; border: 1px solid rgba(196,69,59,0.3); padding: 8px 12px; border-radius: 8px; font-size: 12.5px; margin-bottom: 10px; display: flex; gap: 6px; align-items: center; }
        .asl-dash { flex: 1; overflow-y: auto; }
        .asl-stat-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
        .asl-stat-label { width: 90px; font-size: 12.5px; font-weight: 600; }
        .asl-stat-bar-track { flex: 1; height: 10px; background: var(--bg-soft); border-radius: 6px; overflow: hidden; }
        .asl-stat-bar-fill { height: 100%; border-radius: 6px; }
        .asl-stat-count { width: 22px; text-align: right; font-family: 'IBM Plex Mono', monospace; font-size: 12px; opacity: 0.7; }
        .asl-table-wrap { background: var(--paper); border-radius: 12px; padding: 4px; margin-top: 18px; color: var(--ink); overflow-x: auto; }
        .asl-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 480px; }
        .asl-table th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ink-soft); padding: 10px 12px; border-bottom: 1px solid var(--paper-line); }
        .asl-table td { padding: 10px 12px; border-bottom: 1px solid var(--paper-line); vertical-align: top; }
        .asl-table tr:last-child td { border-bottom: none; }
        .asl-type-pill { font-size: 10.5px; font-weight: 700; padding: 2px 7px; border-radius: 999px; color: #fff; white-space: nowrap; }
        .asl-ts { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--ink-soft); white-space: nowrap; }
        .asl-dash-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }
        .asl-dash-title { font-family: 'Fraunces', serif; font-size: 18px; }
        .asl-dash-clear { border: none; background: none; color: var(--cream-text); opacity: 0.45; font-size: 12px; cursor: pointer; }
      `}</style>

      <div className="asl-header">
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div className="asl-logo">Abhi's <span>Self Learn</span></div>
          <div className="asl-tabs">
            <button className={`asl-tab ${view === 'practice' ? 'active' : ''}`} onClick={() => setView('practice')}>
              <MessageSquare size={14} /> Practice
            </button>
            <button className={`asl-tab ${view === 'dashboard' ? 'active' : ''}`} onClick={() => { setView('dashboard'); loadMistakes(); }}>
              <LayoutDashboard size={14} /> Dashboard
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ padding: '6px 10px', borderRadius: 8, border: 'none', background: 'var(--bg-soft)', color: 'var(--cream-text)' }}>
            <option value="daily">Daily conversation</option>
            <option value="interview">Interview practice</option>
            <option value="office">Office English</option>
            <option value="travel">Travel English</option>
            <option value="story">Storytelling practice</option>
          </select>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ fontSize: 12, opacity: 0.8 }}>{ttsChecking ? 'Checking voice…' : ttsAvailable ? 'Human voice: On' : 'Human voice: Off'}</div>
            {!ttsAvailable && !ttsChecking && (
              <button onClick={enableHumanVoice} style={{ padding: '6px 10px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#1A1206', fontWeight: 700 }}>Enable human voice</button>
            )}
          </div>
        </div>
      </div>

      <div className="asl-body">
        {view === 'practice' ? (
          <>
            {error && <div className="asl-error-banner"><AlertCircle size={14} /> {error}</div>}
            {!micSupported && (
              <div className="asl-error-banner"><AlertCircle size={14} /> Speech recognition isn't supported in this browser. Try Chrome on desktop or Android.</div>
            )}
            {messages.length === 0 ? (
              <div className="asl-empty">
                <Mic size={30} strokeWidth={1.3} />
                <div style={{ fontFamily: "'Fraunces', serif", fontSize: 17 }}>Tap the mic and say a sentence</div>
                <div style={{ fontSize: 12.5, maxWidth: 260 }}>Speak naturally in English. Your coach will reply, then show a quick correction.</div>
              </div>
            ) : (
              <div className="asl-chat">
                {messages.map((m) => (
                  <div key={m.id} className={`asl-bubble-row ${m.role === 'user' ? 'user' : 'ai'}`}>
                    {m.role === 'user' && <div className="asl-bubble user-bubble">{m.text}</div>}
                    {m.role === 'ai' && (
                      <div className="asl-bubble ai-bubble">
                        {m.reply && (
                          <div className="asl-reply-line">
                            <span className="asl-reply-text">{m.reply}</span>
                            <button className="asl-speak-btn" onClick={() => speak(m.reply)} aria-label="Listen to reply">
                              <Volume2 size={13} />
                            </button>
                          </div>
                        )}
                        <div className="asl-correction-label">Correction</div>
                        <div className="asl-original-line">
                          {m.mistakeList && m.mistakeList.length > 0 ? (
                            <MarkedText original={m.original} mistakes={m.mistakeList} />
                          ) : (
                            <span>{m.original}</span>
                          )}
                        </div>
                        <div className="asl-correct-line">
                          <span className="asl-correct-text">{m.corrected}</span>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <button className="asl-speak-btn" onClick={() => speak(m.corrected)} aria-label="Listen">
                              <Volume2 size={13} />
                            </button>
                            <button className="asl-speak-btn" title="Repeat after me" onClick={() => handleRepeat(m.corrected)}>
                              <RotateCcw size={13} />
                            </button>
                          </div>
                        </div>
                        {m.mistakeList && m.mistakeList.length > 0 && (
                          <div>
                            {m.mistakeList.map((mm, i) => (
                              <div key={i} style={{ marginTop: 6 }}>
                                <span className="asl-mistake-chip">{ERROR_TYPES[mm.error_type]?.label || 'Other'}</span>
                                <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--ink-soft)' }}>{mm.explanation}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {m.feedback && <div className="asl-feedback">{m.feedback}</div>}
                      </div>
                    )}
                    {m.role === 'error' && <div className="asl-bubble ai-bubble" style={{ color: 'var(--mistake)' }}>{m.text}</div>}
                  </div>
                ))}
                {isProcessing && (
                  <div className="asl-bubble-row ai">
                    <div className="asl-bubble ai-bubble" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Thinking...
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}

            <div className="asl-controls">
              {isRecording && (
                <div className="asl-waveform">
                  {[0, 1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="asl-bar" style={{ animationDelay: `${i * 0.1}s` }} />
                  ))}
                </div>
              )}
              <button className={`asl-mic-btn ${isRecording ? 'recording' : ''}`} onClick={toggleRecording} disabled={!micSupported || isProcessing}>
                {isRecording ? <Square size={22} fill="#1A1206" /> : <Mic size={26} />}
              </button>
              <div className="asl-hint">{isRecording ? 'Listening... tap to stop' : 'Tap to talk'}</div>
              {messages.length > 0 && (
                <button className="asl-reset" onClick={resetPractice}><RotateCcw size={11} /> Clear conversation</button>
              )}
            </div>
          </>
        ) : (
          <div className="asl-dash">
            <div className="asl-dash-header">
              <div className="asl-dash-title">Weak points</div>
              {mistakes.length > 0 && <button className="asl-dash-clear" onClick={clearMistakes}>Clear history</button>}
            </div>
            {mistakes.length === 0 ? (
              <div className="asl-empty" style={{ padding: '40px 10px' }}>
                <div style={{ fontFamily: "'Fraunces', serif", fontSize: 16 }}>No mistakes logged yet</div>
                <div style={{ fontSize: 12.5 }}>Practice a few sentences and your patterns will show up here.</div>
              </div>
            ) : (
              <>
                {Object.keys(ERROR_TYPES).map((key) => {
                  const count = errorCounts[key] || 0;
                  if (count === 0) return null;
                  return (
                    <div className="asl-stat-row" key={key}>
                      <div className="asl-stat-label">{ERROR_TYPES[key].label}</div>
                      <div className="asl-stat-bar-track">
                        <div className="asl-stat-bar-fill" style={{ width: `${(count / maxCount) * 100}%`, background: ERROR_TYPES[key].color }} />
                      </div>
                      <div className="asl-stat-count">{count}</div>
                    </div>
                  );
                })}

                <div className="asl-table-wrap">
                  <table className="asl-table">
                    <thead>
                      <tr><th>Said</th><th>Correct</th><th>Type</th><th>When</th></tr>
                    </thead>
                    <tbody>
                      {mistakes.map((m) => (
                        <tr key={m.id}>
                          <td style={{ color: 'var(--mistake)' }}>{m.incorrect_phrase}</td>
                          <td style={{ color: 'var(--correct)' }}>{m.corrected_phrase}</td>
                          <td>
                            <span className="asl-type-pill" style={{ background: ERROR_TYPES[m.error_type]?.color || '#6B6558' }}>
                              {ERROR_TYPES[m.error_type]?.label || 'Other'}
                            </span>
                          </td>
                          <td className="asl-ts">
                            {new Date(m.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
