// "Yes" to Wanda's offer to guide (pure, unit tested in twin/src/guideYes.test.ts).
// After "... Want me to talk you through it while you walk?" a plain yes starts the page's walk on the drawn route,
// exactly like the "Guide me" button: no agent call, so the step sheet, hands-free "next" and the map all follow.
// Only a guiding offer counts: a yes to a change card ("Shall I close the lift?") always goes to the agent.
import { normalizeSpeech, parseWake } from "./wake";

const GUIDE_ME = /^(?:guide me|walk me|walk me there|take me there|begleite mich|begleit mich|führ mich hin)$/;
const YES =
  /^(?:yes|yeah|yep|yup|sure|ok|okay|please|go|let's go|ja|jo|klar|gerne|gern|bitte|los|guide me|walk me|talk me|take me|begleite mich|begleit mich)\b/;
const NOT_A_PLAIN_YES = /\b(?:no|nope|not|don't|nein|nicht|nee|but|aber|instead|stattdessen|other|andere|anderen|another)\b/;
const MAX_WORDS = 7;
// What Wanda's guiding offers say (walk.OFFER and the model's own wording, English and German).
const OFFER =
  /\b(?:guide you|talk you through|walk you|take you there|lead you|show you the way|begleiten|begleite dich|führen|lotsen|schritt für schritt)\b/i;

/** The person's words without a leading "Hey Wanda". */
function withoutWake(message: string): string {
  const said = normalizeSpeech(message);
  const woken = parseWake(said);
  return woken && woken.rest ? normalizeSpeech(woken.rest) : said;
}

/** True if the last sentence of Wanda's reply is an offer to guide the person along the route. */
export function offersGuiding(reply: string | undefined): boolean {
  if (!reply) return false;
  const sentences = reply.trim().split(/(?<=[.!?])\s+/);
  const last = sentences[sentences.length - 1] ?? "";
  return last.endsWith("?") && OFFER.test(last);
}

/** The message starts the page's walk: "guide me" on its own, or a plain yes right after a guiding offer. */
export function acceptsGuiding(message: string, lastAgentReply: string | undefined): boolean {
  const said = withoutWake(message);
  if (GUIDE_ME.test(said)) return true;
  if (!offersGuiding(lastAgentReply)) return false;
  return YES.test(said) && !NOT_A_PLAIN_YES.test(said) && said.split(" ").length <= MAX_WORDS;
}
