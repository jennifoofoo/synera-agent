"""English room names for the Urban Colab (Wanda speaks English, the building's own signs are English). Ids stay."""
import json, sys
P = "plan-89323a15-"
NAMES = {
    "F0-S001": "Project Room West", "F0-S003": "West Corridor", "F0-S004": "Changing Room West", "F0-S005": "IT Room",
    "F0-S006": "Electrical Room", "F0-S007": "Storage by the Lift", "F0-S008": "Lift", "F0-S009": "South Corridor",
    "F0-S010": "Storage Foyer", "F0-S011": "Main Stairs", "F0-S014": "Café", "F0-S015": "North Corridor",
    "F0-S016": "Office", "F0-S017": "Storage North", "F0-S018": "Waste Room", "F0-S019": "Changing Room East",
    "F0-S020": "Toilets", "F0-S021": "Toilets", "F0-S022": "Toilets", "F0-S023": "East Corridor",
    "F1-S001": "Work Area", "F1-S003": "Cleaning Room", "F1-S004": "IT Room", "F1-S005": "Toilets", "F1-S006": "Toilets",
    "F1-S007": "Lift", "F1-S008": "Storage", "F1-S009": "First Floor Corridor", "F1-S010": "West Stairs",
    "F1-S011": "Main Stairs", "F1-S012": "Terrace", "F1-S014": "Void", "F1-S015": "Kitchenette",
    "F1-S016": "Retail Living Lab", "F1-S017": "Void",
}
path = sys.argv[1]
b = json.load(open(path))
changed = []
for s in b["spaces"]:
    k = s["id"].replace(P, "")
    if k in NAMES and s["name"] != NAMES[k]:
        changed.append((k, s["name"], NAMES[k])); s["name"] = NAMES[k]
json.dump(b, open(path, "w"), ensure_ascii=False, indent=1)
for c in changed: print(*c, sep="  ")
print(len(changed), "renamed;", sorted({s["name"] for s in b["spaces"]}))
