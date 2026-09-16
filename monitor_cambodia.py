import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from babel import Locale
from playwright.sync_api import sync_playwright


URL = "https://www.cambodiapost.com.kh/calculate/international"
COUNTRY_API = "https://www.cambodiapost.com.kh/select2/getAllCountries"

DEBUG_HTML = Path("debug_single_country.html")
DEBUG_PNG = Path("debug_single_country.png")
DEBUG_API = Path("debug_single_country_api.json")

WEIGHT = "0.02"

KHMER_LOCALE = Locale("km")
ENGLISH_LOCALE = Locale("en")


def log(message=""):
    print(message, flush=True)


def fetch_json(url, timeout=60):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def extract_country_code(text):
    match = re.match(
        r"^\s*([A-Z]{2})\s*\(",
        text or "",
    )

    return match.group(1) if match else ""


def get_country_name(code, locale, fallback):
    if not code:
        return fallback

    try:
        value = locale.territories.get(code)

        if value:
            return value
    except Exception:
        pass

    return fallback


def find_united_states(records):
    for record in records:
        if not isinstance(record, dict):
            continue

        text = str(
            record.get("text", "")
        ).strip()

        code = extract_country_code(text)

        if code == "US":
            return record

        if "UNITED STATES" in text.upper():
            return record

    return None


def fetch_all_country_records():
    log("=" * 60)
    log("FETCHING COUNTRY API")
    log("=" * 60)

    records = []

    page_number = 1
    last_page = None

    while True:
        url = (
            f"{COUNTRY_API}?page={page_number}"
        )

        log(
            f"Fetching API page {page_number}..."
        )

        data = fetch_json(url)

        page_records = data.get(
            "data",
            [],
        )

        log(
            f"  Received {len(page_records)} records."
        )

        records.extend(page_records)

        meta = data.get(
            "meta",
            {},
        )

        if isinstance(meta, dict):
            try:
                last_page = int(
                    meta.get("last_page")
                )
            except Exception:
                last_page = None

        if last_page is not None:
            if page_number >= last_page:
                break
        elif not page_records:
            break

        page_number += 1

    log(
        f"TOTAL COUNTRY RECORDS: {len(records)}"
    )

    return records


def find_country_select(page):
    select = page.locator(
        "#country_id"
    )

    if select.count() == 0:
        raise RuntimeError(
            "Could not find #country_id"
        )

    return select.first


def find_weight_input(page):
    selectors = [
        "input[name='weight']",
        "input[id='weight']",
        "input[type='number']",
        "input[placeholder*='ទម្ងន់']",
    ]

    for selector in selectors:
        locator = page.locator(selector)

        for i in range(locator.count()):
            candidate = locator.nth(i)

            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                pass

    raise RuntimeError(
        "Could not find weight input."
    )


def find_calculate_button(page):
    candidates = page.locator(
        "button, input[type='submit'], "
        "input[type='button'], a"
    )

    for i in range(candidates.count()):
        candidate = candidates.nth(i)

        try:
            if not candidate.is_visible():
                continue

            text = (
                candidate.inner_text(
                    timeout=2000
                )
                .strip()
                .lower()
            )

            value = (
                candidate.get_attribute("value")
                or ""
            ).strip().lower()

            combined = f"{text} {value}"

            if (
                "calculate" in combined
                or "គណនា" in combined
            ):
                return candidate

        except Exception:
            pass

    raise RuntimeError(
        "Could not find Calculate button."
    )


def add_country_option(
    page,
    country_id,
    country_text,
):
    result = page.evaluate(
        """
        ({countryId, countryText}) => {
            const select =
                document.querySelector('#country_id');

            if (!select) {
                return {
                    ok: false,
                    reason: 'select not found'
                };
            }

            let option =
                Array.from(select.options).find(
                    o => String(o.value) === String(countryId)
                );

            if (!option) {
                option =
                    document.createElement('option');

                option.value =
                    String(countryId);

                option.textContent =
                    countryText;

                select.appendChild(option);
            }

            option.selected = true;
            select.value = String(countryId);

            if (window.jQuery) {
                window.jQuery(select)
                    .val(String(countryId))
                    .trigger("change");
            } else {
                select.dispatchEvent(
                    new Event(
                        "change",
                        {bubbles: true}
                    )
                );
            }

            return {
                ok: true,
                value: select.value,
                text: option.textContent
            };
        }
        """,
        {
            "countryId": str(country_id),
            "countryText": str(country_text),
        },
    )

    if not result.get("ok"):
        raise RuntimeError(
            f"Could not select country: {result}"
        )

    log(
        f"Selected country value: "
        f"{result.get('value')}"
    )


def main():
    log("")
    log("=" * 60)
    log("CAMBODIA POST SINGLE COUNTRY DIAGNOSTIC")
    log("=" * 60)

    log(
        f"Started: "
        f"{datetime.now(timezone.utc).isoformat()}"
    )

    records = fetch_all_country_records()

    country = find_united_states(records)

    if country is None:
        raise RuntimeError(
            "United States was not found in country API."
        )

    country_id = country.get("id")
    country_text = country.get("text")

    log("")
    log("=" * 60)
    log("TEST COUNTRY")
    log("=" * 60)

    log(
        f"Country API ID: {country_id}"
    )

    log(
        f"Country API text: {country_text}"
    )

    code = extract_country_code(
        str(country_text)
    )

    english_name = get_country_name(
        code,
        ENGLISH_LOCALE,
        str(country_text),
    )

    khmer_name = get_country_name(
        code,
        KHMER_LOCALE,
        english_name,
    )

    log(
        f"English name: {english_name}"
    )

    log(
        f"Khmer name: {khmer_name}"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            }
        )

        page = context.new_page()

        page.set_default_timeout(15000)

        log("")
        log("=" * 60)
        log("OPENING CAMBODIA POST")
        log("=" * 60)

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        log(
            f"Loaded: {page.url}"
        )

        page.wait_for_timeout(3000)

        log("")
        log("Adding United States to Select2...")

        add_country_option(
            page,
            country_id,
            country_text,
        )

        weight = find_weight_input(page)

        log(
            "Entering weight: 0.02 kg"
        )

        weight.fill(
            WEIGHT
        )

        log(
            f"Weight value now: "
            f"{weight.input_value()}"
        )

        calculate = find_calculate_button(page)

        log("")
        log(
            "CLICKING CALCULATE..."
        )

        calculate.click()

        log(
            "Calculate clicked."
        )

        log("")
        log(
            "Waiting 5 seconds for result..."
        )

        page.wait_for_timeout(5000)

        log("")
        log("=" * 60)
        log("PAGE TEXT AFTER CALCULATION")
        log("=" * 60)

        text = page.locator(
            "body"
        ).inner_text()

        print(text, flush=True)

        log("")
        log("=" * 60)
        log("HTML AFTER CALCULATION")
        log("=" * 60)

        html = page.content()

        DEBUG_HTML.write_text(
            html,
            encoding="utf-8",
        )

        log(
            f"Saved HTML: {DEBUG_HTML}"
        )

        page.screenshot(
            path=str(DEBUG_PNG),
            full_page=True,
        )

        log(
            f"Saved screenshot: {DEBUG_PNG}"
        )

        DEBUG_API.write_text(
            json.dumps(
                country,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        log(
            f"Saved country API record: {DEBUG_API}"
        )

        log("")
        log("=" * 60)
        log("DIAGNOSTIC COMPLETE")
        log("=" * 60)

        context.close()
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
