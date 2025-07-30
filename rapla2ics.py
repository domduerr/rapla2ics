import os
from flask import Flask, send_file
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from waitress import serve
import pytz

HTML_SOURCE_URL = os.environ.get("HTML_SOURCE_URL")
HOST = os.environ.get("HOST")
PORT = int(os.environ.get("PORT"))
ROUTE_PATH = os.environ.get("ROUTE_PATH")
LOCAL_TIMEZONE = os.environ.get("LOCAL_TIMEZONE")


CACHE_DIR = "/data"
CACHE_FILE = f"{CACHE_DIR}/calendar.ics"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 1 day

app = Flask(__name__)

def fetch_and_generate_ics(url, output_ics):
    try:
        response = requests.get(url)
        response.encoding = 'ISO-8859-1'
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch HTML: {e}")
        return False

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', class_='export')
    if not table:
        print("No table with class 'export' found.")
        return False

    rows = table.find_all('tr')[1:]
    calendar = Calendar()

    local_tz = pytz.timezone('Europe/Berlin')

    for row in rows:
        cols = [td.get_text(strip=True) for td in row.find_all('td')]
        if len(cols) < 3:
            continue

        title = cols[0]

        if title.lower().startswith("abwesenheit"):
            continue

        start = cols[1]
        end = cols[2]
        course = cols[3]
        location = cols[5] if len(cols) > 5 else ""

        try:
            naive_start_dt = datetime.strptime(start, "%d.%m.%Y %H:%M")
            naive_end_dt = datetime.strptime(end, "%d.%m.%Y %H:%M")

            start_dt = local_tz.localize(naive_start_dt)
            end_dt = local_tz.localize(naive_end_dt)
        except ValueError:
            print(f"Skipping invalid date: {title}")
            continue

        event = Event()
        event.name = title
        event.begin = start_dt
        event.end = end_dt
        event.location = location
        event.description = f"Kurs: {course}"

        calendar.events.add(event)

    with open(output_ics, 'w', encoding='utf-8') as f:
        f.writelines(calendar)

    print(f"Updated: {output_ics}")
    return True

def is_cache_stale(file_path, ttl_seconds):
    if not os.path.exists(file_path):
        return True
    file_age = time.time() - os.path.getmtime(file_path)
    return file_age > ttl_seconds

@app.route(ROUTE_PATH)
def serve_ics():
    regenerate_needed = is_cache_stale(CACHE_FILE, CACHE_TTL_SECONDS)

    if regenerate_needed:
        print("Cache expired. Trying to regenerate ICS file...")
        success = fetch_and_generate_ics(HTML_SOURCE_URL, CACHE_FILE)
        if not success:
            if os.path.exists(CACHE_FILE):
                print("Source failed, but serving stale cached file.")
                return send_file(CACHE_FILE, as_attachment=False, mimetype='text/calendar')
            else:
                return "Failed to fetch and no cache available.", 500
    else:
        print("Serving fresh cached ICS.")

    return send_file(CACHE_FILE, as_attachment=False, mimetype='text/calendar')

if __name__ == "__main__":
    serve(app, host=HOST, port=PORT)
    # app.run(host=HOST, port=PORT)
