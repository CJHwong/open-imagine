// One sheet for every overlay that reads text over the stage.
//
// The sheet is a `<dialog>` opened with showModal, so the top layer holds it
// above the stage's own overflow and above any sticky bar. The head sits
// outside the scrolling body, so the close button cannot scroll away from
// someone reading a long prompt or a long lyric.
//
// A sheet leaves the document the moment it is dismissed, on every path. The
// browser fires `close` in a later task, and a check that reads the tree right
// after Escape would still find the sheet, so the teardown runs here and the
// `cancel` path prevents the browser's own close.

let current = null;

function closeButton(name) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'icon-btn close';
  button.setAttribute('aria-label', name);
  button.title = name;
  button.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg>';
  return button;
}

// Open a sheet and return its dialog. The caller owns the body node.
// `onClose` runs after the node leaves the document, so a caller that marks its
// trigger can read the tree without the sheet in it.
export function openSheet({id, title, label = title, closeLabel = 'Close', body, footer = null, className = '', onClose = null}) {
  dismissSheet();
  const dialog = document.createElement('dialog');
  dialog.className = 'sheet' + (className ? ' ' + className : '');
  dialog.id = id;
  dialog.setAttribute('aria-label', label);

  const head = document.createElement('div');
  head.className = 'sheet-head';
  const heading = document.createElement('h2');
  heading.textContent = title;
  const close = closeButton(closeLabel);
  head.append(heading, close);

  const scroll = document.createElement('div');
  scroll.className = 'sheet-body';
  if (body) scroll.append(body);

  dialog.append(head, scroll);
  if (footer) {
    const foot = document.createElement('div');
    foot.className = 'sheet-foot';
    foot.append(footer);
    dialog.append(foot);
  }

  let closed = false;
  const cleanup = () => {
    if (closed) return;
    closed = true;
    if (current === dialog) current = null;
    dialog.remove();
    if (onClose) onClose();
  };
  const dismiss = () => {
    if (!dialog.open) return;
    dialog.close();
    cleanup();
  };
  dialog.dismiss = dismiss;
  close.addEventListener('click', dismiss);
  // A press on the backdrop targets the dialog itself, never its content.
  dialog.addEventListener('click', event => {
    if (event.target === dialog) dismiss();
  });
  // Escape closes synchronously here, so the caller's tree is already clean
  // when the key event returns. Without this the browser closes the dialog and
  // fires `close` a task later.
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    dismiss();
  });
  dialog.addEventListener('close', cleanup);

  document.body.append(dialog);
  current = dialog;
  dialog.showModal();
  close.focus();
  return dialog;
}

// Close the sheet this module opened, or the one the caller names.
export function dismissSheet(dialog = current) {
  if (dialog) dialog.dismiss?.();
}
