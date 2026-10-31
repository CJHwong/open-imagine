// One microphone take, shared by Voice and Music. The caller keeps the UI state; only this
// module holds the device, so every path that ends a take also closes the microphone:
// a stop, a cancel, the length cap, and an error from the permission prompt.
//
// A take counts only the seconds that carry sound. A hum of three seconds in a ten second
// take leaves the take short of `minActiveSeconds`, so the take is rejected and the form
// says why, exactly as it does for a take the cap ends.

const SOUND_FLOOR = 0.01;  // Full-scale RMS, about -40 dBFS: above a laptop's noise floor.
const TICK_SECONDS = 0.2;

function readyTone(context) {
  if (!context) return;
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.frequency.value = 880;
  gain.gain.setValueAtTime(0.06, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.15);
  oscillator.connect(gain).connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.15);
}

export function startRecording({
  maxSeconds = 120, minActiveSeconds = 7, name = 'recording.webm',
  onStart, onFinish, onError, onTick, onShort,
}) {
  let stream = null;
  let recorder = null;
  let context = null;
  let analyser = null;
  let timer = 0;
  let ticker = 0;
  let active = 0;
  let cancelled = false;
  const release = () => {
    clearTimeout(timer);
    timer = 0;
    clearInterval(ticker);
    ticker = 0;
    context?.close().catch(() => {});
    context = null;
    analyser = null;
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
  };
  const stopNow = () => { if (recorder?.state === 'recording') recorder.stop(); };
  const api = {
    // Stop always ends the take. One below the minimum is dropped by `onstop`, so the
    // button never argues with the person holding the microphone.
    stop() { stopNow(); },
    cancel() {
      cancelled = true;
      clearTimeout(timer);
      // Detaching the handler keeps a cancelled take from turning into a reference.
      if (recorder?.state === 'recording') { recorder.onstop = null; recorder.stop(); }
      release();
    },
  };
  if (!navigator.mediaDevices?.getUserMedia) {
    onError?.('Recording needs localhost or HTTPS microphone access.');
    return api;
  }
  navigator.mediaDevices.getUserMedia({audio: true}).then(got => {
    if (cancelled) { got.getTracks().forEach(track => track.stop()); return; }
    stream = got;
    // The analyser hears the same stream the recorder writes, so silence never counts as
    // input. A context the browser keeps suspended falls back to wall-clock seconds.
    try {
      context = new AudioContext();
      analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      context.createMediaStreamSource(stream).connect(analyser);
      context.resume().catch(() => {});
    } catch (_) {
      context = null;
      analyser = null;
    }
    const samples = analyser ? new Float32Array(analyser.fftSize) : null;
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      const blob = new Blob(chunks, {type: recorder.mimeType});
      const short = active < minActiveSeconds;
      const values = {active, needed: minActiveSeconds};
      release();
      if (cancelled) return;
      if (short) { onShort?.(values); return; }
      onFinish?.(new File([blob], name, {type: blob.type}));
    };
    recorder.start();
    const started = performance.now() / 1000;
    ticker = setInterval(() => {
      if (!analyser || context?.state !== 'running') active += TICK_SECONDS;
      else {
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const sample of samples) sum += sample * sample;
        if (Math.sqrt(sum / samples.length) > SOUND_FLOOR) active += TICK_SECONDS;
      }
      onTick?.({seconds: performance.now() / 1000 - started, active, needed: minActiveSeconds});
    }, TICK_SECONDS * 1000);
    timer = setTimeout(stopNow, maxSeconds * 1000);
    // The tone waits for the context to run, so it sounds when the input is live.
    if (context) context.resume().then(() => readyTone(context)).catch(() => {});
    onStart?.(api);
  }).catch(error => {
    release();
    if (!cancelled) onError?.('The microphone could not be opened: ' + error.message);
  });
  return api;
}
