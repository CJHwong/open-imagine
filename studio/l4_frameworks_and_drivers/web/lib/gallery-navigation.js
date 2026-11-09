// Every result strip uses the displayed order, including its pending preview.
// Return -1 when there is nothing to select; otherwise wrap in either direction.
export function galleryStepIndex(length, current, delta) {
  if (!length) return -1;
  if (current < 0) return delta < 0 ? length - 1 : 0;
  return ((current + delta) % length + length) % length;
}
