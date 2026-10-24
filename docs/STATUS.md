# Status: who works on what

Claim before you start: edit the row, commit, push, then work. Set `gemergt` in the same commit as the merge.
Status: `offen`, `in Arbeit`, `Test grün`, `gemergt`. Branch pattern: `feat/q-<kind>`.
File ownership (avoids merge conflicts): Leonie owns `queries.py`, `geometry.py`. Jennifer owns `tools.py`, `agent.py`, `directions.py`, `queries_routing.py`.
Priority by test weight (145 test questions): floor_area_total 33, shared_walls_count 26, largest_room 21, errand 20, wide_delivery_count 18, straight_line_3d 15, room_stacked 9, what_if_door 3, step_free_reachable_count 0.

| Aufgabe | Wer | Status | Branch |
|---|---|---|---|
| geometry.py (Fläche, Schwerpunkt, Wand, Stapel) | Leonie | offen | |
| floor_area_total (33) | Leonie | offen | |
| shared_walls_count (26) | Leonie | offen | |
| largest_room (21) | Leonie | offen | |
| straight_line_3d (15) | Leonie | offen | |
| wide_delivery_count (18) | Leonie | offen | |
| room_stacked (9) | Leonie | offen | |
| errand (20), in `queries_routing.py` | Jennifer | in Arbeit | feat/q-errand |
| tools.py + agent.py + find_space | Jennifer | offen | |
| what_if_door (3) | Jennifer | offen | |
| step_free_reachable_count (0 im Test) | | offen | |
| G1: Dev-Lauf, Test-CSV, Tag known-good | Jennifer | offen | |
| Interaction (6 Skripte als Tests, Verständniskarte, Landmarken) | Jennifer | offen | |
| Mutations-API + schlanke Web-Seite | Leonie | offen | |
| Voice-Spike + Voice | Jennifer | offen | |
| Chaos-Button, Level-4-Builder schlank | Leonie | offen | |
| Demo-Video + Tech-Erklärung | beide | offen | |
