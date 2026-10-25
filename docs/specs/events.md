# Events and room bookings

## Goal
Wanda knows what happens where and when: sessions, deadlines and room bookings ("Where are the pitches?", "Is the
Project Room free at 10:00?", "Wann ist der Code Freeze?"). Same place-knowledge store, same rule: every time and room
comes from deterministic Python, the model only picks the tool and phrases the reply, then offers the route.

## Design
- New fact kind `event` in `building_agent/knowledge.py`: title in `text`, room(s) = anchor `space_id` plus `related`,
  `valid_from` = start, `valid_to` = end, `author` = organiser or "booked by". A room booking is an event
  ("Project Room booked: Team Synera", author "Leonie").
- `KnowledgeStore.add(..., valid_from=...)`: a start time other than now is accepted for kind `event` only (past or
  future); notes, issues and closures keep "valid from now". Events never touch routing (`active_closures` reads
  closures only). `query(status="all"|history)` also returns facts that have not started yet (status `future`), so the
  page and the graph see upcoming events; the default "open now" query is unchanged.
- `building_agent/knowledge_tools.py`, one chat tool `find_events(query, when, place)`: filters events by title words,
  by time ("now", "today", "this afternoon", "at 14:00", "um 15 Uhr"; reuses `period_bounds`, `clock_of` and
  `day_words`/`clock_words`) and by room (`resolve_anchor`). Each hit: title, rooms, start and end in words, running
  now, by. With `place` and a clock time it also answers `free` (true/false) and `busy_with` for that moment.
- Prompt (`KNOWLEDGE_RULES` in `agent.py`): events, sessions, bookings, "where is X happening", "is room Y free" use
  find_events; never invent times or rooms; offer the route with give_directions. Benchmark (Answer:) never calls it
  (the tool refuses in an Answer: message, the benchmark agent has no store anyway).
- Page: `FactKind` gets `event`; the notes list shows a text tag "Event" with "14:00 to 16:00 today"; the knowledge
  graph draws events in ring 2 (role `event`, existing colours, dashed outline) and the time slider shows them once
  the slider reaches their start.
- Demo seed `scripts/demo_events_seed.py` (Urban Colab, plan-89323a15, dates relative to today, Europe/Berlin,
  idempotent by title and start).

## Acceptance
- "Where are the pitches?" -> find_events, reply names Auditorium (Arena) and 14:00 and offers the route.
- "Is the Project Room free at 10:00?" -> not free, booked by Team Synera (until 12:00).
- "Wann ist der Code Freeze?" -> 13:00.
- Live suite stays green, dev benchmark `--per-kind 3` stays 24/24.

## Tests
- Unit (`tests/test_events.py`): future start accepted for events only; query default skips future events, history
  shows them as `future`; events never close anything; find_events by title, time, place, running now; room free and
  busy; Answer: messages refused; seed is idempotent; `/api/facts?history=1` lists a future event.
- Live (`tests/live/test_events.py`): the three acceptance conversations on the seeded Urban Colab with a fixed clock.
