import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
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

# Keep these reasonably short so a bad country does not
# consume a very long time.
SELECTION_TIMEOUT = 8_000
CALCULATION_RESPONSE_TIMEOUT = 10_000
RESULT_TIMEOUT = 10_000


KHMER_LOCALE = Locale("km")
ENGLISH_LOCALE = Locale("en")


# ============================================================
# COUNTRY DATA
# ============================================================

@dataclass
class Country:
    country_id: str
    code: str
    english_name: str
    khmer_name: str
    api_text: str

    @property
    def display_name(self) -> str:
        return f"{self.khmer_name} — {self.english_name}"


# ============================================================
# COUNTRY API
# ============================================================

def fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": URL,
        },
        method="GET",
    )

    with urlopen(request, timeout=API_TIMEOUT) as response:
        raw = response.read().decode("utf-8")

    return json.loads(raw)


def extract_country_code(api_text: str) -> str:
    match = re.match(
        r"^\s*([A-Z]{2})\s*\(",
        api_text or "",
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return ""


def english_country_name(
    code: str,
    api_name: str,
) -> str:

    code = (code or "").upper()

    if code:
        try:
            name = ENGLISH_LOCALE.territories.get(code)

            if name:
                return str(name)
        except Exception:
            pass

    cleaned = re.sub(
        r"^\s*[A-Z]{2}\s*\(\s*",
        "",
        api_name or "",
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*\)\s*$",
        "",
        cleaned,
    )

    return cleaned.strip() or api_name.strip()


def khmer_country_name(code: str) -> str:

    code = (code or "").upper()

    if code:
        try:
            name = KHMER_LOCALE.territories.get(code)

            if name:
                return str(name)
        except Exception:
            pass

    return ""


def fetch_all_countries() -> list[Country]:

    print()
    print("=" * 60)
    print("COUNTRY API DISCOVERY")
    print("=" * 60)

    countries: list[Country] = []
    seen_ids: set[str] = set()

    page_number = 1

    while True:

        api_url = f"{COUNTRY_API}?page={page_number}"

        print()
        print(
            f"Fetching country API page {page_number}..."
        )

        try:
            payload = fetch_json(api_url)

        except HTTPError as exc:
            raise RuntimeError(
                f"Country API returned HTTP {exc.code} "
                f"on page {page_number}"
            ) from exc

        except URLError as exc:
            raise RuntimeError(
                f"Could not reach country API on "
                f"page {page_number}: {exc}"
            ) from exc

        except Exception as exc:
            raise RuntimeError(
                f"Could not read country API page "
                f"{page_number}: {exc}"
            ) from exc

        records = payload.get("data") or []

        print(
            f"  Received {len(records)} country records."
        )

        for record in records:

            country_id = str(
                record.get("id", "")
            ).strip()

            api_text = str(
                record.get("text", "")
            ).strip()

            if not country_id or not api_text:
                continue

            if country_id in seen_ids:
                continue

            code = extract_country_code(api_text)

            english_name = english_country_name(
                code,
                api_text,
            )

            khmer_name = khmer_country_name(code)

            if not khmer_name:
                khmer_name = english_name

            countries.append(
                Country(
                    country_id=country_id,
                    code=code,
                    english_name=english_name,
                    khmer_name=khmer_name,
                    api_text=api_text,
                )
            )

            seen_ids.add(country_id)

        last_page = payload.get("last_page")

        try:
            last_page = int(last_page)
        except (TypeError, ValueError):
            last_page = None

        if last_page is not None:

            if page_number >= last_page:
                break

        else:

            if not records:
                break

        page_number += 1

        if page_number > 1000:
            raise RuntimeError(
                "Country API pagination exceeded 1000 pages."
            )

    try:
        DEBUG_API.write_text(
            json.dumps(
                {
                    "fetched_at": datetime.now().isoformat(),
                    "total_countries": len(countries),
                    "countries": [
                        {
                            "id": country.country_id,
                            "code": country.code,
                            "api_text": country.api_text,
                            "english_name": country.english_name,
                            "khmer_name": country.khmer_name,
                        }
                        for country in countries
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        print(
            f"Warning: could not save API debug file: {exc}"
        )

    print()
    print(
        f"TOTAL COUNTRIES FOUND: {len(countries)}"
    )

    if not countries:
        raise RuntimeError(
            "Cambodia Post country API returned zero countries."
        )

    return countries


# ============================================================
# PAGE ELEMENTS
# ============================================================

def find_country_select(page: Page):
    selectors = [
        "select#country_id",
        "select[name='country_id']",
        "select[aria-label='Select country']",
    ]

    for selector in selectors:

        locator = page.locator(selector).first

        try:
            if locator.count() > 0:
                return locator
        except Exception:
            pass

    return None


def find_weight_input(page: Page):

    selectors = [
        "input[placeholder*='បញ្ចូលទម្ងន់']",
        "input[name*='weight']",
        "input[id*='weight']",
        "input[type='number']",
        "input[type='text']",
    ]

    for selector in selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

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
        "input[type='button']",
        "input[type='submit']",
    ]

    for selector in selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):

            candidate = locator.nth(index)

            try:

                if not candidate.is_visible():
                    continue

                tag_name = candidate.evaluate(
                    "(element) => element.tagName.toLowerCase()"
                )

                if tag_name == "button":
                    text = candidate.inner_text(
                        timeout=1000
                    )
                else:
                    text = (
                        candidate.get_attribute("value")
                        or ""
                    )

                normalized = text.strip().lower()

                if (
                    "calculate" in normalized
                    or "គណនា" in normalized
                ):
                    return candidate

            except Exception:
                continue

    return None


# ============================================================
# DEBUG
# ============================================================

def save_debug(page: Page) -> None:

    try:
        DEBUG_HTML.write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception as exc:
        print(
            f"Warning: could not save debug HTML: {exc}"
        )

    try:
        page.screenshot(
            path=str(DEBUG_PNG),
            full_page=True,
        )
    except Exception as exc:
        print(
            f"Warning: could not save debug PNG: {exc}"
        )


# ============================================================
# COUNTRY SELECTION
# ============================================================

def ensure_country_option(
    page: Page,
    country: Country,
) -> bool:

    select = find_country_select(page)

    if select is None:
        print(
            "  -> Country select was not found."
        )
        return False

    try:

        result = page.evaluate(
            """
            (data) => {
                const select =
                    document.querySelector("#country_id") ||
                    document.querySelector(
                        'select[name="country_id"]'
                    );

                if (!select) {
                    return {
                        ok: false,
                        reason: "country select not found"
                    };
                }

                const wantedValue =
                    String(data.countryId);

                let option = Array.from(
                    select.options
                ).find(
                    item =>
                        String(item.value) ===
                        wantedValue
                );

                if (!option) {
                    option = new Option(
                        data.apiText,
                        wantedValue,
                        false,
                        false
                    );

                    select.add(option);
                }

                return {
                    ok: true,
                    value: String(option.value),
                    text: option.text
                };
            }
            """,
            {
                "countryId": country.country_id,
                "apiText": country.api_text,
            },
        )

        return bool(
            result and result.get("ok")
        )

    except Exception as exc:

        print(
            f"  -> Could not create country option: {exc}"
        )

        return False


def select_country(
    page: Page,
    country: Country,
) -> bool:

    print(
        f"  Selecting: {country.display_name}"
    )

    if not ensure_country_option(
        page,
        country,
    ):
        return False

    try:

        result = page.evaluate(
            """
            (data) => {
                const select =
                    document.querySelector("#country_id") ||
                    document.querySelector(
                        'select[name="country_id"]'
                    );

                if (!select) {
                    return {
                        ok: false,
                        reason: "country select not found"
                    };
                }

                const wantedValue =
                    String(data.countryId);

                let option = Array.from(
                    select.options
                ).find(
                    item =>
                        String(item.value) ===
                        wantedValue
                );

                if (!option) {
                    option = new Option(
                        data.apiText,
                        wantedValue,
                        true,
                        true
                    );

                    select.add(option);
                }

                option.selected = true;
                select.value = wantedValue;

                /*
                 * Trigger the native change event.
                 */
                select.dispatchEvent(
                    new Event(
                        "change",
                        {
                            bubbles: true
                        }
                    )
                );

                /*
                 * Trigger jQuery/Select2 events when
                 * jQuery is available.
                 */
                if (window.jQuery) {

                    const jq =
                        window.jQuery(select);

                    jq.val(wantedValue);

                    jq.trigger("change");

                    jq.trigger({
                        type: "select2:select",
                        params: {
                            data: {
                                id: wantedValue,
                                text: data.apiText
                            }
                        }
                    });
                }

                return {
                    ok: true,
                    value: String(select.value),
                    optionCount: select.options.length
                };
            }
            """,
            {
                "countryId": country.country_id,
                "apiText": country.api_text,
            },
        )

        if not result or not result.get("ok"):
            return False

    except Exception as exc:

        print(
            f"  -> Country selection failed: {exc}"
        )

        return False

    deadline = (
        time.time()
        + SELECTION_TIMEOUT / 1000
    )

    while time.time() < deadline:

        try:

            current_value = page.evaluate(
                """
                () => {
                    const select =
                        document.querySelector(
                            "#country_id"
                        ) ||
                        document.querySelector(
                            'select[name="country_id"]'
                        );

                    return select
                        ? String(select.value)
                        : "";
                }
                """
            )

            if str(current_value) == str(
                country.country_id
            ):
                return True

        except Exception:
            pass

        time.sleep(0.15)

    print(
        "  -> Country value did not become active."
    )

    return False


# ============================================================
# WEIGHT
# ============================================================

def set_weight(
    page: Page,
    weight: str,
) -> bool:

    weight_input = find_weight_input(page)

    if weight_input is None:
        print(
            "  -> Weight input was not found."
        )
        return False

    try:

        weight_input.fill(weight)

        try:
            weight_input.press("Tab")
        except Exception:
            pass

        return True

    except Exception as exc:

        print(
            f"  -> Could not enter weight: {exc}"
        )

        return False


# ============================================================
# RESULT HELPERS
# ============================================================

def body_text(page: Page) -> str:

    try:
        return page.locator("body").inner_text(
            timeout=3000
        )
    except Exception:
        return ""


def has_error_message(text: str) -> bool:

    lowered = text.lower()

    error_patterns = [
        "an error occurred",
        "error occurred",
        "something went wrong",
        "unable to calculate",
        "failed to calculate",
        "calculation failed",
        "invalid weight",
        "please select country",
        "please select a country",
        "មិនអាចគណនា",
        "មានបញ្ហា",
        "កំហុស",
        "សូមជ្រើសរើសប្រទេស",
    ]

    return any(
        pattern in lowered
        for pattern in error_patterns
    )


def extract_letter_section(text: str) -> str:

    match = re.search(
        r"(?is).{0,500}\bLetter\b.{0,1500}",
        text,
    )

    if match:
        return match.group(0)

    return ""


def letter_has_price(
    letter_section: str,
) -> bool:

    if not letter_section:
        return False

    lowered = letter_section.lower()

    currency_found = any(
        marker in lowered
        for marker in [
            "price",
            "khr",
            "៛",
            "រៀល",
        ]
    )

    if not currency_found:
        return False

    number_found = re.search(
        r"\b\d[\d,\s]*(?:\.\d+)?\b",
        letter_section,
    )

    return number_found is not None


# ============================================================
# CALCULATE
# ============================================================

def click_calculate_and_wait(
    page: Page,
    before_text: str,
) -> tuple[str, str]:

    button = find_calculate_button(page)

    if button is None:
        return (
            "technical",
            "Calculate button was not found",
        )

    response_seen = False

    try:

        with page.expect_response(
            lambda response:
                CALCULATION_ENDPOINT
                in response.url,
            timeout=CALCULATION_RESPONSE_TIMEOUT,
        ) as response_info:

            button.click()

        response = response_info.value

        response_seen = True

        print(
            "  -> Calculation response received: "
            f"HTTP {response.status}"
        )

        # If the server explicitly returned an HTTP
        # error, allow the result parser to inspect the
        # page before classifying it.
        time.sleep(0.25)

    except PlaywrightTimeoutError:

        print(
            "  -> No calculation API response detected; "
            "checking page result..."
        )

    except Exception as exc:

        print(
            "  -> Calculation response monitoring error: "
            f"{exc}"
        )

    deadline = (
        time.time()
        + RESULT_TIMEOUT / 1000
    )

    while time.time() < deadline:

        current_text = body_text(page)

        if not current_text:
            time.sleep(0.25)
            continue

        if has_error_message(current_text):

            return (
                "suspended",
                "Error message displayed after Calculate",
            )

        letter_section = extract_letter_section(
            current_text
        )

        if letter_section:

            if letter_has_price(letter_section):

                return (
                    "available",
                    letter_section,
                )

        time.sleep(0.30)

    # Final inspection.
    final_text = body_text(page)

    if has_error_message(final_text):

        return (
            "suspended",
            "Error message displayed after Calculate",
        )

    letter_section = extract_letter_section(
        final_text
    )

    if not letter_section:

        return (
            "suspended",
            "Letter service was not displayed",
        )

    if not letter_has_price(letter_section):

        return (
            "suspended",
            "Letter service displayed without Price (KHR)",
        )

    if not response_seen:

        return (
            "technical",
            "No calculation response or usable result",
        )

    return (
        "available",
        letter_section,
    )


# ============================================================
# TEST ONE COUNTRY
# ============================================================

def test_country(
    page: Page,
    country: Country,
    index: int,
    total: int,
) -> tuple[str, str]:

    print()
    print(
        f"Testing {index}/{total}: "
        f"{country.display_name}"
    )

    # --------------------------------------------------------
    # 1. Select country
    # --------------------------------------------------------

    if not select_country(
        page,
        country,
    ):

        return (
            "technical",
            "Country could not be selected",
        )

    # --------------------------------------------------------
    # 2. Enter weight
    # --------------------------------------------------------

    if not set_weight(
        page,
        WEIGHT,
    ):

        return (
            "technical",
            "Weight input could not be filled",
        )

    # --------------------------------------------------------
    # Capture current body text before Calculate.
    # --------------------------------------------------------

    before_text = body_text(page)

    # --------------------------------------------------------
    # 3. Click Calculate
    # --------------------------------------------------------

    status, detail = (
        click_calculate_and_wait(
            page,
            before_text,
        )
    )

    # --------------------------------------------------------
    # 4. Analyze result
    # --------------------------------------------------------

    if status == "available":

        print(
            "  -> AVAILABLE: "
            "Letter + Price (KHR) found"
        )

        return status, detail

    if status == "suspended":

        print(
            f"  -> SUSPENDED: {detail}"
        )

        return status, detail

    print(
        f"  -> TECHNICAL ERROR: {detail}"
    )

    return (
        "technical",
        detail,
    )


# ============================================================
# PAGE PREPARATION
# ============================================================

def prepare_page(page: Page) -> None:

    print()
    print(
        "Opening Cambodia Post international calculator..."
    )

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=10_000,
        )

    except PlaywrightTimeoutError:
        pass

    print(
        f"Page loaded: {page.url}"
    )

    # Give the site's JavaScript and Select2 time to
    # initialize.
    time.sleep(1.5)

    if find_country_select(page) is None:
        raise RuntimeError(
            "Country select was not found."
        )

    if find_weight_input(page) is None:
        raise RuntimeError(
            "Weight input was not found."
        )

    if find_calculate_button(page) is None:
        raise RuntimeError(
            "Calculate button was not found."
        )


# ============================================================
# TEST ALL COUNTRIES
# =====================================================
