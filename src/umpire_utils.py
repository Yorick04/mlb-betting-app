# League Average Run Score for 2026: 9.8
UMPIRE_DATA = {
    # --- HITTER FRIENDLY (High Runs / Small Zones) ---
    "James Jean": 10.5, "Dale Scott": 10.7, "Clint Vondrak": 10.8, "Jen Pawol": 11.3,
    "Andy Fletcher": 10.5, "James Hoye": 10.1, "Hunter Wendelstedt": 10.2, "Edwin Moscoso": 10.4,
    "C.B. Bucknor": 10.2, "Mark Wegner": 10.1, "Carlos Torres": 10.3, "Lance Barksdale": 10.1,
    "Adrian Johnson": 10.2, "Nic Lentz": 10.3, "Shane Livensparger": 10.1, "Alfonso Marquez": 10.4,
    "Ramon De Jesus": 10.2,

    # --- PITCHER FRIENDLY (Low Runs / Wide Zones) ---
    "Emil Jimenez": 8.6, "Mike Estabrook": 8.2, "Ron Kulpa": 7.8, "Will Little": 8.0,
    "Bruce Dreckman": 8.5, "Chris Segal": 8.3, "Dan Merzel": 8.2, "Brennan Miller": 7.8,
    "Austin Jones": 7.5, "Bill Miller": 9.1, "Brian O'Nora": 9.0, "Phil Cuzzi": 8.9,
    "Ryan Blakney": 9.0, "Alex MacKay": 9.1, "Jeremie Rehak": 9.4
}

def get_umpire_multiplier(name):
    return UMPIRE_DATA.get(name, 9.8) / 9.8