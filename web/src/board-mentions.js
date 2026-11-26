// Match the hub's mention boundaries and case-insensitive team membership.
const MENTION = /(?<![A-Za-z0-9_@.-])(@[A-Za-z0-9][A-Za-z0-9-]{0,47})(?![A-Za-z0-9_-])/g;

export function mentionParts(text, members) {
  return text.split(MENTION).map((part, i) => ({
    text: part, mention: i % 2 === 1 && members.has(part.slice(1).toLowerCase()),
  }));
}

// Mark only text nodes to preserve the renderer's escaping and link targets.
export function highlightBoardMentions(markup, members) {
  if (!members?.size || !markup.includes("@")) return markup;
  const root = document.createElement("template");
  root.innerHTML = markup;
  const walker = document.createTreeWalker(root.content, NodeFilter.SHOW_TEXT);
  const matches = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.data.includes("@")) continue;
    const parts = mentionParts(node.data, members);
    if (parts.some(part => part.mention)) matches.push([node, parts]);
  }
  for (const [node, parts] of matches) {
    node.replaceWith(...parts.map(({ text, mention }) => {
      if (!mention) return document.createTextNode(text);
      const mark = document.createElement("mark");
      mark.className = "board-mention";
      mark.textContent = text;
      return mark;
    }));
  }
  return root.innerHTML;
}
