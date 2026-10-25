// "Forget where I am" typed or spoken: the page forgets the position itself (POST /api/here/clear, like the chip's ×).
// No agent turn, so Wanda does not ask "Where are you now?". Only the plain command; "I'm not there any more"
// still goes to the agent.

export const FORGET_HERE_REPLY = "Okay, I've forgotten where you are.";

const FORGET_HERE =
  /^(please\s+)?(forget|clear|reset|remove)\s+(where\s+i\s*(am|'m)|my\s+(position|location)|the\s+(blue\s+)?dot)(\s+please)?$|^vergiss,?\s+(wo\s+ich\s+bin|meine\s+position|meinen\s+standort)(\s+bitte)?$/i;

export function isForgetHere(message: string): boolean {
  return FORGET_HERE.test(message.trim().replace(/[.!?]+$/, "").replace(/\s+/g, " "));
}
