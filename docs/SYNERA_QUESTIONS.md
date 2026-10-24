# Questions for Synera (ask on site, one person)

Short list first. Details below each item if they ask.

1. **Output format on Sunday.** Is it the README CSV (`question_id,answer` with a final `Answer:` line) or `answers.json` as in the brief (located item or room id, route as an ordered list of node ids, route length in metres)? Do we submit both?
2. **Question types.** Besides the 8 benchmark kinds, does Sunday include warm-up kinds (locate, count, route, step-free route, route with closure, tour)? Roughly how many questions, and are they all about one building?
3. **Route scoring.** Is the best route always measured with your door-to-door rule (inside each space, 15 cm off walls, stairs 2 m per metre, lift 15 m plus 1 m per metre), also for the warm-up questions? Is our own distance number ignored?
4. **Level 3 (several buildings).** How will it be checked? Will you give us several buildings plus the connections between them, and in which format (file, description, in the question)? How do we measure the walk between two entrances of different buildings? Will Sunday contain questions that span more than one building?
5. **Level 4 (build from plans).** How is it checked: do you give us plan images (format, which style, how many floors) and then ask questions about the built building, or do you compare our `building.json` to a reference? Is there a time limit per building? Will the plans have a scale bar, or should we ask the user for a known length?
6. **Forklift and bays.** Do questions use the forklift rule (aisles and openings of 3 m or wider) and "bays are destinations, not shortcuts"? How are bay entries measured (to the opening or the bay centre)? What counts as an aisle?
7. **Compass words.** Are directions such as "the east lift" used in questions? What is east in the plan (+x)?
8. **Voice.** Does browser speech recognition count as "voice in" or do you expect ElevenLabs in both directions? Which browser and network will the demo use?
9. **Process.** Exact code-freeze time, time limit per question when you run `BENCHMARK.md`, and which ElevenLabs quota we have.
10. **Aisles and docks.** In the data, aisles are named "Main aisle H-C1" and no space has "dock" in its name. How are "Aisle 4" and "dock B" meant in the Sunday questions (names, numbering, which spaces)?
11. **Time and deliveries.** The deck mentions "Where is the steel drum delivered yesterday?". Will Sunday contain questions about history or deliveries (the data has no timestamps)?
12. **Access rights.** Do the Sunday buildings or questions include access restrictions (rooms or doors that need a clearance, keycards, safety gear, escorted access)? The data has no such fields.
