// One microphone take, shared by Voice and Music. The caller keeps the UI state; only this
// module holds the device, so every path that ends a take also closes the microphone:
// a stop, a cancel, the length cap, and an error from the permission prompt.

export function startRecording({maxSeconds = 120, name = 'recording.webm', onStart, onFinish, onError}) {
  let stream = null;
  let recorder = null;
  let timer = 0;
  let cancelled = false;
  const release = () => {
    clearTimeout(timer);
    timer = 0;
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
  };
  const api = {
    stop() { if (recorder?.state === 'recording') recorder.stop(); },
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
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      const blob = new Blob(chunks, {type: recorder.mimeType});
      release();
      if (!cancelled) onFinish?.(new File([blob], name, {type: blob.type}));
    };
    recorder.start();
    onStart?.(api);
    timer = setTimeout(api.stop, maxSeconds * 1000);
  }).catch(error => {
    release();
    if (!cancelled) onError?.('The microphone could not be opened: ' + error.message);
  });
  return api;
}
