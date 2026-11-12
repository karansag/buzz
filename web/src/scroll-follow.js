// Keep the reader's intent separate from the current bottom distance. A
// queued scroll event can arrive after a message/image grows the content:
// the reader did not scroll up just because the bottom moved away.
export function createBottomFollower() {
  let pinned = true;
  let lastTop = 0;
  return {
    onScroll(el) {
      const top = Math.max(0, el.scrollTop);
      if (top + el.clientHeight >= el.scrollHeight - 8) pinned = true;
      else if (top < lastTop - 1) pinned = false;
      lastTop = top;
    },
    follow(el) {
      if (pinned) el.scrollTop = el.scrollHeight;
      lastTop = Math.max(0, el.scrollTop);
    },
    // A deliberate jump somewhere else in the thread: stop following the
    // newest message until the reader scrolls back to the bottom.
    unpin() {
      pinned = false;
    },
    // Whether the reader is following the newest message.
    pinned() {
      return pinned;
    },
    // Back to following, e.g. after a layout change they did not ask for.
    pin() {
      pinned = true;
    },
  };
}
