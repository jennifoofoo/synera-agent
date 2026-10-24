"""General knowledge per asset type: what this KIND of device is for, what people say when they need it, safety.

Hand-written content. The data only has type, category, position and size, so nothing here is a fact about one
unit (no specs, settings, state or capacity). `tasks` are lowercase verb phrases and nouns in English and German."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Knowledge:
    kind: str
    summary: str
    tasks: tuple[str, ...]
    safety: str = ""


def _k(kind: str, summary: str, tasks: str, safety: str = "") -> Knowledge:
    return Knowledge(
        kind, summary, tuple(dict.fromkeys(part.strip() for part in tasks.split(",") if part.strip())), safety
    )


TRAINED = "Trained staff only. Wear the protective equipment required for this area."

ASSET_KNOWLEDGE: dict[str, Knowledge] = {
    # ---------- machines ----------
    "3d_printer": _k(
        "machine",
        "A 3D printer builds small plastic parts and models layer by layer from a digital design.",
        "3d print, 3d printing, print a model, prototype, make a prototype, additive, 3d drucken, 3d druck, prototyp, "
        "3d drucker",
        "Hot parts while printing. Do not touch the nozzle or the heated bed.",
    ),
    "industrial_3d_printer": _k(
        "machine",
        "An industrial 3D printer builds larger or stronger parts layer by layer from a digital design.",
        "3d print, 3d printing, industrial 3d print, additive manufacturing, additive, prototype, print a part, "
        "3d drucken, 3d druck, additive fertigung",
        TRAINED,
    ),
    "cnc_mill": _k(
        "machine",
        "A CNC mill cuts material off a block with a computer-controlled spinning tool to shape a part.",
        "mill, milling, machine a part, cnc mill, cnc milling, cut metal, fraesen, cnc fraese, fraese, cnc fraesen",
        TRAINED,
    ),
    "milling_machine": _k(
        "machine",
        "A milling machine shapes metal or other material with a rotating cutting tool.",
        "mill, milling, machine a part, mill a part, milling machine, fraesen, fraesmaschine, fraese",
        TRAINED,
    ),
    "cnc_lathe": _k(
        "machine",
        "A CNC lathe spins a workpiece while a cutting tool shapes it, for example into shafts and round parts.",
        "turn a shaft, turn a part, turn metal, lathe, cnc lathe, make a round part, drehmaschine, "
        "cnc drehmaschine, welle drehen, teil drehen",
        TRAINED,
    ),
    "drill_press": _k(
        "machine",
        "A drill press drills precise holes into a workpiece clamped on its table.",
        "drill, drilling, drill a hole, make a hole, bore a hole, bohren, loch bohren, bohrmaschine, saeulenbohrmaschine",
        "Clamp the workpiece, tie back hair and loose clothes, wear eye protection.",
    ),
    "press_brake": _k(
        "machine",
        "A press brake bends sheet metal into angles.",
        "bend a sheet, bend sheet metal, bend metal, fold sheet metal, press brake, abkanten, abkantpresse, "
        "blech biegen, blech abkanten",
        TRAINED,
    ),
    "laser_cutter": _k(
        "machine",
        "A laser cutter cuts or engraves flat material such as sheet metal, wood or acrylic with a focused laser beam.",
        "laser, laser cut, laser cutting, cut sheet metal, cut metal, cut acrylic, cut with a laser, engrave, engraving, laser cutter, laser schneiden, "
        "lasercutter, gravieren, laserschneiden",
        "Laser radiation and fumes. Trained staff only, never look into the beam.",
    ),
    "waterjet_cutter": _k(
        "machine",
        "A waterjet cutter cuts sheet material such as metal, stone or glass with a high-pressure jet of water.",
        "cut sheet metal, cut stone, cut glass, waterjet, water jet, waterjet cutting, cut a plate, cut metal, "
        "wasserstrahl, wasserstrahlschneiden, blech schneiden, stein schneiden, glas schneiden",
        "High-pressure water and noise. Trained staff only, wear hearing and eye protection.",
    ),
    "injection_moulding_machine": _k(
        "machine",
        "An injection moulding machine makes plastic parts by pressing melted plastic into a mould.",
        "injection moulding, injection molding, mould plastic, mold plastic, make plastic parts, plastic part, "
        "spritzguss, spritzgiessen, kunststoffteile, spritzgussmaschine",
        "Hot plastic and closing mould parts. Trained staff only.",
    ),
    "robot_cell": _k(
        "machine",
        "A robot cell is a fenced work area where an industrial robot automates a task such as handling or assembly.",
        "robot, robotics, robot cell, pick and place, industrial robot, roboter, roboterzelle",
        "Never enter the fenced area while the robot is active. Trained staff only.",
    ),
    "conveyor": _k(
        "machine",
        "A conveyor moves goods or parts along a fixed path, for example between work areas.",
        "conveyor, conveyor belt, move parts, transport goods, foerderband, transportband",
        "Keep hands, hair and clothing away from moving parts.",
    ),
    "curing_oven": _k(
        "machine",
        "A curing oven heats coated or bonded parts so that powder coating, paint or glue hardens.",
        "cure coating, curing oven, bake coating, harden coating, powder coating, oven, aushaerten, einbrennen, "
        "lack einbrennen, ofen",
        "Very hot surfaces. Trained staff only.",
    ),
    "forklift": _k(
        "machine",
        "A forklift is a vehicle with forks that lifts and moves pallets and heavy goods.",
        "forklift, fork lift, lift pallets, move pallets, move heavy goods, stapler, gabelstapler, "
        "paletten transportieren",
        "Licensed drivers only. Pedestrians keep clear of its route.",
    ),
    "coordinate_measuring_machine": _k(
        "machine",
        "A coordinate measuring machine measures the exact dimensions of a part with a touch probe.",
        "measure a part, measure parts, precision measurement, check dimensions, quality check, cmm, "
        "coordinate measuring, teil vermessen, messmaschine, koordinatenmessgeraet, bauteil messen",
        "Trained staff only. Handle probes and parts with care.",
    ),
    "hvac_unit": _k(
        "machine",
        "An HVAC unit heats, cools and ventilates the air of a building or area.",
        "ventilation, air conditioning, central heating, heating system, cooling system, air cooling, air handling, hvac, climate, lueftung, klimaanlage, "
        "klima, heizung",
        "Technical staff only.",
    ),
    "boiler": _k(
        "machine",
        "A boiler heats water for heating or hot water supply.",
        "boiler, hot water, heating water, water heater, heizkessel, warmwasser, heizung, kessel",
        "Technical staff only. Hot surfaces and pressure.",
    ),
    "compressor": _k(
        "machine",
        "An air compressor supplies compressed air for tools and machines.",
        "compressed air, compressor, air supply, pneumatic, druckluft, kompressor, luftkompressor",
        "Technical staff only. Pressurised air and noise.",
    ),
    # ---------- equipment ----------
    "welding_station": _k(
        "equipment",
        "A welding station is a work area for joining metal parts by welding.",
        "weld, welding, join metal, join two pieces of metal, join two parts, join parts, connect metal parts, weld two parts, "
        "schweissen, schweissplatz, schweissen, metall verbinden",
        "Trained staff only. Wear a welding helmet, gloves and protective clothing, and keep the fume extraction on.",
    ),
    "soldering_station": _k(
        "equipment",
        "A soldering station joins electronic components to circuit boards with a heated soldering iron.",
        "solder, soldering, solder a circuit board, solder electronics, repair electronics, loeten, loetstation, "
        "elektronik loeten, platine loeten",
        "Very hot iron and fumes. Wear eye protection and keep the area ventilated.",
    ),
    "powder_station": _k(
        "equipment",
        "A powder handling station is where powder for powder coating or additive manufacturing is handled.",
        "powder, handle powder, powder handling, powder coating, powder coat, pulver, pulverbeschichten, pulverstation",
        "Fine powder can irritate lungs and eyes. Trained staff only, wear a mask and eye protection.",
    ),
    "forklift_charging_station": _k(
        "equipment",
        "A forklift charging station is where the batteries of electric forklifts are charged.",
        "charge a forklift, charge forklift, forklift charging, charge forklift battery, forklift battery, "
        "stapler laden, gabelstapler laden, stapler ladestation",
        "Trained staff only. Batteries can release gas and carry high current.",
    ),
    "pallet_jack": _k(
        "equipment",
        "A pallet jack is a hand-pulled or electric truck that lifts and moves pallets over short distances.",
        "pallet jack, move a pallet, move pallets, pallet truck, hand pallet truck, hubwagen, palette bewegen, "
        "handhubwagen",
        "Mind your feet and keep the load stable.",
    ),
    "fire_extinguisher": _k(
        "equipment",
        "A fire extinguisher puts out small fires.",
        "fire extinguisher, extinguish a fire, put out a fire, fire safety, extinguisher, feuerloescher, "
        "feuer loeschen",
        "Only fight small fires and keep an escape route behind you.",
    ),
    "defibrillator": _k(
        "equipment",
        "A defibrillator (AED) gives an electric shock to restart the heart in a cardiac emergency.",
        "defibrillator, defib, aed, cardiac arrest, heart emergency, first aid, defibrillator holen, "
        "herzstillstand, erste hilfe",
        "Emergency use. Call the emergency number and follow the spoken instructions of the device.",
    ),
    "eyewash_station": _k(
        "equipment",
        "An eyewash station rinses the eyes with water after contact with chemicals or particles.",
        "eyewash, wash eyes, rinse eyes, chemical in eye, eye emergency, augendusche, augen spuelen, augenspuelung, "
        "augen auswaschen",
        "Emergency use. Rinse for a long time and get medical help.",
    ),
    "fume_hood": _k(
        "equipment",
        "A fume hood is a ventilated cabinet for working with chemicals or fumes so they do not reach the room.",
        "fume hood, work with chemicals, chemicals, handle fumes, extract fumes, fume extraction, abzug, "
        "chemikalien, laborabzug, mit chemikalien arbeiten",
        "Wear lab protection and keep the sash at the working height.",
    ),
    "electrical_panel": _k(
        "equipment",
        "An electrical panel holds the fuses and breakers that distribute power to a building or area.",
        "electrical panel, fuse box, fuse, breaker, circuit breaker, power outage, power distribution, "
        "sicherungskasten, sicherung, stromverteiler, stromausfall, schaltschrank",
        "Qualified electricians only.",
    ),
    "ups_unit": _k(
        "equipment",
        "A UPS is a battery backup that keeps equipment such as servers running during a short power outage.",
        "ups, battery backup, backup power, uninterruptible power, usv, notstrom, unterbrechungsfreie stromversorgung",
        "Technical staff only. It can carry live voltage even when unplugged.",
    ),
    "server_rack": _k(
        "equipment",
        "A server rack is a cabinet holding servers and network equipment.",
        "server, servers, network, network equipment, it equipment, server rack, serverschrank, netzwerk, serverraum",
        "IT staff only.",
    ),
    "printer": _k(
        "equipment",
        "A printer prints documents on paper.",
        "print, print a document, print documents, printing, paper printout, drucken, dokument drucken, drucker, "
        "ausdrucken",
    ),
    "multifunction_printer": _k(
        "equipment",
        "A multifunction printer prints, copies and scans documents.",
        "print, print a document, copy, copying, photocopy, scan, scanning, scan a document, drucken, kopieren, "
        "scannen, kopierer, ausdrucken",
    ),
    "coffee_machine": _k(
        "equipment",
        "A coffee machine makes coffee and often other hot drinks.",
        "coffee, make coffee, get coffee, espresso, cappuccino, hot drink, kaffee, kaffee holen, kaffeemaschine, "
        "kaffeeautomat, kaffeevollautomat",
        "Hot liquids and steam.",
    ),
    "water_dispenser": _k(
        "equipment",
        "A water dispenser gives drinking water.",
        "water, drinking water, get water, fill a bottle, refill bottle, water dispenser, wasser, trinkwasser, "
        "wasserspender, wasser holen, flasche fuellen",
    ),
    "vending_machine": _k(
        "equipment",
        "A vending machine sells snacks and drinks.",
        "snack, snacks, buy a snack, buy a drink, vending machine, candy, drink, snackautomat, getraenkeautomat, "
        "automat, snack kaufen",
    ),
    "microwave": _k(
        "equipment",
        "A microwave quickly heats up food and drinks.",
        "heat lunch, heat food, warm up food, reheat, microwave, warm up lunch, mikrowelle, essen aufwaermen, "
        "mittagessen aufwaermen, aufwaermen",
        "Do not heat metal or sealed containers.",
    ),
    "fridge": _k(
        "equipment",
        "A fridge keeps food and drinks cold.",
        "cool drinks, keep food cold, store food, cold storage, fridge, refrigerator, kuehlschrank, kuehlen, "
        "essen kuehlen, getraenke kuehlen",
    ),
    "stove": _k(
        "equipment",
        "A stove heats pots and pans for cooking.",
        "cook, cooking, boil, fry, bake, stove, cooker, kochen, herd, braten, kochfeld",
        "Hot surfaces. Never leave it unattended while on.",
    ),
    "dishwasher": _k(
        "equipment",
        "A dishwasher cleans dishes, cups and cutlery.",
        "wash dishes, clean dishes, dishes, dishwasher, wash cups, geschirr spuelen, geschirrspueler, spuelmaschine, "
        "geschirr",
    ),
    "washing_machine": _k(
        "equipment",
        "A washing machine washes clothes and textiles.",
        "wash clothes, do laundry, laundry, washing machine, wash, waesche waschen, waschmaschine, waesche, "
        "kleidung waschen",
    ),
    "hand_dryer": _k(
        "equipment",
        "A hand dryer dries hands with warm air.",
        "dry hands, hand dryer, dry my hands, haende trocknen, haendetrockner, haende abtrocknen",
    ),
    "whiteboard": _k(
        "equipment",
        "A whiteboard is a board for writing and sketching with markers during meetings or teaching.",
        "whiteboard, write on a board, sketch, brainstorm, draw a diagram, flipchart, tafel, weisswandtafel, "
        "an die tafel schreiben, skizzieren",
    ),
    "display_screen": _k(
        "equipment",
        "A display screen shows information, presentations or video to a room.",
        "display, screen, show a presentation, show content, monitor, tv, bildschirm, anzeige, praesentation zeigen, "
        "fernseher",
    ),
    "projector": _k(
        "equipment",
        "A projector shows presentations or video on a screen or wall.",
        "projector, project slides, show slides, beamer, folien zeigen, praesentation projizieren, projektor",
    ),
    "projector_screen": _k(
        "equipment",
        "A projector screen is the surface a projector shows its image on.",
        "projector screen, projection screen, projection surface, leinwand, beamer leinwand, projektionsflaeche",
    ),
    "microscope": _k(
        "equipment",
        "A microscope shows very small things, such as samples or fine parts, enlarged.",
        "microscope, look at a sample, inspect closely, magnify, examine a sample, mikroskop, probe ansehen, "
        "mikroskopieren, vergroessern",
    ),
    "oscilloscope_station": _k(
        "equipment",
        "An oscilloscope station is a work place for measuring and debugging electrical signals.",
        "oscilloscope, measure a signal, measure signals, debug electronics, test electronics, "
        "oszilloskop, signal messen, elektronik testen, elektronik pruefen",
        "Mind the live voltage when probing circuits.",
    ),
    "atm": _k(
        "equipment",
        "An ATM is a cash machine for withdrawing money.",
        "atm, cash machine, withdraw cash, get cash, withdraw money, cashpoint, geldautomat, bargeld abheben, "
        "geld abheben, bankautomat",
    ),
    # ---------- fixtures ----------
    "toilet": _k(
        "fixture",
        "A toilet is a sanitary fixture for personal needs.",
        "toilet, restroom, bathroom, loo, wc, use the toilet, toilette, klo, toilette benutzen, waschraum",
    ),
    "sink": _k(
        "fixture",
        "A sink with a tap is for washing hands or things.",
        "wash hands, wash my hands, sink, tap, rinse, water tap, haende waschen, waschbecken, spuele, wasserhahn",
    ),
    "kitchen_counter": _k(
        "fixture",
        "A kitchen counter is a work surface in a kitchen, often with a sink or cooking appliances.",
        "kitchen counter, prepare food, food preparation, kitchen worktop, counter, kuechenzeile,"
        "essen zubereiten, arbeitsplatte, kueche",
    ),
    "bathtub": _k(
        "fixture",
        "A bathtub is a tub for taking a bath.",
        "bathtub, take a bath, bath, tub, badewanne, baden, wanne",
    ),
    "shower": _k(
        "fixture",
        "A shower is for washing the whole body with running water.",
        "shower, take a shower, wash after work, freshen up, duschen, dusche, duschen gehen",
    ),
    "internal_stairs": _k(
        "fixture",
        "Internal stairs connect two floors inside one room or unit.",
        "stairs, internal stairs, go upstairs, go downstairs, staircase inside, treppe, innentreppe, nach oben gehen, "
        "nach unten gehen",
    ),
    "serving_counter": _k(
        "fixture",
        "A serving counter is where food is handed out, for example in a canteen.",
        "serving counter, get food, get lunch, food counter, canteen counter, food service, essensausgabe, "
        "mittagessen holen, ausgabe, theke",
    ),
    # ---------- furniture ----------
    "chair": _k(
        "furniture",
        "A chair is a seat for one person.",
        "chair, sit, sit down, seat, stuhl, sitzen, sitzplatz",
    ),
    "office_chair": _k(
        "furniture",
        "An office chair is an adjustable seat on wheels for desk work.",
        "office chair, sit at a desk, desk chair, swivel chair, buerostuhl, drehstuhl, am schreibtisch sitzen",
    ),
    "dining_chair": _k(
        "furniture",
        "A dining chair is a seat for eating at a table.",
        "dining chair, sit at a table, sit and eat, eat seated, esszimmerstuhl, am tisch sitzen, essstuhl",
    ),
    "outdoor_chair": _k(
        "furniture",
        "An outdoor chair is a weather-resistant seat for balconies or terraces.",
        "outdoor chair, sit outside, balcony chair, garden chair, terrace seat, gartenstuhl, draussen sitzen, "
        "balkonstuhl",
    ),
    "armchair": _k(
        "furniture",
        "An armchair is a comfortable seat with armrests for relaxing.",
        "armchair, relax, sit comfortably, easy chair, lounge chair, sessel, entspannen, lesesessel",
    ),
    "sofa": _k(
        "furniture",
        "A sofa is a soft seat for several people to relax.",
        "sofa, couch, relax, lounge, lie down, sit comfortably, sofa sitzen, entspannen, ausruhen",
    ),
    "bench": _k(
        "furniture",
        "A bench is a long seat for several people or a place to put things down.",
        "bench, sit on a bench, sit and wait, sitzbank, warten, sitzgelegenheit",
    ),
    "desk": _k(
        "furniture",
        "A desk is a table for working at, usually with a computer or papers.",
        "desk, work at a desk, workplace, work station, computer workplace, schreibtisch, arbeitsplatz, "
        "am schreibtisch arbeiten",
    ),
    "workbench": _k(
        "furniture",
        "A workbench is a sturdy table for manual work such as assembling, repairing or tinkering.",
        "workbench, repair, tinker, manual work, work bench, assemble by hand, werkbank, reparieren, basteln, "
        "handarbeit",
    ),
    "lab_bench": _k(
        "furniture",
        "A lab bench is a work table in a laboratory for experiments and measurements.",
        "lab bench, laboratory bench, experiment, do an experiment, lab work, labortisch, experimentieren, "
        "laborarbeit, versuch",
    ),
    "inspection_bench": _k(
        "furniture",
        "An inspection bench is a table for checking parts and products for quality.",
        "inspect, inspection, inspect a part, quality control, check quality, visual check, pruefen, pruefplatz, "
        "qualitaetskontrolle, kontrollieren",
    ),
    "assembly_station": _k(
        "furniture",
        "An assembly station is a work place where parts are put together into a product.",
        "assemble, assembly, assemble parts, put parts together, assembly station, montage, montieren, "
        "montageplatz, zusammenbauen",
    ),
    "packing_station": _k(
        "furniture",
        "A packing station is a work place for packing goods for shipping.",
        "pack, packing, pack goods, pack a parcel, package, ship goods, shipping, verpacken, paket packen, "
        "packplatz, versand",
    ),
    "tool_cabinet": _k(
        "furniture",
        "A tool cabinet stores hand tools and small equipment.",
        "tool, tools, get a tool, find a tool, hand tools, tool storage, werkzeug, werkzeugschrank, werkzeug holen, "
        "werkzeugkasten",
    ),
    "chemical_cabinet": _k(
        "furniture",
        "A chemical cabinet is a safety cabinet for storing chemicals.",
        "chemical cabinet, store chemicals, chemicals storage, hazardous materials, safety cabinet, chemikalien lagern, "
        "chemikalienschrank, gefahrstoffschrank, gefahrstoffe",
        "Authorised staff only. Keep it closed and never mix chemicals.",
    ),
    "pallet_rack": _k(
        "furniture",
        "A pallet rack is a heavy-duty shelving system for storing goods on pallets.",
        "store pallets, pallet storage, pallet rack, store goods, warehouse storage, palettenregal, paletten lagern, "
        "lagern, hochregal",
    ),
    "shelf": _k(
        "furniture",
        "A shelf is for storing and displaying items.",
        "shelf, shelves, store things, storage, put things away, regal, ablage, regalfach, sachen lagern",
    ),
    "bookshelf": _k(
        "furniture",
        "A bookshelf is for storing books and folders.",
        "bookshelf, books, find a book, store books, folders, buecherregal, buecher, buch finden, buch ausleihen",
    ),
    "paper_shelf": _k(
        "furniture",
        "A paper shelf holds paper and office supplies, often next to a printer.",
        "paper, printer paper, get paper, office supplies, stationery, papier, druckerpapier, papier holen, buerobedarf",
    ),
    "filing_cabinet": _k(
        "furniture",
        "A filing cabinet stores documents and files.",
        "filing cabinet, file documents, store documents, files, archive, aktenschrank, akten, dokumente ablegen, "
        "archiv",
    ),
    "locker": _k(
        "furniture",
        "A locker is a lockable compartment for personal belongings.",
        "locker, store my things, store belongings, lock up my bag, valuables, spind, schliessfach, sachen einschliessen, "
        "tasche einschliessen",
    ),
    "coat_rack": _k(
        "furniture",
        "A coat rack is for hanging up coats and jackets.",
        "coat rack, hang up my coat, hang a jacket, coat, jacket, garderobe, jacke aufhaengen, mantel aufhaengen, "
        "kleiderstaender",
    ),
    "shoe_cabinet": _k(
        "furniture",
        "A shoe cabinet stores shoes.",
        "shoe cabinet, store shoes, shoes, leave my shoes, schuhschrank, schuhe, schuhe abstellen, schuhregal",
    ),
    "wardrobe": _k(
        "furniture",
        "A wardrobe is a tall cabinet for storing clothes.",
        "wardrobe, store clothes, clothes, hang clothes, closet, kleiderschrank, kleidung, schrank",
    ),
    "built_in_wardrobe": _k(
        "furniture",
        "A built-in wardrobe is a fitted closet for storing clothes.",
        "built in wardrobe, fitted wardrobe, built in closet, store clothes, clothes, einbauschrank, "
        "einbaukleiderschrank, kleidung, kleiderschrank",
    ),
    "bed": _k(
        "furniture",
        "A bed is for sleeping, usually for two people.",
        "bed, sleep, double bed, go to sleep, rest, bett, schlafen, doppelbett, ausruhen",
    ),
    "single_bed": _k(
        "furniture",
        "A single bed is for sleeping, for one person.",
        "single bed, sleep, one person bed, go to sleep, rest, einzelbett, schlafen, bett, ausruhen",
    ),
    "nightstand": _k(
        "furniture",
        "A nightstand is a small table next to a bed.",
        "nightstand, bedside table, bedside, put things next to bed, nachttisch, nachtkaestchen, beistelltisch am bett",
    ),
    "plant": _k(
        "furniture",
        "A plant is a decorative or living green element in a room.",
        "plant, plants, greenery, water the plants, flowers, pflanze, pflanzen, blumen, blumen giessen, gruen",
    ),
    "waste_basket": _k(
        "furniture",
        "A waste basket is for throwing away small waste.",
        "waste basket, throw away, trash, rubbish, bin, garbage, trash can, muell, muelleimer, wegwerfen, "
        "abfalleimer, papierkorb",
    ),
    "coffee_table": _k(
        "furniture",
        "A coffee table is a low table in front of a sofa.",
        "coffee table, low table, put a cup down, sofa table, couchtisch, wohnzimmertisch, niedriger tisch",
    ),
    "seminar_table": _k(
        "furniture",
        "A seminar table is a table for group work or classes in a seminar room.",
        "seminar table, group work, class table, workshop table, seminartisch, gruppenarbeit, seminar, kurstisch",
    ),
    "meeting_table": _k(
        "furniture",
        "A meeting table is a large table for meetings.",
        "meeting, meeting table, hold a meeting, team meeting, conference table, besprechung, besprechungstisch, "
        "konferenztisch, sitzung",
    ),
    "dining_table": _k(
        "furniture",
        "A dining table is a table for eating.",
        "dining table, eat, eat at a table, have a meal, esstisch, essen, am tisch essen, mahlzeit",
    ),
    "canteen_table": _k(
        "furniture",
        "A canteen table is a table where people eat their lunch in a canteen.",
        "canteen table, eat lunch, have lunch, lunch, canteen, kantinentisch, mittagessen, mittagspause, kantine",
    ),
    "outdoor_table": _k(
        "furniture",
        "An outdoor table is a weather-resistant table for balconies or terraces.",
        "outdoor table, eat outside, balcony table, garden table, terrace table, gartentisch, draussen essen, "
        "balkontisch",
    ),
    "reading_table": _k(
        "furniture",
        "A reading table is a table for studying or reading, for example in a library.",
        "reading table, read, study, learn, quiet work, lesetisch, lesen, lernen, studieren",
    ),
    "lecture_seating_row": _k(
        "furniture",
        "A seating row is a row of fixed seats for an audience in a lecture hall.",
        "lecture seating, seating row, attend a lecture, listen to a lecture, lecture, auditorium seat, vorlesung, "
        "hoersaal, sitzreihe, vorlesung besuchen",
    ),
    "lectern": _k(
        "furniture",
        "A lectern is a stand for a speaker to hold notes while presenting.",
        "lectern, podium, give a talk, give a lecture, present, speak, rednerpult, pult, vortrag halten, referieren",
    ),
    "reception_desk": _k(
        "furniture",
        "A reception desk is where visitors are greeted and registered.",
        "reception, reception desk, check in, visitor registration, front desk, ask for help, empfang, rezeption, "
        "besucher anmelden, anmeldung",
    ),
    "tv_stand": _k(
        "furniture",
        "A TV stand is a low cabinet that holds a television.",
        "tv stand, television, tv, watch tv, media console, fernseher, tv schrank, fernsehen, tv board",
    ),
}
