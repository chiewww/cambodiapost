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

OUTPUT_FILE = Path("output_cambodia.txt")

DEBUG_HTML = Path("debug_cambodiapost.html")
DEBUG_PNG = Path("debug_cambodiapost.png")
DEBUG_API = Path("debug_cambodiapost_api.json")

WEIGHT = "0.02"

PAGE_TIMEOUT = 60_000
API_TIMEOUT = 60
ACTION_TIMEOUT = 15_000
RESULT_TIMEOUT = 15_000

KHMER_LOCALE = Locale("km")
ENGLISH_LOCALE = Locale("en")


# ============================================================
# DATA STRUCTURE
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
        return (
            f"{self.khmer_name} — "
            f"{self.english_name}"
        )


# ============================================================
# LOGGING
# ============================================================

def log(message: str = "") -> None:
    print(message, flush=True)


# ============================================================
# COUNTRY API
# ============================================================

def fetch_json(
    url: str,
    timeout: int = API_TIMEOUT,
) -> Any:

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
            "Accept": (
                "application/json,"
                "text/plain,*/*"
            ),
        },
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def extract_country_code(
    text: str,
) -> str:

    match = re.match(
        r"^\s*([A-Z]{2})\s*\(",
        text or "",
    )

    if match:
        return match.group(1)

    return ""


def get_country_name(
    locale: Locale,
    code: str,
    fallback: str,
) -> str:

    if not code:
        return fallback

    try:
        name = locale.territories.get(code)

        if name:
            return name

    except Exception:
        pass

    return fallback


def convert_country(
    record: dict[str, Any],
) -> Country | None:

    country_id = str(
        record.get("id", "")
    ).strip()

    raw_text = str(
        record.get("text", "")
    ).strip()

    if not country_id or not raw_text:
        return None

    code = extract_country_code(
        raw_text
    )

    if not code:
        return None

    match = re.search(
        r"^\s*[A-Z]{2}\s*\((.*?)\)\s*$",
        raw_text,
    )

    if match:
        fallback_english = (
            match.group(1).strip()
        )
    else:
        fallback_english = raw_text

    english_name = get_country_name(
        ENGLISH_LOCALE,
        code,
        fallback_english,
    )

    khmer_name = get_country_name(
        KHMER_LOCALE,
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


def fetch_all_countries() -> list[Country]:

    log("")
    log("=" * 60)
    log("COUNTRY DISCOVERY")
    log("=" * 60)

    countries: list[Country] = []

    page_number = 1

    while True:

        api_url = (
            f"{COUNTRY_API}"
            f"?page={page_number}"
        )

        log(
            f"Fetching country API page "
            f"{page_number}..."
        )

        data = fetch_json(
            api_url
        )

        records = data.get(
            "data",
            [],
        )

        if not isinstance(
            records,
            list,
        ):
            records = []

        log(
            f"  Received "
            f"{len(records)} country records."
        )

        if not records:
            break

        for record in records:

            if not isinstance(
                record,
                dict,
            ):
                continue

            country = convert_country(
                record
            )

            if country:
                countries.append(
                    country
                )

        page_number += 1

    # Remove duplicate IDs while preserving order.
    unique_countries = []
    seen_ids = set()

    for country in countries:

        if country.country_id in seen_ids:
            continue

        seen_ids.add(
            country.country_id
        )

        unique_countries.append(
            country
        )

    countries = unique_countries

    DEBUG_API.write_text(
        json.dumps(
            [
                {
                    "id": c.country_id,
                    "raw_text": c.raw_text,
                    "code": c.code,
                    "english_name": c.english_name,
                    "khmer_name": c.khmer_name,
                }
                for c in countries
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log("")
    log(
        f"TOTAL COUNTRIES FOUND: "
        f"{len(countries)}"
    )

    if not countries:
        raise RuntimeError(
            "No countries were found."
        )

    return countries


# ============================================================
# PAGE ELEMENTS
# ============================================================

def find_country_select(
    page: Page,
):

    locator = page.locator(
        "#country_id"
    )

    if locator.count() == 0:
        raise RuntimeError(
            "Country select #country_id "
            "was not found."
        )

    return locator.first


def find_weight_input(
    page: Page,
):

    selectors = [
        "input[name='weight']",
        "input[id='weight']",
        "input[type='number']",
        "input[placeholder*='ទម្ងន់']",
    ]

    for selector in selectors:

        locator = page.locator(
            selector
        )

        for index in range(
            locator.count()
        ):

            candidate = locator.nth(
                index
            )

            try:

                if candidate.is_visible():
                    return candidate

            except Exception:
                pass

    raise RuntimeError(
        "Weight input was not found."
    )


def find_calculate_button(
    page: Page,
):

    candidates = page.locator(
        "button, "
        "input[type='submit'], "
        "input[type='button'], "
        "a"
    )

    for index in range(
        candidates.count()
    ):

        candidate = candidates.nth(
            index
        )

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
                candidate.get_attribute(
                    "value"
                )
                or ""
            ).strip().lower()

            combined = (
                f"{text} {value}"
            )

            if (
                "calculate" in combined
                or "គណនា" in combined
            ):
                return candidate

        except Exception:
            pass

    raise RuntimeError(
        "Calculate button was not found."
    )


# ============================================================
# SELECT2 COUNTRY SELECTION
# ============================================================

def select_country(
    page: Page,
    country: Country,
) -> None:

    log(
        f"  Selecting: "
        f"{country.display_name}"
    )

    result = page.evaluate(
        """
        ({ countryId, countryText }) => {

            const select =
                document.querySelector(
                    '#country_id'
                );

            if (!select) {
                return {
                    ok: false,
                    reason: 'country select not found'
                };
            }

            const value =
                String(countryId);

            let option =
                Array.from(
                    select.options
                ).find(
                    opt =>
                        String(opt.value)
                        === value
                );

            if (!option) {

                option =
                    document.createElement(
                        'option'
                    );

                option.value = value;
                option.textContent =
                    countryText;

                select.appendChild(
                    option
                );
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
                value: select.value,
                text: option.textContent
            };
        }
        """,
        {
            "countryId": country.country_id,
            "countryText": country.raw_text,
        },
    )

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "Invalid country selection result."
        )

    if not result.get("ok"):
        raise RuntimeError(
            "Could not select country: "
            f"{result.get('reason')}"
        )

    selected_value = str(
        result.get(
            "value",
            "",
        )
    )

    if selected_value != (
        country.country_id
    ):
        raise RuntimeError(
            "Country selection verification "
            "failed. "
            f"Expected {country.country_id}, "
            f"got {selected_value}"
        )

    page.wait_for_timeout(
        300
    )


# ============================================================
# WEIGHT
# ============================================================

def set_weight(
    page: Page,
) -> None:

    weight = find_weight_input(
        page
    )

    weight.fill(
        WEIGHT
    )

    actual = (
        weight.input_value()
        .strip()
    )

    if actual != WEIGHT:
        raise RuntimeError(
            "Weight verification failed. "
            f"Expected {WEIGHT}, "
            f"got {actual}"
        )


# ============================================================
# RESULT TABLE DETECTION
# ============================================================

def get_letter_row_text(
    page: Page,
) -> str:

    """
    Look for the actual Letter service row
    in the rendered result table.

    We intentionally inspect table rows rather
    than searching the entire page for the words
    'Letter' and 'Price (KHR)'.
    """

    rows = page.locator(
        "tr"
    )

    for index in range(
        rows.count()
    ):

        row = rows.nth(
            index
        )

        try:

            if not row.is_visible():
                continue

            text = (
                row.inner_text(
                    timeout=2_000
                )
                .strip()
            )

            if not text:
                continue

            normalized = re.sub(
                r"\s+",
                " ",
                text,
            ).strip()

            # Match a row whose first service
            # name is Letter.
            #
            # Avoid matching:
            # Letter Register
            # Letter Register + AR
            if re.match(
                r"^Letter\s+",
                normalized,
                flags=re.IGNORECASE,
            ):

                return normalized

            if normalized.lower() == "letter":
                return normalized

        except Exception:
            continue

    return ""


def letter_row_has_price(
    row_text: str,
) -> bool:

    if not row_text:
        return False

    # A normal result looks approximately like:
    #
    # Letter    3,300 ៛    19 to 26 days
    #
    # We therefore look for a numeric price.
    #
    # Accept:
    # 3300
    # 3,300
    # 3 300
    # 3300 ៛
    # 3,300 ៛

    price_pattern = re.compile(
        r"\b\d{1,3}"
        r"(?:[,\s]\d{3})*"
        r"\b"
    )

    matches = price_pattern.findall(
        row_text
    )

    if not matches:
        return False

    # Exclude the service name itself and
    # require a plausible KHR amount.
    for match in matches:

        digits = re.sub(
            r"\D",
            "",
            match,
        )

        if not digits:
            continue

        try:
            amount = int(
                digits
            )
        except ValueError:
            continue

        if amount > 0:
            return True

    return False


def page_has_calculation_table(
    page: Page,
) -> bool:

    row = get_letter_row_text(
        page
    )

    return bool(row)


# ============================================================
# CALCULATION
# ============================================================

def click_calculate(
    page: Page,
) -> None:

    button = find_calculate_button(
        page
    )

    log(
        "  Clicking Calculate..."
    )

    button.click(
        timeout=ACTION_TIMEOUT
    )


def wait_for_calculation(
    page: Page,
) -> None:

    """
    Wait until the Letter row appears.

    We don't depend on a particular AJAX response
    URL because the website's JavaScript implementation
    may change.
    """

    deadline = (
        time.monotonic()
        + RESULT_TIMEOUT / 1000
    )

    while (
        time.monotonic()
        < deadline
    ):

        row = get_letter_row_text(
            page
        )

        if row:
            return

        page.wait_for_timeout(
            250
        )

    # If the result didn't appear, leave the
    # final decision to the caller.
    return


# ============================================================
# TEST ONE COUNTRY
# ============================================================

def test_country(
    page: Page,
    country: Country,
) -> tuple[bool, str]:

    # --------------------------------------------------------
    # 1. Select country
    # --------------------------------------------------------

    select_country(
        page,
        country,
    )

    # --------------------------------------------------------
    # 2. Enter 0.02 kg
    # --------------------------------------------------------

    log(
        "  Entering weight: 0.02 kg"
    )

    set_weight(
        page
    )

    # --------------------------------------------------------
    # 3. Click Calculate
    # --------------------------------------------------------

    click_calculate(
        page
    )

    # --------------------------------------------------------
    # 4. Wait for result
    # --------------------------------------------------------

    wait_for_calculation(
        page
    )

    # --------------------------------------------------------
    # 5. Determine Letter availability
    # --------------------------------------------------------

    letter_row = get_letter_row_text(
        page
    )

    if not letter_row:

        return (
            True,
            "Letter service is missing",
        )

    if not letter_row_has_price(
        letter_row
    ):

        return (
            True,
            "Letter service has no KHR price",
        )

    return (
        False,
        f"Letter available: {letter_row}",
    )


# ============================================================
# PAGE PREPARATION
# ============================================================

def prepare_page(
    page: Page,
) -> None:

    log("")
    log("=" * 60)
    log("OPENING CAMBODIA POST")
    log("=" * 60)

    log(
        f"Opening {URL}..."
    )

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    log(
        f"Page loaded: {page.url}"
    )

    page.wait_for_timeout(
        3_000
    )

    find_country_select(
        page
    )

    log(
        "Country select found."
    )

    find_weight_input(
        page
    )

    log(
        "Weight input found."
    )

    find_calculate_button(
        page
    )

    log(
        "Calculate button found."
    )


# ============================================================
# TEST ALL COUNTRIES
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
        f"Total countries: "
        f"{len(countries)}"
    )

    log(
        f"Weight: {WEIGHT} kg"
    )

    for index, country in enumerate(
        countries,
        start=1,
    ):

        log("")
        log(
            f"[{index}/{len(countries)}] "
            f"Testing: "
            f"{country.display_name}"
        )

        try:

            is_suspended, reason = (
                test_country(
                    page,
                    country,
                )
            )

            if is_suspended:

                suspended.append(
                    country
                )

                log(
                    f"  -> SUSPENDED: "
                    f"{reason}"
                )

            else:

                log(
                    f"  -> AVAILABLE: "
                    f"{reason}"
                )

        except PlaywrightTimeoutError as exc:

            suspended.append(
                country
            )

            log(
                "  -> TECHNICAL ERROR: "
                f"{exc}"
            )

        except Exception as exc:

            suspended.append(
                country
            )

            log(
                "  -> TECHNICAL ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        page.wait_for_timeout(
            200
        )

    return suspended


# ============================================================
# OUTPUT FILE
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

    # --------------------------------------------------------
    # COUNTRY LIST
    # --------------------------------------------------------

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

        status = ""

        if country.country_id in suspended_ids:
            status = " — SUSPENDED"

        lines.append(
            f"{index}. "
            f"{country.khmer_name} — "
            f"{country.english_name}"
            f"{status}"
        )

    lines.append("")

    # --------------------------------------------------------
    # SUSPENDED LIST
    # --------------------------------------------------------

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
        f"Countries: {len(countries)}"
    )

    log(
        f"Suspended: {len(suspended)}"
    )


# ============================================================
# DEBUG
# ============================================================

def save_debug(
    page: Page,
) -> None:

    try:

        DEBUG_HTML.write_text(
            page.content(),
            encoding="utf-8",
        )

        log(
            f"Saved debug HTML: "
            f"{DEBUG_HTML}"
        )

    except Exception as exc:

        log(
            f"Could not save debug HTML: "
            f"{exc}"
        )

    try:

        page.screenshot(
            path=str(DEBUG_PNG),
            full_page=True,
        )

        log(
            f"Saved debug screenshot: "
            f"{DEBUG_PNG}"
        )

    except Exception as exc:

        log(
            f"Could not save screenshot: "
            f"{exc}"
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

        # ----------------------------------------------------
        # STEP 1
        # ----------------------------------------------------

        log("")
        log(
            "Step 1: Discovering all countries..."
        )

        countries = fetch_all_countries()

        # ----------------------------------------------------
        # STEP 2
        # ----------------------------------------------------

        log("")
        log(
            "Step 2: Starting Chromium..."
        )

        with sync_playwright() as playwright:

            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            context = browser.new_context(
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
                locale="en-US",
            )

            page = context.new_page()

            page.set_default_timeout(
                ACTION_TIMEOUT
            )

            try:

                # ------------------------------------------------
                # STEP 3
                # ------------------------------------------------

                prepare_page(
                    page
                )

                # ------------------------------------------------
                # STEP 4
                # ------------------------------------------------

                log("")
                log(
                    "Step 3: Testing every country..."
                )

                suspended = (
                    test_all_countries(
                        page,
                        countries,
                    )
                )

                # ------------------------------------------------
                # STEP 5
                # ------------------------------------------------

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
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                save_debug(
                    page
                )

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
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        return 1


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
