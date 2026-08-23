#!/usr/bin/env python3
"""Autonomous per-country coverage gap analyzer. Computes each country's feed
deficit vs a transit-size floor and emits the worst gaps + candidate cities to
synthesize next. Drives the self-perpetuating coverage-grow loop.

Usage: python3 scripts/coverage_gaps.py [top_n]   -> prints JSON {gaps, cities}
"""
import json, os, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")

# transit-size floor (rough # of open operators a country "should" have)
FLOOR = {
    'IN': 200, 'ID': 40, 'CN': 45, 'TR': 40, 'PH': 25, 'PK': 20, 'VN': 20, 'IR': 15,
    'NG': 20, 'SA': 15, 'BD': 15, 'EG': 15, 'EC': 12, 'VE': 12, 'KZ': 12, 'IQ': 8,
    'TZ': 10, 'UG': 8, 'MA': 12, 'BG': 12, 'LK': 10, 'UZ': 10, 'ET': 10, 'DZ': 12,
    'TN': 8, 'JO': 6, 'AZ': 6, 'MM': 8, 'SD': 5, 'DO': 8, 'GT': 8, 'KE': 10, 'GH': 8,
    'BO': 8, 'CI': 6, 'CM': 6, 'SN': 6, 'ZM': 6, 'GE': 6, 'AM': 4, 'MD': 6, 'KH': 5,
    'MZ': 4, 'AO': 5, 'HN': 5, 'NI': 4, 'CR': 6, 'PY': 6, 'SV': 6, 'NP': 6, 'MG': 4,
    'RW': 4, 'MN': 4, 'HT': 3, 'AF': 3, 'SY': 3, 'YE': 3, 'LA': 3, 'MW': 3, 'TD': 2,
}

# major cities per gap country (for synthesis targeting)
CITIES = {
    'IN': ['Surat', 'Kanpur', 'Vadodara', 'Indore', 'Bhopal', 'Coimbatore', 'Visakhapatnam', 'Patna'],
    'ID': ['Jakarta', 'Semarang', 'Makassar', 'Palembang', 'Denpasar', 'Yogyakarta', 'Malang', 'Batam'],
    'CN': ['Chongqing', 'Tianjin', 'Shenzhen', 'Chengdu', 'Dongguan', 'Foshan', 'Harbin', 'Qingdao'],
    'TR': ['Adana', 'Gaziantep', 'Konya', 'Antalya', 'Kayseri', 'Mersin', 'Eskisehir', 'Samsun'],
    'PH': ['Cebu', 'Davao', 'Iloilo', 'Baguio', 'Cagayan de Oro', 'Bacolod', 'Zamboanga'],
    'PK': ['Islamabad', 'Faisalabad', 'Multan', 'Peshawar', 'Rawalpindi', 'Quetta', 'Gujranwala'],
    'VN': ['Hanoi', 'Da Nang', 'Can Tho', 'Hai Phong', 'Bien Hoa', 'Nha Trang', 'Hue'],
    'IR': ['Tehran', 'Mashhad', 'Isfahan', 'Shiraz', 'Tabriz', 'Karaj', 'Qom', 'Ahvaz'],
    'NG': ['Kano', 'Ibadan', 'Port Harcourt', 'Benin City', 'Kaduna', 'Enugu', 'Jos'],
    'SA': ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam'],
    'BD': ['Dhaka', 'Chittagong', 'Khulna', 'Rajshahi', 'Sylhet'],
    'EG': ['Cairo', 'Alexandria', 'Giza', 'Port Said', 'Suez', 'Mansoura'],
    'EC': ['Quito', 'Guayaquil', 'Cuenca', 'Ambato', 'Machala'],
    'VE': ['Caracas', 'Maracaibo', 'Valencia', 'Barquisimeto', 'Maracay'],
    'KZ': ['Almaty', 'Astana', 'Shymkent', 'Karaganda', 'Aktobe'],
    'IQ': ['Baghdad', 'Basra', 'Mosul', 'Erbil', 'Najaf'],
    'TZ': ['Dar es Salaam', 'Dodoma', 'Mwanza', 'Arusha', 'Mbeya'],
    'UG': ['Kampala', 'Gulu', 'Mbarara', 'Jinja'],
    'MA': ['Casablanca', 'Rabat', 'Marrakesh', 'Fez', 'Tangier', 'Agadir'],
    'BG': ['Sofia', 'Plovdiv', 'Varna', 'Burgas', 'Ruse'],
    'LK': ['Colombo', 'Kandy', 'Galle', 'Jaffna', 'Negombo'],
    'UZ': ['Tashkent', 'Samarkand', 'Namangan', 'Andijan', 'Bukhara'],
    'ET': ['Addis Ababa', 'Dire Dawa', 'Mekelle', 'Adama', 'Bahir Dar'],
    'DZ': ['Algiers', 'Oran', 'Constantine', 'Annaba', 'Blida'],
    'TN': ['Tunis', 'Sfax', 'Sousse', 'Kairouan', 'Bizerte'],
    'JO': ['Amman', 'Zarqa', 'Irbid', 'Aqaba'],
    'AZ': ['Baku', 'Ganja', 'Sumqayit', 'Mingachevir'],
    'MM': ['Yangon', 'Mandalay', 'Naypyidaw', 'Bago'],
    'SD': ['Khartoum', 'Omdurman', 'Port Sudan'],
    'DO': ['Santo Domingo', 'Santiago', 'La Romana'],
    'GT': ['Guatemala City', 'Quetzaltenango', 'Escuintla'],
    'KE': ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret'],
    'GH': ['Accra', 'Kumasi', 'Tamale', 'Sekondi-Takoradi'],
    'BO': ['La Paz', 'Santa Cruz', 'Cochabamba', 'El Alto', 'Sucre'],
    'CI': ['Abidjan', 'Bouake', 'Yamoussoukro'],
    'CM': ['Douala', 'Yaounde', 'Bafoussam', 'Garoua'],
    'SN': ['Dakar', 'Touba', 'Thies', 'Saint-Louis'],
    'ZM': ['Lusaka', 'Kitwe', 'Ndola', 'Kabwe'],
    'GE': ['Tbilisi', 'Batumi', 'Kutaisi', 'Rustavi'],
    'AM': ['Yerevan', 'Gyumri', 'Vanadzor'],
    'MD': ['Chisinau', 'Balti', 'Tiraspol'],
    'KH': ['Phnom Penh', 'Siem Reap', 'Battambang'],
    'AO': ['Luanda', 'Huambo', 'Lobito'],
    'HN': ['Tegucigalpa', 'San Pedro Sula'],
    'CR': ['San Jose', 'Alajuela', 'Cartago'],
    'PY': ['Asuncion', 'Ciudad del Este', 'Encarnacion'],
    'SV': ['San Salvador', 'Santa Ana', 'San Miguel'],
    'NP': ['Kathmandu', 'Pokhara', 'Biratnagar'],
    'RW': ['Kigali', 'Butare', 'Gisenyi'],
    'MN': ['Ulaanbaatar', 'Erdenet', 'Darkhan'],
    'MG': ['Antananarivo', 'Toamasina', 'Antsirabe'],
}


def main():
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    d = json.load(open(SRC))
    c = Counter(f.get("cc") for f in d
                if f.get("status") not in ("deprecated", "inactive")
                and (f.get("producer_url") or f.get("hosted_url")))
    gaps = sorted([(cc, c.get(cc, 0), fl, fl - c.get(cc, 0))
                   for cc, fl in FLOOR.items() if c.get(cc, 0) < fl],
                  key=lambda x: -x[3])
    top = gaps[:top_n]
    # build a synthesis city list: worst countries, cities not likely already covered
    covered = set()
    for f in d:
        cc = f.get("cc")
        city = (f.get("city") or "").strip().lower()
        if cc and city:
            covered.add((cc, city))
    cities = []
    for cc, have, fl, deficit in top:
        for city in CITIES.get(cc, []):
            if (cc, city.lower()) in covered:
                continue
            cities.append([cc, city])
    out = {"gaps": [{"cc": cc, "have": h, "floor": fl, "deficit": g} for cc, h, fl, g in top],
           "cities": cities[:40], "total_deficit": sum(g for _, _, _, g in gaps)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
