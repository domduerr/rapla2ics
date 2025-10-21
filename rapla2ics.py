import os
from flask import Flask, send_file
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from waitress import serve
import pytz
import caldav # Import der neuen Bibliothek
from caldav.elements import dav, cdav
from urllib.parse import unquote



HTML_SOURCE_URL = os.environ.get("HTML_SOURCE_URL")
HOST = os.environ.get("HOST")
PORT = int(os.environ.get("PORT"))
ROUTE_PATH = os.environ.get("ROUTE_PATH")
MERGED_ROUTE_PATH = os.environ.get("MERGED_ROUTE_PATH")
LOCAL_TIMEZONE = os.environ.get("LOCAL_TIMEZONE")


CACHE_DIR = "/data"
CACHE_FILE = f"{CACHE_DIR}/calendar.ics"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 1 day
CACHE_TIMEOUT_SECONDS = 24 * 60 * 60 * 2  # 2 days
MERGED_CACHE_FILE = f"{CACHE_DIR}/merged_calendar.ics"

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


def ensure_cache_updated():
    regenerate_needed = is_cache_stale(CACHE_FILE, CACHE_TTL_SECONDS)

    if regenerate_needed:
        print("Cache expired. Trying to regenerate ICS file...")
        success = fetch_and_generate_ics(HTML_SOURCE_URL, CACHE_FILE)
        if not success:
            if os.path.exists(CACHE_FILE):
                if (time.time() - os.path.getmtime(CACHE_FILE)) > CACHE_TIMEOUT_SECONDS:
                    return "Failed to fetch new data and cache is to old.", 500
            else:
                return "Failed to fetch and no cache available.", 500
    return None # No error


def ensure_merged_cache_updated():
    regenerate_needed = is_cache_stale(MERGED_CACHE_FILE, CACHE_TTL_SECONDS)

    if regenerate_needed:
        print("Merged cache expired. Trying to regenerate merged ICS file...")
        external_sources = get_external_sources_from_env()
        success = get_merged_calendar(CACHE_FILE, external_sources, MERGED_CACHE_FILE)
        if not success:
            if os.path.exists(MERGED_CACHE_FILE):
                if (time.time() - os.path.getmtime(MERGED_CACHE_FILE)) > CACHE_TIMEOUT_SECONDS:
                    return "Failed to fetch new data and merged cache is to old.", 500
            else:
                return "Failed to fetch and no merged cache available.", 500
    return None # No error


def get_external_sources_from_env():
    sources = []
    i = 1
    while True:
        url = os.environ.get(f'EXTERNAL_{i}_URL')
        if not url:
            break

        username = os.environ.get(f'EXTERNAL_{i}_USERNAME')
        password = os.environ.get(f'EXTERNAL_{i}_PASSWORD')

        sources.append({'url': url, 'username': username, 'password': password})
        i += 1
    return sources

def get_merged_calendar(local_calendar_path, external_sources, output_ics):
    try:
        with open(local_calendar_path, 'r', encoding='utf-8') as f:
            local_cal = Calendar(f.read())
    except FileNotFoundError:
        local_cal = Calendar()

    for source in external_sources:
        url = source.get('url')
        username = source.get('username')
        password = source.get('password')

        if not url:
            continue

        # --- Case 1: CalDAV source (requires authentication) ---
        if username and password:
            print(f"Fetching from CalDAV source: {url}")
            try:
                client = caldav.DAVClient(url=url, username=username, password=password)
                principal = client.principal()

                calendar_to_sync = None
                calendars = principal.calendars()

                if calendars:
                    # Normalize the target URL to handle potential trailing slashes
                    normalized_target_url = url.strip('/')

                    # Iterate through all available calendars to find the correct one by its URL.
                    for cal in calendars:
                        decoded_cal_url = unquote(str(cal.url)).strip('/')
                        if decoded_cal_url == normalized_target_url:
                            calendar_to_sync = cal
                            print(f"SUCCESS: Found matching calendar by URL: {calendar_to_sync.name}")
                            break  # Exit the loop once the match is found

                    # Fallback if no calendar with a matching URL was found.                    if not calendar_to_sync:
                        print(f"Could not find a calendar with the URL '{url}'. Falling back to the first available calendar.")
                        calendar_to_sync = calendars[0]
                        print(f"Fallback successful, using first calendar: {calendar_to_sync.name}")

                if calendar_to_sync:
                    event_list = calendar_to_sync.events()
                    print(f"Found {len(event_list)} events in the calendar.")

                    for event_vcal in event_list:
                        external_cal = Calendar(event_vcal.data)
                        for event in external_cal.events:
                            local_cal.events.add(event)
                else:
                    print(f"Error: No calendars could be found for user {username}.")
                    return False

            except Exception as e:
                print(f"Failed to fetch or parse CalDAV from {url}: {e}")
                return False

        # --- Case 2: Simple ICS URL (no authentication) ---
        else:
            print(f"Fetching from ICS URL: {url}")
            try:
                response = requests.get(url)
                response.raise_for_status()
                external_cal = Calendar(response.text)
                for event in external_cal.events:
                    local_cal.events.add(event)
            except requests.RequestException as e:
                print(f"Failed to fetch external ICS from {url}: {e}")
                return False
            except Exception as e:
                print(f"Failed to parse external ICS from {url}: {e}")
                return False

    try:
        with open(output_ics, 'w', encoding='utf-8') as f:
            f.write(local_cal.serialize())
    except Exception as e:
        print(f"Failed to write merged calendar file to {output_ics}: {e}")
        return False

    print(f"Successfully updated: {output_ics}")
    return True


@app.route(ROUTE_PATH)
def serve_ics():
    error = ensure_cache_updated()
    if error:
        return error
    print("Serving fresh cached ICS.")
    return send_file(CACHE_FILE, as_attachment=False, mimetype='text/calendar')


@app.route(MERGED_ROUTE_PATH)
def serve_merged_ics():
    error = ensure_cache_updated()
    if error:
        return error

    error = ensure_merged_cache_updated()
    if error:
        return error

    print("Serving fresh cached merged ICS.")
    return send_file(MERGED_CACHE_FILE, as_attachment=False, mimetype='text/calendar')


if __name__ == "__main__":
    serve(app, host=HOST, port=PORT)
    # app.run(host=HOST, port=PORT)
