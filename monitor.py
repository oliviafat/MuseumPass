import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from playwright.sync_api import sync_playwright

PASS_URL = "https://rooms.kcls.org/passes/8e456682901d"
PASS_NAME = "Seattle Aquarium Museum Pass (KCLS)"


def check_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(PASS_URL, wait_until="networkidle", timeout=30000)

        # Wait for the loading spinner to disappear
        try:
            page.wait_for_selector("text=Working...", state="hidden", timeout=15000)
        except Exception:
            pass  # may not appear if content loaded fast

        # Give JS a moment to finish rendering the calendar
        page.wait_for_timeout(2000)

        html = page.content()
        browser.close()
        return html


def find_available_dates(html):
    """
    LibCal renders available calendar days with a link and an availability count.
    This looks for patterns like '3 available' or 'X of Y available', and also
    for LibCal CSS classes that mark open slots.
    Returns a list of human-readable strings describing what's available.
    """
    found = []

    # Pattern: "N available" where N > 0
    for m in re.finditer(r"(\d+)\s+(?:of\s+\d+\s+)?available", html, re.IGNORECASE):
        count = int(m.group(1))
        if count > 0:
            # Grab surrounding context (up to 120 chars) for the notification
            start = max(0, m.start() - 60)
            end = min(len(html), m.end() + 60)
            snippet = re.sub(r"<[^>]+>", " ", html[start:end]).strip()
            snippet = re.sub(r"\s+", " ", snippet)
            found.append(snippet)

    # LibCal calendar cells: class="s-lc-cal-av" marks available days
    av_cells = re.findall(
        r'class="[^"]*s-lc-cal-av[^"]*"[^>]*>.*?</td>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    for cell in av_cells:
        text = re.sub(r"<[^>]+>", " ", cell).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            found.append(text)

    return found


def send_email(available_info: list[str]):
    sender = os.environ["GMAIL_ADDRESS"]
        # Gmail App Password (16-char, generated at myaccount.google.com > Security > App Passwords)
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"[KCLS] Museum Pass Available — Act Fast!"

    snippets = "\n".join(f"  • {s}" for s in available_info[:10])
    body = f"""\
Museum passes are now available for {PASS_NAME}!

{snippets}

Book now before they're gone:
{PASS_URL}

---
This is an automated notification. You will receive another email
the next time availability is detected.
"""
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print("Notification email sent.")


def main():
    print(f"Fetching: {PASS_URL}")
    html = check_availability()

    available = find_available_dates(html)

    if available:
        print(f"Availability detected ({len(available)} item(s)). Sending email...")
        send_email(available)
    else:
        print("No availability found.")


if __name__ == "__main__":
    main()
