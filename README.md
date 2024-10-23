# Calumny

Calumny is a calendar renderer for e-ink displays. It's meant to render your calendar
from an iCal export, so you can display it on any kind of e-ink display. It's designed
for high-contrast viewing, with black-and-white or three-color displays.

Here's an example of how the rendered calendar looks:

![](misc/screenshot.png)


## How it works

Calumny uses the Google Calendar API to get the day's events. Follow [Google's
instructions](https://developers.google.com/calendar/api/quickstart/python) to get
a file with credentials, which you put in the same directory as Calumny, and which it
will use to fetch the events.

When you run `calumny.py`, Calumny will fetch the events, put them into `calendar.html`,
write a temporary file with the resulting output, and then use Selenium with Chrome to
take a screenshot of the page.

To then send the screenshot to your display, you can use whatever program you want.


## Usage

To use Calumny, run `python calumny.py <outfile.png>`. If you have
[uv](https://github.com/astral-sh/uv) installed, you can run it as `./calumny.py
<outfile.png>`, which will automatically create a virtual environment and install
Calumny's dependencies.

You can customize your working hours (so Calumny only shows from your starting to your
ending times), as well as your display's resolution.
