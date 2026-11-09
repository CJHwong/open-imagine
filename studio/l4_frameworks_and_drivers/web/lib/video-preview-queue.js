// Prepare a visible group with bounded decoder use, then reveal its motion together.
const waiting = [], completed = [];
let running = 0, collecting;
const concurrency = 2;

function drain() {
  while (waiting.length && running < concurrency) {
    const entry = waiting.shift();
    running++;
    Promise.resolve().then(entry.prepare).then(
      value => completed.push(() => entry.resolve(value)),
      error => completed.push(() => entry.reject(error)),
    ).finally(() => { running--; drain(); });
  }
  if (running || waiting.length || collecting) return;
  const group = completed.splice(0);
  group.forEach(reveal => reveal());
}

export function queueVideoPreview(prepare) {
  const result = new Promise((resolve, reject) => waiting.push({prepare, resolve, reject}));
  clearTimeout(collecting);
  collecting = setTimeout(() => { collecting = null; drain(); }, 40);
  return result;
}
