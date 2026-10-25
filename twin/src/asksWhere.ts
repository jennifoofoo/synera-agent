// Does Wanda's reply end by asking where the person is? Then the next tap on the map answers it ("I'm here.").
// The chat reply carries needs_position when a tool needed the unknown position (waitsForPlace); else a small
// heuristic on the reply's last question decides. EN and DE.

const WHERE = [
  /\bwhere are you\b(?!\s+(?:going|heading|headed|off to|trying|walking|looking|planning|travell?ing)\b)/,
  /\b(?:which|what) room are you\b/,
  /\bwhere (?:exactly )?are you (?:now|right now|at the moment|standing|located)\b/,
  /\bwhere do you stand\b/,
  /\bwo bist du\b(?!\s+(?:hin|unterwegs))/,
  /\bwo (?:befindest du dich|sind sie|befinden sie sich|stehst du)\b/,
  /\bin welchem raum (?:bist du|sind sie|befindest du dich|befinden sie sich)\b/,
];

/** The last question of the reply (the "Answer:" line left out), lower case; "" when the reply asks nothing. */
export function lastQuestion(reply: string): string {
  const lines = reply.trimEnd().split("\n");
  if (lines.length > 1 && /^\s*\**\s*Answer:/i.test(lines[lines.length - 1])) lines.pop();
  const text = lines.join(" ").replace(/[*_`]+/g, "").trim();
  const end = text.lastIndexOf("?");
  if (end < 0) return "";
  const start = Math.max(text.lastIndexOf(".", end - 1), text.lastIndexOf("!", end - 1), text.lastIndexOf("?", end - 1), text.lastIndexOf(":", end - 1));
  return text.slice(start + 1, end + 1).trim().toLowerCase();
}

/** True when the reply's last question asks for the person's location (room or spot). */
export function asksWhereYouAre(reply: string | null | undefined): boolean {
  if (!reply) return false;
  const question = lastQuestion(reply);
  return !!question && WHERE.some((pattern) => pattern.test(question));
}

// Fallback when the server sends no needs_position flag: the person asked for a place or a way, and Wanda's last
// question is about their own place ("Could you tap the room you're in on the plan?").
const ROUTING = /\b(?:where|nearest|closest|next|route|way to|how do i get|get to|take me|guide me|directions?|wo|nächste[nrs]?|weg|wie komme)\b/i;
const OWN_PLACE = [
  /\b(?:room|spot|place) you(?:'re| are) (?:in|at|standing)\b/,
  /\bwhere you are\b/,
  /\btap (?:the|your) (?:room|spot|place)\b/,
  /\byour (?:room|position|location|starting point|start)\b/,
  /\b(?:dein(?:en)? standort|wo du (?:bist|gerade bist|stehst)|in welchem raum du)\b/,
];

/** Wanda waits for a place: the next map tap or "I'm here" answers her question. The server's needs_position (a tool
 * needed the unknown position this turn) decides; without it, the reply text and the person's question do. */
export function waitsForPlace(
  reply: { reply?: string | null; error?: string; needs_position?: boolean } | null | undefined,
  question: string,
): boolean {
  if (!reply || reply.error) return false;
  if (reply.needs_position) return true;
  if (asksWhereYouAre(reply.reply)) return true;
  const last = lastQuestion(reply.reply ?? "");
  return !!last && ROUTING.test(question) && OWN_PLACE.some((pattern) => pattern.test(last));
}
