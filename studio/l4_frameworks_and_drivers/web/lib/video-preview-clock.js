// One clock for every visible thumbnail. Each owner draws only when its frame changes.
const viewers = new Set();
let scheduled;
function tick(time) {
  scheduled = null;
  viewers.forEach(draw => draw(time));
  if (viewers.size) scheduled = requestAnimationFrame(tick);
}
export function watchVideoPreview(draw) {
  viewers.add(draw);
  if (scheduled == null) scheduled = requestAnimationFrame(tick);
  return () => {
    viewers.delete(draw);
    if (!viewers.size && scheduled != null) {
      cancelAnimationFrame(scheduled);
      scheduled = null;
    }
  };
}
