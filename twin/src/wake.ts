// Wake word matcher for "Hey Wanda" (pure, no imports: unit tested in twin/src/wake.test.ts).
// Speech recognition mishears the name a lot ("Evander", "E Wander", "hey vanda", "Juanda"), so the first one to
// three tokens are compared by sound, not spelling. Only the START of the utterance counts, and the real English
// words "wander"/"wonder" only count after a greeting ("hey wonder") or alone, so "I wonder where" and
// "wander around the hall" never wake Wanda.

/** Lower case, punctuation to spaces, single spaces. Apostrophes stay ("what's"). */
export function normalizeSpeech(text: string): string {
  return text
    .toLowerCase()
    .replace(/[’`]/g, "'")
    .replace(/[^\p{L}\p{N}'\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Said before the name: "hey wanda", "hi wanda", "okay wanda", "hallo wanda".
const GREETINGS = new Set(["hey", "hay", "hei", "heyy", "hi", "hello", "hallo", "ok", "okay", "oh", "yo"]);
// Short sounds the recogniser puts in front of the name: "e wander", "a wanda", "eh wanda".
const FILLERS = new Set(["e", "eh", "a", "ah", "ay", "ey", "uh", "i"]);
// Real words that sound like the name: only with a greeting or filler in front, or as the whole utterance.
const WEAK = new Set(["wander", "wonder", "wanders", "wonders", "wondered", "wandered", "wanna", "wand"]);

/** A word's sound key: v→w, "ju"/"hu"→w, o→a, final "er"→a, no apostrophes or trailing "s". */
function soundKey(word: string): string {
  return word
    .replace(/'s$/, "")
    .replace(/'/g, "")
    .replace(/^(?:ju|hu|gu)(?=a)/, "w")
    .replace(/v/g, "w")
    .replace(/o/g, "a")
    .replace(/er$/, "a")
    .replace(/(?<=a)s$/, "");
}

const NAME = "wanda";
// The name glued to a filler or greeting sound: "evander" → "ewanda", "ivanda" → "iwanda", "heywanda".
const GLUED_PREFIX = /^(?:e|i|a|ey|ay|eh|ah|hey|hi|hay|ok|okay)(?=wanda$)/;

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let diagonal = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const above = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, diagonal + (a[i - 1] === b[j - 1] ? 0 : 1));
      diagonal = above;
    }
  }
  return row[b.length];
}

/** The key is the name, maybe glued to a short sound in front. `loose` (after a greeting) also takes one edit. */
function isName(key: string, loose: boolean): boolean {
  if (key === NAME || key.replace(GLUED_PREFIX, "") === NAME) return true;
  return loose && key.length >= 4 && key.length <= 6 && key[0] === "w" && distance(key, NAME) <= 1;
}

/** The text after the wake word (normalised), or null when the utterance does not start with it. */
export function parseWake(text: string): { rest: string } | null {
  const tokens = normalizeSpeech(text).split(" ").filter(Boolean);
  if (!tokens.length) return null;
  const rest = (from: number) => ({ rest: tokens.slice(from).join(" ") });
  const [first, second = "", third = ""] = tokens;

  // "hey wanda …", "hey evander …", "hey e wander …", "hey wonder", "hey wanda's"
  if (GREETINGS.has(first) && second) {
    if (isName(soundKey(second), true)) return rest(2);
    if (FILLERS.has(second) && third && isName(soundKey(third), false)) return rest(3);
    if (third && isName(soundKey(second + third), false)) return rest(3);
  }
  // "e wander …", "a wanda …" ("i" only before the real name, never "I wonder")
  if (FILLERS.has(first) && second && isName(soundKey(second), false)) {
    if (first !== "i" || !WEAK.has(second)) return rest(2);
  }
  // "evander …", "ivanda …", "wanda …", "vanda …", "juanda …"; "wander"/"wonder" only alone
  if (isName(soundKey(first), false)) {
    if (!WEAK.has(first) || tokens.length === 1) return rest(1);
  }
  return null;
}
