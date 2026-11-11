// Queens: a team's lead agent. The crown is the one marker for the role
// everywhere an agent is listed - the roster, the tile grid, the agent
// switcher, chat rows, the task board, pickers and the hive canvas - so being
// a queen never depends on sort order alone.
import { html } from "htm/preact";

// The team `user` queens, read from team data on every render so a promotion
// or a cleared queen shows up on the next poll. Takes one team or an array.
export function queenTeam(teams, user) {
  if (!user) return null;
  return (Array.isArray(teams) ? teams : [teams]).find(t => t && t.queen === user) || null;
}

export function isQueen(teams, user) {
  return queenTeam(teams, user) !== null;
}

// Plain text for <option> labels and canvas captions, which cannot hold markup.
export function queenSuffix(teams, user) {
  return isQueen(teams, user) ? " · ♛ queen" : "";
}

// ♛ with the role spelled out in the tooltip and for screen readers. `word`
// adds the visible word "queen", and `teamName` spells out which team, for
// the lists with room for it.
export function Crown({ teams, user, word = false, teamName = false }) {
  const team = queenTeam(teams, user);
  if (!team) return null;
  const said = `queen of ${team.name}`;
  const shown = teamName ? said : word ? "queen" : null;
  return html`<span class="crown" title=${said}><span aria-hidden="true">♛</span>${shown && html`<span class="crown-word" aria-hidden="true">${shown}</span>`}<span class="sr-only">${said}</span></span>`;
}
