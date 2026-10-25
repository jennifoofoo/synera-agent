// Does Wanda's reply end by asking where the person is? Then the next tap on the map answers it ("I'm here.").
// The chat reply carries no flag for this (the server only says "Which room are you in?" in the text), so a small
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
