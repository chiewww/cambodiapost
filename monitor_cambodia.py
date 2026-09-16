import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from babel import Locale
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# CONFIGURATION
# ============================================================

URL = "https://www.cambodiapost.com.kh/calculate/international"

COUNTRY_API = (
    "https://www.cambodiapost.com.kh/select2/getAllCountries"
)

CALCULATION_ENDPOINT = (
    "/delivery_service/services/calculate_item_total_cost_multi"
)

OUTPUT_FILE = Path("output_cambodia.txt")

DEBUG_HTML = Path("debug_cambodiapost.html")
DEBUG_PNG = Path("debug_cambodiapost.png")
DEBUG_API = Path("debug_cambodiapost_api.json")

WEIGHT = "0.02"

PAGE_TIMEOUT = 60_000
API_TIMEOUT = 60
SELECTION_TIMEOUT = 10_000
RESULT_TIMEOUT = 10_000

KHMER_LOCALE = Locale("km")
ENGLISH_LOCALE = Locale("en")


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Country:
    country_id: str
    raw_text: str
    code: str
    english_name: str
    khmer_name: str

    @property
    def display_name(self) -> str:
        return f"{self.khmer_name} — {self.english_name}"


# ============================================================
# GENERAL HELPERS
# ============================================================

def log(message: str = "") -> None:
    print(message, flush=True)


def fetch_json(url: str, timeout: int = API_TIMEOUT) -> Any:
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
        method="GET",
    )

    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")

    return json.loads(raw)


def extract_country_code(text: str) -> str:
    """
    Cambodia Post returns country labels such as:

        AE (UNITED ARAB EMIRATES)

    Extract the two-letter code.
    """
    match = re.match(r"^\s*([A-Z]{2})\s*\(", text or "")

    if match:
        return match.group(1)

    return ""


def get_english_country_name(code: str, fallback: str) -> str:
    if not code:
        return fallback

    try:
        name = ENGLISH_LOCALE.territories.get(code)

        if name:
            return name

    except Exception:
        pass

    return fallback


def get_khmer_country_name(code: str, fallback: str) -> str:
    if not code:
        return fallback

    try:
        name = KHMER_LOCALE.territories.get(code)

        if name:
            return name

    except Exception:
        pass

    return fallback


def convert_api_record(record: dict[str, Any]) -> Country | None:
    country_id = str(
        record.get("id", "")
    ).strip()

    raw_text = str(
        record.get("text", "")
    ).strip()

    if not country_id or not raw_text:
        return None

    code = extract_country_code(raw_text)

    if not code:
        return None

    match = re.search(
        r"^\s*[A-Z]{2}\s*\((.*?)\)\s*$",
        raw_text,
    )

    if match:
        fallback_english = match.group(1).strip()
    else:
        fallback_english = raw_text

    english_name = get_english_country_name(
        code,
        fallback_english,
    )

    khmer_name = get_khmer_country_name(
        code,
        english_name,
    )

    return Country(
        country_id=country_id,
        raw_text=raw_text,
        code=code,
        english_name=english_name,
        khmer_name=khmer_name,
    )


# ============================================================
# COUNTRY API
# ============================================================

def fetch_all_countries() -> list[Country]:
    log("")
    log("=" * 60)
    log("COUNTRY DISCOVERY")
    log("=" * 60)

    countries: list[Country] = []

    page_number = 1
    last_page = None

    while True:
        api_url = (
            f"{COUNTRY_API}?page={page_number}"
        )

        log(
            f"Fetching country API page {page_number}..."
        )

        data = fetch_json(api_url)

        if not isinstance(data, dict):
            raise RuntimeError(
                "Cambodia Post country API returned "
                "an unexpected response."
            )

        records = data.get("data", [])

        if not isinstance(records, list):
            records = []

        log(
            f"  Received {len(records)} country records."
        )

        for record in records:
            if not isinstance(record, dict):
                continue

            country = convert_api_record(record)

            if country is not None:
                countries.append(country)

        meta = data.get("meta", {})

        if isinstance(meta, dict):
            if last_page is None:
                raw_last_page = meta.get("last_page")

                if raw_last_page is not None:
                    try:
                        last_page = int(raw_last_page)
                    except Exception:
                        last_page = None

        if last_page is not None:
            if page_number >= last_page:
                break
        else:
            if not records:
                break

        page_number += 1

    # Remove duplicates while preserving order.
    unique: list[Country] = []
    seen_ids: set[str] = set()

    for country in countries:
        if country.country_id in seen_ids:
            continue

        seen_ids.add(country.country_id)
        unique.append(country)

    countries = unique

    DEBUG_API.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "country_count": len(countries),
                "countries": [
                    {
                        "id": c.country_id,
                        "raw_text": c.raw_text,
                        "code": c.code,
                        "english_name": c.english_name,
                        "khmer_name": c.khmer_name,
                    }
                    for c in countries
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log("")
    log(
        f"TOTAL COUNTRIES FOUND: {len(countries)}"
    )

    if not countries:
        raise RuntimeError(
            "No countries were returned by Cambodia Post's "
            "country API."
        )

    return countries


# ============================================================
# PAGE LOCATORS
# ============================================================

def find_country_select(page: Page):
    selectors = [
        "#country_id",
        "select[name='country_id']",
        "select[id='country_id']",
    ]

    for selector in selectors:
        locator = page.locator(selector)

        if locator.count() > 0:
            return locator.first

    return None


def find_weight_input(page: Page):
    selectors = [
        "input[name='weight']",
        "input[id='weight']",
        "input[placeholder*='ទម្ងន់']",
        "input[type='number']",
        "input[type='text']",
    ]

    for selector in selectors:
        locator = page.locator(selector)

        count = locator.count()

        for index in range(count):
            candidate = locator.nth(index)

            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue

    return None


def find_calculate_button(page: Page):
    selectors = [
        "button",
        "input[type='submit']",
        "input[type='button']",
        "a",
    ]

    for selector in selectors:
        locator = page.locator(selector)

        count = locator.count()

        for index in range(count):
            candidate = locator.nth(index)

            try:
                if not candidate.is_visible():
                    continue

                text = (
                    candidate.inner_text(
                        timeout=2_000
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
                continue

    return None


# ============================================================
# DEBUGGING
# ============================================================

def save_debug(page: Page) -> None:
    try:
        page.screenshot(
            path=str(DEBUG_PNG),
            full_page=True,
        )
        log(
            f"Saved debug screenshot: {DEBUG_PNG}"
        )
    except Exception as exc:
        log(
            f"Could not save screenshot: {exc}"
        )

    try:
        html = page.content()

        DEBUG_HTML.write_text(
            html,
            encoding="utf-8",
        )

        log(
            f"Saved debug HTML: {DEBUG_HTML}"
        )

    except Exception as exc:
        log(
            f"Could not save debug HTML: {exc}"
        )


# ============================================================
# SELECT2 COUNTRY HANDLING
# ============================================================

def ensure_country_option(
    page: Page,
    country: Country,
) -> bool:
    """
    Ensure the hidden native select contains the
    requested country option.

    Cambodia Post uses Select2, so the native select
    normally contains only the placeholder.
    """

    result = page.evaluate(
        """
        ({ countryId, countryText }) => {
            const select = document.querySelector(
                '#country_id'
            );

            if (!select) {
                return {
                    ok: false,
                    reason: 'country select not found'
                };
            }

            let option = Array.from(
                select.options
            ).find(
                opt => String(opt.value) === String(countryId)
            );

            if (!option) {
                option = document.createElement('option');

                option.value = String(countryId);
                option.textContent = countryText;

                select.appendChild(option);
            }

            option.textContent = countryText;

            return {
                ok: true,
                value: option.value,
                text: option.textContent
            };
        }
        """,
        {
            "countryId": country.country_id,
            "countryText": country.raw_text,
        },
    )

    return bool(
        isinstance(result, dict)
        and result.get("ok")
    )


def select_country(
    page: Page,
    country: Country,
) -> None:
    log(
        f"  Selecting: {country.display_name}"
    )

    if not ensure_country_option(
        page,
        country,
    ):
        raise RuntimeError(
            "Could not create country option."
        )

    result = page.evaluate(
        """
        ({ countryId }) => {
            const select = document.querySelector(
                '#country_id'
            );

            if (!select) {
                return {
                    ok: false,
                    reason: 'country select not found'
                };
            }

            const value = String(countryId);

            const option = Array.from(
                select.options
            ).find(
                opt => String(opt.value) === value
            );

            if (!option) {
                return {
                    ok: false,
                    reason: 'country option not found'
                };
            }

            option.selected = true;
            select.value = value;

            if (window.jQuery) {
                window.jQuery(select)
                    .val(value)
                    .trigger('change');
            } else {
                select.dispatchEvent(
                    new Event(
                        'change',
                        {
                            bubbles: true
                        }
                    )
                );
            }

            return {
                ok: true,
                value: select.value
            };
        }
        """,
        {
            "countryId": country.country_id,
        },
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            "Country selection returned an invalid result."
        )

    if not result.get("ok"):
        raise RuntimeError(
            "Country selection failed: "
            + str(result.get("reason"))
        )

    selected_value = str(
        result.get("value", "")
    )

    if selected_value != country.country_id:
        raise RuntimeError(
            "Country selection verification failed. "
            f"Expected {country.country_id}, "
            f"got {selected_value}"
        )

    # Give Select2 a moment to update its visible UI.
    try:
        page.wait_for_timeout(250)
    except Exception:
        pass


# ============================================================
# WEIGHT
# ============================================================

def set_weight(
    page: Page,
    weight: str,
) -> None:
    weight_input = find_weight_input(page)

    if weight_input is None:
        raise RuntimeError(
            "Weight input could not be found."
        )

    weight_input.fill(weight)

    actual = weight_input.input_value()

    if actual.strip() != weight:
        raise RuntimeError(
            "Weight input verification failed. "
            f"Expected {weight}, got {actual}"
        )


# ============================================================
# RESULT ANALYSIS
# ============================================================

def body_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(
            timeout=5_000
        )
    except Exception:
        return ""


def has_error_message(text: str) -> bool:
    lowered = text.lower()

    error_patterns = [
        "error",
        "failed",
        "invalid",
        "not available",
        "unavailable",
        "suspended",
        "មិនអាច",
        "បរាជ័យ",
        "កំហុស",
    ]

    return any(
        pattern in lowered
        for pattern in error_patterns
    )


def extract_letter_section(text: str) -> str:
    """
    Extract the section of page text beginning around
    the Letter service.

    This intentionally remains tolerant because the
    page layout can change.
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for index, line in enumerate(lines):
        if line.lower() == "letter":
            start = max(0, index - 2)
            end = min(
                len(lines),
                index + 12,
            )

            return "\n".join(
                lines[start:end]
            )

    # Also allow Letter to occur inside a larger line.
    for index, line in enumerate(lines):
        if "letter" in line.lower():
            start = max(0, index - 2)
            end = min(
                len(lines),
                index + 12,
            )

            return "\n".join(
                lines[start:end]
            )

    return ""


def letter_has_price(
    letter_section: str,
) -> bool:
    if not letter_section:
        return False

    lowered = letter_section.lower()

    if "price" not in lowered:
        return False

    # Cambodia Post displays the price in KHR.
    if "khr" not in lowered:
        return False

    # Require at least one number near the price.
    price_patterns = [
        r"price\s*\(khr\).*?\d",
        r"price.*?khr.*?\d",
        r"khr.*?\d",
    ]

    return any(
        re.search(
            pattern,
            lowered,
            flags=re.DOTALL,
        )
        for pattern in price_patterns
    )


def analyze_result(
    page: Page,
) -> tuple[bool, str]:
    text = body_text(page)

    if has_error_message(text):
        return (
            True,
            "Error message detected",
        )

    letter_section = extract_letter_section(text)

    if not letter_section:
        return (
            True,
            "Letter service is missing",
        )

    if not letter_has_price(letter_section):
        return (
            True,
            "Letter service has no Price (KHR)",
        )

    return (
        False,
        "Letter service has Price (KHR)",
    )


# ============================================================
# CALCULATION
# ============================================================

def click_calculate(
    page: Page,
) -> None:
    button = find_calculate_button(page)

    if button is None:
        raise RuntimeError(
            "Calculate button could not be found."
        )

    log("  Clicking Calculate...")

    try:
        button.click(
            timeout=SELECTION_TIMEOUT
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not click Calculate: {exc}"
        ) from exc


def wait_for_result(
    page: Page,
) -> None:
    """
    Wait for the calculation result to appear.

    We do not require the network response because
    Cambodia Post may change its AJAX implementation.
    """

    deadline = time.monotonic() + (
        RESULT_TIMEOUT / 1000
    )

    last_text = ""

    while time.monotonic() < deadline:
        text = body_text(page)

        if text != last_text:
            last_text = text

        lowered = text.lower()

        if (
            "letter" in lowered
            or "error" in lowered
            or "price (khr)" in lowered
            or "price" in lowered
        ):
            return

        page.wait_for_timeout(250)


def calculate_country(
    page: Page,
    country: Country,
) -> tuple[bool, str]:
    select_country(
        page,
        country,
    )

    set_weight(
        page,
        WEIGHT,
    )

    click_calculate(
        page,
    )

    wait_for_result(
        page,
    )

    return analyze_result(page)


# ============================================================
# PAGE PREPARATION
# ============================================================

def prepare_page(page: Page) -> None:
    log("")
    log("=" * 60)
    log("OPENING CAMBODIA POST")
    log("=" * 60)

    log(
        f"Opening {URL} ..."
    )

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    log(
        f"Page loaded: {page.url}"
    )

    page.wait_for_timeout(2_000)

    country_select = find_country_select(page)

    if country_select is None:
        raise RuntimeError(
            "Country select #country_id was not found."
        )

    log(
        "Country select found: #country_id"
    )

    weight_input = find_weight_input(page)

    if weight_input is None:
        raise RuntimeError(
            "Weight input could not be found."
        )

    log(
        "Weight input found."
    )

    calculate_button = find_calculate_button(page)

    if calculate_button is None:
        raise RuntimeError(
            "Calculate button could not be found."
        )

    log(
        "Calculate button found."
    )


# ============================================================
# MONITOR
# ============================================================

def test_all_countries(
    page: Page,
    countries: list[Country],
) -> list[Country]:
    suspended: list[Country] = []

    log("")
    log("=" * 60)
    log("TESTING COUNTRIES")
    log("=" * 60)

    log(
        f"Countries to test: {len(countries)}"
    )

    log(
        f"Weight for every test: {WEIGHT} kg"
    )

    for index, country in enumerate(
        countries,
        start=1,
    ):
        log("")
        log(
            f"[{index}/{len(countries)}] "
            f"Testing: {country.display_name}"
        )

        try:
            is_suspended, reason = calculate_country(
                page,
                country,
            )

            if is_suspended:
                suspended.append(country)

                log(
                    f"  -> SUSPENDED: {reason}"
                )
            else:
                log(
                    f"  -> AVAILABLE: {reason}"
                )

        except PlaywrightTimeoutError as exc:
            suspended.append(country)

            log(
                "  -> TECHNICAL ERROR / SUSPENDED: "
                f"{exc}"
            )

        except Exception as exc:
            suspended.append(country)

            log(
                "  -> TECHNICAL ERROR / SUSPENDED: "
                f"{exc}"
            )

        # Small pause between countries.
        page.wait_for_timeout(150)


    return suspended


# ============================================================
# OUTPUT
# ============================================================

def write_output(
    countries: list[Country],
    suspended: list[Country],
) -> None:
    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    suspended_ids = {
        country.country_id
        for country in suspended
    }

    lines: list[str] = []

    lines.append(
        "CAMBODIA POST INTERNATIONAL SHIPPING MONITOR"
    )

    lines.append(
        f"Last checked: {timestamp}"
    )

    lines.append(
        f"Weight tested: {WEIGHT} kg"
    )

    lines.append("")

    lines.append(
        "============================================================"
    )

    lines.append(
        f"COUNTRY LIST ({len(countries)} countries)"
    )

    lines.append(
        "============================================================"
    )

    for index, country in enumerate(
        countries,
        start=1,
    ):
        status = (
            " — SUSPENDED"
            if country.country_id in suspended_ids
            else ""
        )

        lines.append(
            f"{index}. "
            f"{country.khmer_name} — "
            f"{country.english_name}"
            f"{status}"
        )

    lines.append("")

    lines.append(
        "============================================================"
    )

    lines.append(
        f"SUSPENDED DESTINATIONS ({len(suspended)})"
    )

    lines.append(
        "============================================================"
    )

    if suspended:
        for index, country in enumerate(
            suspended,
            start=1,
        ):
            lines.append(
                f"{index}. "
                f"{country.khmer_name} — "
                f"{country.english_name}"
            )
    else:
        lines.append(
            "None"
        )

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    log("")
    log("=" * 60)
    log("OUTPUT CREATED")
    log("=" * 60)

    log(
        f"File: {OUTPUT_FILE}"
    )

    log(
        f"Country count: {len(countries)}"
    )

    log(
        f"Suspended count: {len(suspended)}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    log("")
    log("=" * 60)
    log("CAMBODIA POST INTERNATIONAL SHIPPING MONITOR")
    log("=" * 60)

    log(
        f"Started: "
        f"{datetime.now(timezone.utc).isoformat()}"
    )

    try:
        log("")
        log("Step 1: Fetching country list from API...")

        countries = fetch_all_countries()

        if not countries:
            raise RuntimeError(
                "Country list is empty."
            )

        log("")
        log(
            "Step 2: Starting Chromium..."
        )

        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            context: BrowserContext = browser.new_context(
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
                locale="en-US",
            )

            page = context.new_page()

            page.set_default_timeout(
                SELECTION_TIMEOUT
            )

            try:
                prepare_page(page)

                log("")
                log(
                    "Step 3: Testing all countries..."
                )

                suspended = test_all_countries(
                    page,
                    countries,
                )

                log("")
                log(
                    "Step 4: Writing output..."
                )

                write_output(
                    countries,
                    suspended,
                )

            except Exception as exc:
                log("")
                log("=" * 60)
                log("MONITOR FAILED")
                log("=" * 60)

                log(
                    f"{type(exc).__name__}: {exc}"
                )

                save_debug(page)

                raise

            finally:
                context.close()
                browser.close()

        log("")
        log("=" * 60)
        log("MONITOR FINISHED SUCCESSFULLY")
        log("=" * 60)

        return 0

    except Exception as exc:
        log("")
        log("=" * 60)
        log("FATAL ERROR")
        log("=" * 60)

        log(
            f"{type(exc).__name__}: {exc}"
        )

        log("")
        log(
            "output_cambodia.txt was not created "
            "because the monitor did not complete."
        )

        return 1


# ============================================================
# REQUIRED ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
