// A request through the phone's pipe can stall without failing: a dropped connection holds
// it open with no answer and no error, for minutes. These two limits end such a request so
// the caller can ask again on a fresh connection. Measured through the pipe, a status read
// answers in 15 to 180 ms, so four seconds is far past a slow answer and short beside a stall.
globalThis.STUDIO_STATUS_TIMEOUT_MS = 4000;
// A result can be a large clip over a slow link. It is never cut for taking long, only for
// receiving nothing for this long.
globalThis.STUDIO_STALL_TIMEOUT_MS = 15000;
// A workspace switch can free a loaded model before it answers, which is slower than a status
// read, so it gets a longer cap than one.
globalThis.STUDIO_SWITCH_TIMEOUT_MS = 30000;

// A small read, a status or the state: the whole answer, body included, within the limit.
globalThis.studioStatusFetch = function (url, init = {}) {
  return fetch(url, {...init, signal: AbortSignal.timeout(globalThis.STUDIO_STATUS_TIMEOUT_MS)});
};

// A result read that ends only when bytes stop arriving. The body is read here, so the answer
// comes back whole and the caller reads it as it would any response.
globalThis.studioStallFetch = async function (url, init = {}) {
  const controller = new AbortController();
  let timer = null;
  function arm() {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      controller.abort(new DOMException('The download stopped receiving data.', 'TimeoutError'));
    }, globalThis.STUDIO_STALL_TIMEOUT_MS);
  }
  arm();
  try {
    const answer = await fetch(url, {...init, signal: controller.signal});
    // A status with no body cannot be rebuilt with one.
    if (!answer.body || [101, 204, 205, 304].includes(answer.status)) return answer;
    const reader = answer.body.getReader();
    const parts = [];
    for (;;) {
      arm();
      const {done, value} = await reader.read();
      if (done) break;
      parts.push(value);
    }
    return new Response(new Blob(parts), {status: answer.status, statusText: answer.statusText, headers: answer.headers});
  } finally {
    window.clearTimeout(timer);
  }
};
