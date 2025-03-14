#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "google-api-python-client",
#     "google-auth-httplib2",
#     "google-auth-oauthlib",
#     "selenium",
#     "webdriver_manager",
#     "pydantic",
# ]
# ///
import argparse
import datetime
import os.path
import subprocess
import tempfile
import threading
from datetime import time
from http.server import HTTPServer
from http.server import SimpleHTTPRequestHandler
from pprint import pprint
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager


# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class Event(BaseModel):
    title: str
    startTime: time
    endTime: time
    status: str | None = None
    optional: bool = False

    class Config:
        json_encoders = {time: lambda t: t.strftime("%H:%M")}


class Calendar(BaseModel):
    events: list[Event] = []
    currentDay: dict[str, Any]
    workingHours: dict[str, int]

    class Config:
        json_encoders = {time: lambda t: t.strftime("%H:%M")}


def capture(url: str, output_file: str, width: int, height: int):
    options = Options()
    for argument in [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--hide-scrollbars",
        "--disable-extensions",
        "--disable-web-security",
        "--allow-running-insecure-content",
        "--force-device-scale-factor=1",
        "--high-dpi-support=1",
        "--proxy-server='direct://'",
        "--proxy-bypass-list=*",
    ]:
        options.add_argument(argument)

    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=options,
    )
    window_size = driver.execute_script(
        """
        return [window.outerWidth - window.innerWidth + arguments[0],
          window.outerHeight - window.innerHeight + arguments[1]];
        """,
        width,
        height,
    )
    driver.set_window_size(*window_size)

    driver.get(url)

    filename = output_file
    driver.save_screenshot(filename)
    driver.close()


def get_todays_events(target_date: datetime.datetime) -> list[Event]:
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)

        # Get the start and end of today in the user's timezone
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + datetime.timedelta(days=1)

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_of_day.isoformat() + "Z",
                timeMax=end_of_day.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            print("No events found for today.")
            return []

        output = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))

            # Convert to datetime objects
            start_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))

            # Format as HH:MM
            start_time = start_dt.strftime("%H:%M")
            end_time = end_dt.strftime("%H:%M")

            if start_time == end_time:
                continue

            if my_attendance := [
                x for x in event.get("attendees", []) if x.get("self")
            ]:
                attendance = my_attendance[0]
            else:
                attendance = {}

            # Convert HH:MM strings to time objects
            start_time_obj = datetime.datetime.strptime(start_time, "%H:%M").time()
            end_time_obj = datetime.datetime.strptime(end_time, "%H:%M").time()

            output.append(
                Event(
                    title=event.get("summary", "(No title)"),
                    startTime=start_time_obj,
                    endTime=end_time_obj,
                    status=attendance.get("responseStatus"),
                    optional=event.get("optional", False),
                )
            )

        return output

    except Exception as e:
        print(f"An error occurred: {e}")
        return []


def get_calendar_data(day_start, day_end) -> Calendar:
    today = datetime.datetime.now()
    return Calendar(
        currentDay={"name": today.strftime("%A"), "date": today.day},
        workingHours={"start": day_start, "end": day_end},
        events=get_todays_events(today),
    )


def parse_arguments():
    parser = argparse.ArgumentParser(description="Generate calendar image.")
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        default=540,
        help="Width of the output image (default 960)",
    )
    parser.add_argument(
        "-g",
        "--height",
        type=int,
        default=960,
        help="Height of the output image (default 540)",
    )
    parser.add_argument(
        "output",
        type=str,
        help="Output file path for the generated image",
    )
    parser.add_argument(
        "-s",
        "--day-start",
        type=int,
        default=10,
        help="24-hour format hour when the workday starts (default: 10)",
    )
    parser.add_argument(
        "-e",
        "--day-end",
        type=int,
        default=18,
        help="24-hour format hour when the workday ends (default: 18)",
    )
    args = parser.parse_args()

    if not 0 <= args.day_start <= 24:
        parser.error("Day start must be between 0 and 24.")
    if not 0 <= args.day_end <= 24:
        parser.error("Day end must be between 0 and 24.")
    if args.day_start >= args.day_end:
        parser.error("Day start must be before day end.")

    return args


def main():
    args = parse_arguments()
    with open("calendar.html", "r") as file:
        calendar_html = file.read()

    calendar = get_calendar_data(args.day_start, args.day_end)
    pprint(calendar)

    updated_html = calendar_html.replace(
        "{{calendarDataJSON}}", calendar.model_dump_json()
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False
    ) as temp_file:
        temp_file.write(updated_html)
        temp_file_name = temp_file.name

    def serve_file(file_path):
        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                with open(file_path, "rb") as file:
                    self.wfile.write(file.read())

        httpd = HTTPServer(("", 33597), Handler)
        print(f"Serving {file_path} on http://localhost:33597")
        httpd.serve_forever()

    server_thread = threading.Thread(target=serve_file, args=(temp_file_name,))
    server_thread.daemon = True
    server_thread.start()

    print("Server is ready. Proceeding with gowitness...")

    try:
        capture(
            "http://localhost:33597/calendar.html", args.output, args.width, args.height
        )
    except subprocess.CalledProcessError as e:
        print(f"Error capturing screenshot: {e}")
    finally:
        os.unlink(temp_file_name)


if __name__ == "__main__":
    main()
