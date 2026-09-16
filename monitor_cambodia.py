import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from babel import Locale
from playwright.sync_api import (
    sync_playwright,
    Page,
    Browser,
    BrowserContext,
)


# ============================================================
# CONFIGURATION
# ============================================================

URL = "https://www.cambodiapost.com.kh/calculate/international"

COUNTRY_API = (
    "https://www.cambodiapost.com.kh/"
    "select2/getAllCountries"
)

OUTPUT_FILE = Path("output_cambodia.txt")

DEBUG_HTML = Path("debug_cambodiapost.html")
DEBUG_PNG = Path("debug_cambodiapost.png")
DEBUG_API = Path("debug_cambodiapost_api.json")

WEIGHT = "0.02"

PAGE_TIMEOUT = 60_000
RESULT_TIMEOUT = 30_000

API_TIMEOUT = 60


# ============================================================
# BABEL LOCALES
# ============================================================

KHMER_LOCALE = Locale("km")
ENGLISH_LOCALE = Locale("en")


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class Country:
    country_id: str
    code: str
    english_name: str
    khmer_name: str

    @property
    def display_name(self) -> str:
        if self.khmer_name:
            return (
                f"{self.khmer_name} — "
                f"{self.english_name}"
            )

        return self.english_name


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_name(value: str) -> str:
    return clean_text(value).casefold()


def save_debug(
    page: Page,
) -> None:

    try:
        DEBUG_HTML.write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        page.screenshot(
            path=str(DEBUG_PNG),
            full_page=True,
        )
    except Exception:
        pass


# ============================================================
# COUNTRY NAME HANDLING
# ============================================================

def english_country_name(
    code: str,
    api_name: str,
) -> str:

    code = clean_text(code).upper()

    # Babel provides standardized English territory names.
    if code:
        try:
            name = ENGLISH_LOCALE.territories.get(
                code,
                "",
            )

            if name:
                return clean_text(name)
        except Exception:
            pass

    # Fall back to API text.
    api_name = clean_text(api_name)

    # Remove "XX (" and ")" if present.
    match = re.match(
        r"^[A-Z]{2}\s*\((.*?)\)$",
        api_name,
        flags=re.IGNORECASE,
    )

    if match:
        return clean_text(
            match.group(1)
        )

    return api_name


def khmer_country_name(
    code: str,
) -> str:

    code = clean_text(code).upper()

    if not code:
        return ""

    try:
        name = KHMER_LOCALE.territories.get(
            code,
            "",
        )

        if name:
            return clean_text(name)
    except Exception:
        pass

    return ""


# ============================================================
# FETCH CAMBODIA POST COUNTRY API
# ============================================================

def fetch_json(
    url: str,
) -> dict[str, Any]:

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
            "Accept": (
                "application/json,text/plain,*/*"
            ),
            "Referer": URL,
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=API_TIMEOUT,
        ) as response:

            raw = response.read()

            text = raw.decode(
                "utf-8",
                errors="replace",
            )

            return json.loads(text)

    except HTTPError as exc:
        raise RuntimeError(
            f"Country API returned HTTP "
            f"{exc.code}: {url}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            f"Could not connect to country API: "
            f"{exc}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Country API did not return valid JSON: "
            f"{url}"
        ) from exc


def parse_country_record(
    record: dict[str, Any],
) -> Country | None:

    country_id = clean_text(
        record.get("id")
    )

    text = clean_text(
        record.get("text")
    )

    if not country_id or not text:
        return None

    # Expected API format:
    #
    # "AE (UNITED ARAB EMIRATES)"
    #
    match = re.match(
        r"^([A-Z]{2})\s*\((.*?)\)$",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        code = clean_text(
            match.group(1)
        ).upper()

        api_name = clean_text(
            match.group(2)
        )
    else:
        code = ""

        api_name = text

    english_name = english_country_name(
        code,
        api_name,
    )

    khmer_name = khmer_country_name(
        code,
    )

    return Country(
        country_id=country_id,
        code=code,
        english_name=english_name,
        khmer_name=khmer_name,
    )


def fetch_all_countries() -> list[Country]:

    print()
    print(
        "============================================================"
    )
    print(
        "FETCHING COUNTRIES FROM CAMBODIA POST API"
    )
    print(
        "============================================================"
    )

    countries: list[Country] = []

    page_number = 1

    # Safety limit.
    max_pages = 100

    while page_number <= max_pages:

        api_url = (
            f"{COUNTRY_API}"
            f"?page={page_number}"
        )

        print(
            f"Fetching country API page "
            f"{page_number}..."
        )

        data = fetch_json(
            api_url
        )

        rows = data.get(
            "data",
            [],
        )

        if not isinstance(
            rows,
            list,
        ):
            raise RuntimeError(
                "Unexpected country API response: "
                "'data' is not a list."
            )

        if not rows:
            break

        for record in rows:

            if not isinstance(
                record,
                dict,
            ):
                continue

            country = parse_country_record(
                record
            )

            if country is not None:
                countries.append(
                    country
                )

        last_page = data.get(
            "last_page"
        )

        if last_page is not None:
            try:
                last_page_int = int(
                    last_page
                )
            except Exception:
                last_page_int = page_number
        else:
            last_page_int = page_number

        print(
            f"  Received {len(rows)} "
            f"country records."
        )

        if page_number >= last_page_int:
            break

        next_page = data.get(
            "next_page_url"
        )

        if not next_page:
            break

        page_number += 1

    # Remove duplicates.
    unique: list[Country] = []

    seen_ids: set[str] = set()

    for country in countries:

        if country.country_id in seen_ids:
            continue

        seen_ids.add(
            country.country_id
        )

        unique.append(
            country
        )

    countries = unique

    if not countries:
        raise RuntimeError(
            "Cambodia Post country API returned "
            "zero countries."
        )

    # Save raw API data for diagnostics.
    try:
        DEBUG_API.write_text(
            json.dumps(
                [
                    {
                        "id": c.country_id,
                        "code": c.code,
                        "khmer_name": c.khmer_name,
                        "english_name": c.english_name,
                    }
                    for c in countries
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    print()
    print(
        f"TOTAL COUNTRIES FOUND: {len(countries)}"
    )

    return countries


# ============================================================
# FIND COUNTRY SELECT
# ============================================================

def find_country_select(
    page: Page,
):

    selects = page.locator(
        "select"
    )

    count = selects.count()

    if count == 0:
        return None

    # Prefer the select with country_id.
    for index in range(count):

        select = selects.nth(index)

        try:
            name = clean_text(
                select.get_attribute(
                    "name"
                )
                or ""
            )

            element_id = clean_text(
                select.get_attribute(
                    "id"
                )
                or ""
            )

            if (
                name == "country_id"
                or element_id == "country_id"
            ):
                return select

        except Exception:
            continue

    # Fallback: inspect surrounding text.
    for index in range(count):

        select = selects.nth(index)

        try:

            surrounding = page.evaluate(
                """
                (element) => {
                    const parent =
                        element.closest(
                            "div, form, section"
                        );

                    return (
                        parent?.innerText
                        || element.parentElement?.innerText
                        || ""
                    );
                }
                """,
                select.element_handle(),
            )

            text = clean_text(
                surrounding or ""
            ).lower()

            if (
                "country" in text
                or "ប្រទេស" in text
            ):
                return select

        except Exception:
            continue

    return selects.nth(0)


# ============================================================
# INSERT COUNTRY OPTIONS
# ============================================================

def populate_country_select(
    page: Page,
    countries: list[Country],
) -> None:

    select = find_country_select(
        page
    )

    if select is None:
        raise RuntimeError(
            "Country select #country_id "
            "could not be found."
        )

    print()
    print(
        "Populating Cambodia Post Country select..."
    )

    options = [
        {
            "id": country.country_id,
            "text": (
                f"{country.code} "
                f"({country.english_name})"
                if country.code
                else country.english_name
            ),
        }
        for country in countries
    ]

    result = page.evaluate(
        """
        (payload) => {

            const select =
                document.querySelector(
                    "#country_id"
                )
                || document.querySelector(
                    'select[name="country_id"]'
                );

            if (!select) {
                return {
                    ok: false,
                    reason: "country select not found"
                };
            }

            // Keep the original placeholder.
            const placeholder =
                select.querySelector(
                    'option[value=""]'
                )
                || select.querySelector(
                    'option:not([value])'
                );

            select.innerHTML = "";

            if (placeholder) {
                select.appendChild(
                    placeholder.cloneNode(true)
                );
            }

            let added = 0;

            for (const item of payload) {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value = String(
                    item.id
                );

                option.textContent =
                    item.text;

                select.appendChild(
                    option
                );

                added += 1;
            }

            // Trigger native events.
            select.dispatchEvent(
                new Event(
                    "input",
                    {
                        bubbles: true
                    }
                )
            );

            select.dispatchEvent(
                new Event(
                    "change",
                    {
                        bubbles: true
                    }
                )
            );

            // If Select2 is installed, refresh it.
            if (
                window.jQuery
                && window.jQuery.fn
                && window.jQuery.fn.select2
            ) {

                const jq =
                    window.jQuery(select);

                try {
                    jq.trigger("change");
                } catch (e) {}

                try {
                    jq.select2();
                } catch (e) {}
            }

            return {
                ok: true,
                added: added,
                total: select.options.length
            };
        }
        """,
        options,
    )

    print(
        "Country select population result:",
        result,
    )

    if not result.get("ok"):
        raise RuntimeError(
            "Could not populate Country select."
        )

    # Confirm options exist.
    option_count = select.locator(
        "option"
    ).count()

    print(
        f"Country select now contains "
        f"{option_count} option(s)."
    )

    if option_count <= 1:
        raise RuntimeError(
            "Country select still contains only "
            "the placeholder after population."
        )


# ============================================================
# SELECT ONE COUNTRY
# ============================================================

def select_country(
    page: Page,
    country: Country,
) -> None:

    select = find_country_select(
        page
    )

    if select is None:
        raise RuntimeError(
            "Country select could not be found."
        )

    print(
        f"  Selecting: "
        f"{country.display_name}"
    )

    # Use the actual ID supplied by Cambodia Post.
    select.select_option(
        value=country.country_id
    )

    # Trigger Select2/jQuery change explicitly.
    page.evaluate(
        """
        (countryId) => {

            const select =
                document.querySelector(
                    "#country_id"
                )
                || document.querySelector(
                    'select[name="country_id"]'
                );

            if (!select) {
                return false;
            }

            select.value =
                String(countryId);

            select.dispatchEvent(
                new Event(
                    "input",
                    {
                        bubbles: true
                    }
                )
            );

            select.dispatchEvent(
                new Event(
                    "change",
                    {
                        bubbles: true
                    }
                )
            );

            if (
                window.jQuery
                && window.jQuery.fn
                && window.jQuery.fn.select2
            ) {

                try {
                    window.jQuery(select)
                        .val(String(countryId))
                        .trigger("change");
                } catch (e) {}
            }

            return true;
        }
        """,
        country.country_id,
    )

    time.sleep(0.3)


# ============================================================
# WEIGHT INPUT
# ============================================================

def find_weight_input(
    page: Page,
):

    selectors = [
        'input[placeholder*="បញ្ចូលទម្ងន់"]',
        'input[name*="weight" i]',
        'input[id*="weight" i]',
        'input[type="number"]',
        'input[type="text"]',
    ]

    for selector in selectors:

        locator = page.locator(
            selector
        )

        try:

            count = locator.count()

            for index in range(count):

                item = locator.nth(index)

                if item.is_visible():
                    return item

        except Exception:
            continue

    return None


def set_weight(
    page: Page,
) -> None:

    weight_input = find_weight_input(
        page
    )

    if weight_input is None:
        raise RuntimeError(
            "Weight input could not be found."
        )

    weight_input.fill(
        WEIGHT
    )

    # Fire normal browser events.
    try:
        weight_input.press(
            "Tab"
        )
    except Exception:
        pass

    time.sleep(0.2)


# ============================================================
# CALCULATE BUTTON
# ============================================================

def find_calculate_button(
    page: Page,
):

    buttons = page.locator(
        "button, input[type='button'], "
        "input[type='submit']"
    )

    count = buttons.count()

    for index in range(count):

        button = buttons.nth(index)

        try:

            if not button.is_visible():
                continue

            text = clean_text(
                button.inner_text()
            ).lower()

            value = clean_text(
                button.get_attribute(
                    "value"
                )
                or ""
            ).lower()

            if (
                "calculate" in text
                or "គណនា" in text
                or "calculate" in value
                or "គណនា" in value
            ):
                return button

        except Exception:
            continue

    return None


# ============================================================
# RESULT TEXT
# ============================================================

def get_body_text(
    page: Page,
) -> str:

    try:
        return clean_text(
            page.locator(
                "body"
            ).inner_text()
        )
    except Exception:
        return ""


def get_letter_section(
    page: Page,
) -> str:

    text = get_body_text(
        page
    )

    lines = [
        clean_text(line)
        for line in text.splitlines()
        if clean_text(line)
    ]

    relevant: list[str] = []

    for index, line in enumerate(
        lines
    ):

        if re.search(
            r"\bLetter\b",
            line,
            flags=re.IGNORECASE,
        ):

            start = max(
                0,
                index - 3,
            )

            end = min(
                len(lines),
                index + 8,
            )

            relevant.extend(
                lines[start:end]
            )

    # Preserve order but remove duplicates.
    return "\n".join(
        dict.fromkeys(
            relevant
        )
    )


# ============================================================
# ERROR DETECTION
# ============================================================

def has_error_message(
    text: str,
) -> bool:

    lowered = text.lower()

    patterns = [
        "error",
        "failed",
        "failure",
        "invalid",
        "not available",
        "unavailable",
        "suspended",
        "cannot",
        "unable",
        "មិនអាច",
        "បរាជ័យ",
        "មិនមាន",
        "ផ្អាក",
        "មិនទាន់មាន",
    ]

    for pattern in patterns:

        if pattern.lower() in lowered:
            return True

    return False


# ============================================================
# PRICE DETECTION
# ============================================================

def letter_has_price(
    section: str,
) -> bool:

    if not section:
        return False

    lowered = section.lower()

    has_price_label = any(
        word in lowered
        for word in [
            "price",
            "khr",
            "៛",
            "រៀល",
        ]
    )

    if not has_price_label:
        return False

    # Detect amounts such as:
    #
    # 2600
    # 2,600
    # 2 600
    # 12,000
    #
    has_number = bool(
        re.search(
            r"\b\d{3,}\b"
            r"|"
            r"\b\d{1,3}"
            r"(?:[,.\s]\d{3})+\b",
            section,
        )
    )

    return has_number


# ============================================================
# ANALYZE CALCULATION RESULT
# ============================================================

def analyze_result(
    page: Page,
) -> tuple[bool, str]:

    print(
        "  Waiting for calculation result..."
    )

    deadline = (
        time.monotonic()
        + RESULT_TIMEOUT / 1000
    )

    last_text = ""

    while (
        time.monotonic()
        < deadline
    ):

        text = get_body_text(
            page
        )

        if text:
            last_text = text

            if has_error_message(
                text
            ):
                return (
                    True,
                    "Error message detected",
                )

            # Letter service must exist.
            has_letter = bool(
                re.search(
                    r"\bLetter\b",
                    text,
                    flags=re.IGNORECASE,
                )
            )

            if has_letter:

                section = get_letter_section(
                    page
                )

                print(
                    "  Letter section:"
                )

                print(
                    section[:1000]
                )

                if letter_has_price(
                    section
                ):
                    return (
                        False,
                        "Letter service with "
                        "Price (KHR) detected",
                    )

                return (
                    True,
                    "Letter is displayed but "
                    "Price (KHR) is missing",
                )

        time.sleep(
            0.5
        )

    # Final timeout evaluation.
    if not re.search(
        r"\bLetter\b",
        last_text,
        flags=re.IGNORECASE,
    ):
        return (
            True,
            "Letter service was not displayed",
        )

    return (
        True,
        "Price (KHR) was not displayed "
        "for Letter",
    )


# ============================================================
# TEST ONE COUNTRY
# ============================================================

def test_country(
    page: Page,
    country: Country,
) -> tuple[bool, str]:

    print(
        f"Testing: "
        f"{country.display_name}"
    )

    # --------------------------------------------------------
    # REQUIRED ORDER
    #
    # 1. Select country
    # 2. Enter 0.02
    # 3. Click Calculate
    # 4. Analyze result
    # --------------------------------------------------------

    select_country(
        page,
        country,
    )

    set_weight(
        page,
    )

    calculate_button = find_calculate_button(
        page
    )

    if calculate_button is None:
        raise RuntimeError(
            "Calculate button could not be found."
        )

    print(
        "  Clicking Calculate..."
    )

    calculate_button.click()

    suspended, reason = analyze_result(
        page
    )

    if suspended:

        print(
            f"  -> SUSPENDED: "
            f"{reason}"
        )

    else:

        print(
            f"  -> ACTIVE: "
            f"{reason}"
        )

    return (
        suspended,
        reason,
    )


# ============================================================
# TEST ALL COUNTRIES
# ============================================================

def test_all_countries(
    page: Page,
    countries: list[Country],
) -> list[Country]:

    suspended: list[Country] = []

    total = len(
        countries
    )

    print()
    print(
        "============================================================"
    )
    print(
        f"TESTING {total} COUNTRIES"
    )
    print(
        "============================================================"
    )

    for index, country in enumerate(
        countries,
        start=1,
    ):

        print()
        print(
            "------------------------------------------------------------"
        )

        print(
            f"[{index}/{total}] "
            f"{country.display_name}"
        )

        print(
            "------------------------------------------------------------"
        )

        try:

            is_suspended, reason = test_country(
                page,
                country,
            )

            if is_suspended:
                suspended.append(
                    country
                )

        except Exception as exc:

            print(
                f"  -> TECHNICAL ERROR: "
                f"{exc}"
            )

            # A technical Playwright error is NOT
            # automatically considered suspension.

            try:

                print(
                    "  Reloading calculator..."
                )

                page.reload(
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                time.sleep(
                    3
                )

                # Cambodia Post starts with an empty
                # Select2 country field again, so repopulate it.
                populate_country_select(
                    page,
                    countries,
                )

            except Exception as reload_exc:

                print(
                    "  Reload/repopulate error:",
                    reload_exc,
                )

    return suspended


# ============================================================
# OUTPUT FILE
# ============================================================

def write_output(
    countries: list[Country],
    suspended: list[Country],
) -> None:

    checked = datetime.now().astimezone()

    lines: list[str] = []

    lines.append(
        "Cambodia Post International Shipping Monitor"
    )

    lines.append(
        "Checked: "
        + checked.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    )

    lines.append(
        f"Website: {URL}"
    )

    lines.append(
        f"Weight tested: {WEIGHT} kg"
    )

    lines.append("")

    # --------------------------------------------------------
    # LIST 1
    # --------------------------------------------------------

    lines.append(
        "LIST 1 - ALL COUNTRIES"
    )

    lines.append(
        f"Total countries: "
        f"{len(countries)}"
    )

    lines.append("")

    for country in countries:

        lines.append(
            country.display_name
        )

    lines.append("")

    # --------------------------------------------------------
    # LIST 2
    # --------------------------------------------------------

    lines.append(
        "LIST 2 - SUSPENDED DESTINATIONS"
    )

    lines.append(
        f"Total suspended destinations: "
        f"{len(suspended)}"
    )

    lines.append("")

    for country in suspended:

        lines.append(
            country.display_name
        )

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print(
        "============================================================"
    )
    print(
        "OUTPUT CREATED"
    )
    print(
        "============================================================"
    )

    print(
        f"Total countries: "
        f"{len(countries)}"
    )

    print(
        f"Suspended destinations: "
        f"{len(suspended)}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print(
        "Opening Cambodia Post international calculator..."
    )

    with sync_playwright() as playwright:

        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context: BrowserContext = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="en-US",
        )

        page: Page = context.new_page()

        page.set_default_timeout(
            PAGE_TIMEOUT
        )

        page.on(
            "console",
            lambda message: (
                print(
                    f"[Browser {message.type.upper()}] "
                    f"{message.text}"
                )
                if message.type in {
                    "error",
                    "warning",
                }
                else None
            ),
        )

        try:

            # ------------------------------------------------
            # Open calculator.
            # ------------------------------------------------

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            print(
                f"Page loaded: {page.url}"
            )

            time.sleep(
                5
            )

            # ------------------------------------------------
            # Fetch all countries from the actual
            # Cambodia Post Select2 API.
            # ------------------------------------------------

            countries = fetch_all_countries()

            print()
            print(
                "============================================================"
            )

            print(
                f"DISCOVERED {len(countries)} COUNTRIES"
            )

            print(
                "============================================================"
            )

            for index, country in enumerate(
                countries,
                start=1,
            ):

                print(
                    f"{index}. "
                    f"{country.display_name} "
                    f"[id={country.country_id}, "
                    f"code={country.code}]"
                )

            # ------------------------------------------------
            # Populate the actual Select2 country field.
            # ------------------------------------------------

            populate_country_select(
                page,
                countries,
            )

            # ------------------------------------------------
            # Test all destinations.
            # ------------------------------------------------

            suspended = test_all_countries(
                page,
                countries,
            )

            # ------------------------------------------------
            # Write final monitoring output.
            # ------------------------------------------------

            write_output(
                countries,
                suspended,
            )

            print()
            print(
                "============================================================"
            )

            print(
                "MONITOR COMPLETED SUCCESSFULLY"
            )

            print(
                "============================================================"
            )

        except Exception as exc:

            print()
            print(
                "============================================================"
            )

            print(
                "MONITOR FAILED"
            )

            print(
                "============================================================"
            )

            print(
                str(exc)
            )

            print(
                "============================================================"
            )

            save_debug(
                page
            )

            raise

        finally:

            try:
                context.close()
            except Exception:
                pass

            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
