// In-page replacements for window.confirm and window.alert. The Mac app's
// WKWebView has no UI delegate for JavaScript panels, so there confirm()
// returns false without showing anything and alert() does nothing. These
// render a modal <dialog> in the page instead, so the browser and the app
// behave the same. Esc cancels, Enter confirms, and focus returns to the
// element that had it before the dialog opened.

let queue = Promise.resolve();

function openDialog(message, { confirmLabel, cancelLabel }) {
  const dialog = document.createElement("dialog");
  dialog.className = "page-dialog";
  dialog.setAttribute("role", "alertdialog");
  const text = document.createElement("p");
  text.className = "page-dialog-message";
  text.id = `page-dialog-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  text.textContent = message;
  dialog.setAttribute("aria-describedby", text.id);
  dialog.setAttribute("aria-label", cancelLabel ? "Confirm" : "Notice");
  const actions = document.createElement("div");
  actions.className = "page-dialog-actions";
  const button = (label, value, className) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = className;
    b.value = value;
    b.textContent = label;
    b.addEventListener("click", () => dialog.close(value));
    actions.append(b);
    return b;
  };
  if (cancelLabel) button(cancelLabel, "cancel", "mini");
  const ok = button(confirmLabel, "ok", "act");
  dialog.append(text, actions);

  const previous = document.activeElement;
  return new Promise(resolve => {
    dialog.addEventListener("keydown", e => {
      // Keys answered here are the dialog's: the page's own shortcuts (Esc
      // closes the agents panel, for one) must not act on them as well.
      if (e.key === "Escape" || e.key === "Enter") e.stopPropagation();
      if (e.key !== "Enter" || e.isComposing || e.target.value === "cancel") return;
      e.preventDefault();
      dialog.close("ok");
    });
    dialog.addEventListener("close", () => {
      const confirmed = dialog.returnValue === "ok";
      dialog.remove();
      if (previous?.isConnected) previous.focus();
      resolve(confirmed);
    });
    document.body.append(dialog);
    dialog.showModal();
    ok.focus();
  });
}

function enqueue(open) {
  const result = queue.then(open);
  queue = result.catch(() => {});
  return result;
}

/** Ask a yes/no question in the page. Resolves true only when confirmed. */
export function confirmDialog(message, { confirmLabel = "OK", cancelLabel = "Cancel" } = {}) {
  return enqueue(() => openDialog(message, { confirmLabel, cancelLabel }));
}

/** Show a message in the page. Resolves when it is dismissed. */
export function showNotice(message) {
  return enqueue(() => openDialog(message, { confirmLabel: "OK", cancelLabel: null })).then(() => {});
}
