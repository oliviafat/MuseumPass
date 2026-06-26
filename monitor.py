import glob
import os
import re
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from playwright.sync_api import sync_playwright

PASS_URL = "https://rooms.kcls.org/passes/8e456682901d"
PASS_NAME = "Seattle Aquarium Museum Pass (KCLS)"


def wait_for_calendar(page):
    try:
        page.wait_for_selector("text=Working...", state="hidden", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1500)


def check_availability():
    html_chunks = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(PASS_URL, wait_until="networkidle", timeout=30000)

        wait_for_calendar(page)

        # Capture current month
        html_chunks.append(page.content())
        page.screenshot(path="screenshot_month1.png", full_page=True)

        # Navigate to next month
        next_btn = (
            page.locator("button:has-text('Next')").first
            or page.locator("[aria-label='Next']").first
            or page.locator(".s-lc-cal-next").first
        )
        try:
            next_btn.click(timeout=5000)
            wait_for_calendar(page)
            html_chunks.append(page.content())
            page.screenshot(path="screenshot_month2.png", full_page=True)
        except Exception:
            print("Warning: could not navigate to next month.")

        browser.close()

    return "\n".join(html_chunks)


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
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    has_availability = bool(available_info)

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = (
        "[KCLS] Museum Pass Available — Act Fast!"
        if has_availability
        else "[KCLS] Monitor Check — No Availability"
    )

    if has_availability:
        snippets = "\n".join(f"  • {s}" for s in available_info[:10])
        body = f"""\
Museum passes are now available for {PASS_NAME}!

{snippets}

Book now before they're gone:
{PASS_URL}
"""
    else:
        body = f"""\
Routine check complete — no passes available right now for {PASS_NAME}.

Screenshots of both months are attached.

{PASS_URL}
"""

    msg.attach(MIMEText(body, "plain"))

    for path in sorted(glob.glob("screenshot_month*.png")):
        with open(path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-Disposition", "attachment", filename=os.path.basename(path))
            msg.attach(img)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print("Email sent.")


def main():
    print(f"Fetching: {PASS_URL}")
    html = check_availability()

    available = find_available_dates(html)

    if available:
        print(f"Availability detected ({len(available)} item(s)).")
    else:
        print("No availability found.")

    send_email(available)


if __name__ == "__main__":
    main()
