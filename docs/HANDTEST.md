# Hand test: page, voice and edits (about 20 minutes)

Run this together on a real device with the microphone on. Mark each step OK or FAIL and note what you saw. Start the page the usual way (see README). Use a procedural factory building and one OSM building.

Say every voice step in English, at normal speed, and wait for the spoken answer before the next one.

## A. Page basics
1. Open the page, load a building. Expected: plan shows, chat is open.
2. Switch 2D to 3D and back. Expected: same building, no error, state stays.
3. Ask in text: "Where is the nearest coffee machine?" Expected: answer plus the finds light up on the plan.

## B. Click selection
4. Click a room on the plan. Expected: a chip "Picked: Room ..." above the chat.
5. Type: "What is this room?" Expected: the agent names the clicked room (not another one).
6. Clear the chip with its button. Expected: chip gone.

## C. Voice in and out
7. Press the microphone and say: "Where is the largest meeting room?" Expected: text appears in the chat, spoken English answer.
8. Say a room number: "How do I get from room zero point one two to the entrance?" Expected: the right room is understood. If not, note the exact words the page showed.
9. Say: "Keep it short, my hands are full." Then ask a route. Expected: at most 3 steps, "next" gives the next block.

## D. Edits by voice (each needs a card and a clear yes in the NEXT message)
10. Say: "Close lift 1." Expected: a spoken card with the effect on routes, nothing changed yet.
11. Say: "Yes." Expected: change applies, plan shows the lift as closed.
12. Say: "Undo that." Expected: card, then "Yes", lift is open again on the plan.
13. Click a room, then say: "Add a printer here." Expected: the agent asks which printer type (printer, multifunction, 3D), then card, then after "Yes" the printer appears at the clicked place on the plan.
14. Say: "Put a printer in the left corner of this room." Expected: it asks which corner or understands "left", card names the actual position.
15. Say: "Move the printer next to the door." Expected: card, yes, the printer moves on the plan without a reload.

## E. Break it on purpose
16. Say "Yes" with no card pending. Expected: nothing changes, the agent says there is nothing to confirm.
17. Say "Close lift 1", then "What is the weather?", then "Yes". Expected: the old card expired, nothing is closed.
18. Say "I want to weld something." Expected: it names the welding station and where it is, says what it is for as general knowledge, no invented specs.

## F. Level 4 upload
19. Upload one floor plan image, say: "Build this, the building is 40 metres wide." Expected: floors and scale questions only if needed, a preview card with room and door counts.
20. Say "Yes, save it", then ask a route in the new building. Expected: saved, the page opens it, the route works.

## G. Hands-free (needs Leonie's page part)
Needs Chrome, the page in the foreground, localhost or https, and the "Hands-free" switch on.
21. Say: "Hey Wanda, where is the coffee machine?" Expected: a question is sent and answered. Say the same sentence without "Hey Wanda": nothing happens.
22. Say only: "Hey Wanda." Expected: a short tone and a spoken "I'm here.", then your next sentence is the question.
23. While the answer is being spoken, say "Hey Wanda". Expected: the speech stops at once.
24. Leave the page quiet for 2 minutes, then say "Hey Wanda, where is the toilet?" Expected: it still listens (restart worked, no double answers).
25. Switch Hands-free off and talk. Expected: no permanent microphone, the mic symbol shows it is off, push-to-talk still works.

## Result log
Write FAIL lines here with the exact words said and what appeared, then hand them to the agent as bugs.
