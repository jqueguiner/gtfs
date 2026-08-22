#!/usr/bin/env python3
"""LLM normalization stage: turn a NON-GTFS source (a scraped HTML timetable,
a PDF schedule, a CSV route list) into a valid GTFS feed.zip.

Many small operators — especially outside FR/US — publish schedules only as
web pages or PDFs. This stage feeds the raw text/tables to an LLM with a strict
GTFS schema and emits stops.txt / routes.txt / trips.txt / stop_times.txt /
calendar.txt, then zips them into feeds/<id>.zip and writes a feed.json with
"source":"llm-normalized" + "confidence" so it can be reviewed before merge.

Set ANTHROPIC_API_KEY. Model: claude-opus-4-8 (latest, best table/schedule
reasoning). This is the scaffold + contract; wire it to your scraped inputs.
"""
import json, os, sys, io, zipfile

MODEL = "claude-opus-4-8"

GTFS_CONTRACT = """You convert a transit operator's published schedule into GTFS.
Return STRICT JSON with keys: agency, stops, routes, trips, stop_times, calendar.
- agency: {agency_id, agency_name, agency_url, agency_timezone}
- stops[]: {stop_id, stop_name, stop_lat, stop_lon}   (geocode names to lat/lon; null if unknown)
- routes[]: {route_id, route_short_name, route_long_name, route_type}  (route_type: 3=bus,0=tram,1=metro,2=rail,4=ferry)
- trips[]: {route_id, service_id, trip_id, trip_headsign, direction_id}
- stop_times[]: {trip_id, arrival_time, departure_time, stop_id, stop_sequence}  (HH:MM:SS, >24h allowed for after-midnight)
- calendar[]: {service_id, monday..sunday (0/1), start_date, end_date}  (YYYYMMDD)
Never invent stops not in the source. Emit a "confidence" 0..1 and "notes" listing gaps."""

FILES = {
    "agency": ["agency_id", "agency_name", "agency_url", "agency_timezone"],
    "stops": ["stop_id", "stop_name", "stop_lat", "stop_lon"],
    "routes": ["route_id", "route_short_name", "route_long_name", "route_type"],
    "trips": ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"],
    "stop_times": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
    "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday", "start_date", "end_date"],
}


def call_llm(raw_text, agency_hint):
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=MODEL, max_tokens=16000,
        system=GTFS_CONTRACT,
        messages=[{"role": "user", "content": f"Operator: {agency_hint}\n\nSOURCE SCHEDULE:\n{raw_text}\n\nReturn the GTFS JSON."}],
    )
    txt = msg.content[0].text
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])


def to_gtfs_zip(data, out_zip):
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name, cols in FILES.items():
            rows = data.get(name)
            rows = [rows] if isinstance(rows, dict) else (rows or [])
            buf = io.StringIO()
            buf.write(",".join(cols) + "\n")
            for r in rows:
                buf.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
            z.writestr(f"{name}.txt", buf.getvalue())


def normalize(raw_text, agency_hint, feed_id, out_dir):
    data = call_llm(raw_text, agency_hint)
    os.makedirs(out_dir, exist_ok=True)
    zp = os.path.join(out_dir, f"{feed_id}.zip")
    to_gtfs_zip(data, zp)
    json.dump({"agency": {"name": agency_hint}, "feed": {"format": "gtfs", "file": os.path.basename(zp)},
               "source": "llm-normalized", "confidence": data.get("confidence"), "notes": data.get("notes")},
              open(os.path.join(out_dir, "feed.json"), "w"), indent=2, ensure_ascii=False)
    print(f"{feed_id}: GTFS zip written (confidence {data.get('confidence')})")
    return zp


if __name__ == "__main__":
    # demo: echo the contract; real use imports normalize() from the scrape pipeline
    print(GTFS_CONTRACT)
