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
    TimeoutError as PlaywrightTimeoutError,
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

# How long to wait for the calculation result.
RESULT_TIMEOUT = 15_000

# How long to wait for the calculation API response.
CALCULATION_RESPONSE_TIMEOUT = 12_000

# How long a technical country-selection failure gets before
# being reported and moving on.
SELECTION_TIMEOUT = 8_000

API_TIMEOUT = 60

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
# HTTP / API
# ============================================================

def fetch_json(url: str) -> dict[str, Any]:
    """
    Fetch JSON directly from Cambodia Post.

    This is intentionally separate from Playwright because the
    browser's Select2 AJAX resources can be blocked by the site,
    while the country API itself is directly accessible.
    """

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
    """
    Cambodia Post currently returns records such as:

        AE (UNITED ARAB EMIRATES)

    Extract the two-letter ISO-style code.
    """

    match = re.match(
        r"^\s*([A-Z]{2})\s*\(",
        api_text or "",
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return ""


def english_country_name(code: str, api_name: str) -> str:
    """
    Prefer Babel's English territory name.

    Fall back to the API's name if Babel does not know the code.
    """

    code = (code or "").upper()

    if code:
        try:
            name = ENGLISH_LOCALE.territories.get(code)

            if name:
                return str(name)
        except Exception:
            pass

    # Remove the "XX (" and trailing ")" formatting if present.
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
    """
    Prefer Babel's Khmer territory name.
    """

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
    """
    Download every Cambodia Post country API page.

    The API is paginated. We continue until last_page.
    """

    print()
    print("=" * 60)
    print("COUNTRY API DISCOVERY")
    print("=" * 60)

    all_countries: list[Country] = []
    seen_ids: set[str] = set()

    page_number = 1

    while True:
        api_url = f"{COUNTRY_API}?page={page_number}"

        print()
        print(f"Fetching country API page {page_number}...")

        try:
            payload = fetch_json(api_url)
        except HTTPError as exc:
            raise RuntimeError(
                f"Country API returned HTTP {exc.code} "
                f"for page {page_number}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach Cambodia Post country API "
                f"for page {page_number}: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Could not read country API page {page_number}: {exc}"
            ) from exc

        records = payload.get("data") or []

        print(f"  Received {len(records)} country records.")

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
                # If Babel does not provide a Khmer name,
                # retain the API name as a safe fallback.
                khmer_name = english_name

            all_countries.append(
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

        if last_page is not None:
            try:
                last_page = int(last_page)
            except (TypeError, ValueError):
                last_page = None

        if last_page is not None:
            if page_number >= last_page:
                break
        else:
            # If pagination metadata is missing, stop when the
            # current page contains no records.
            if not records:
                break

        page_number += 1

        # Safety guard against a broken API.
        if page_number > 1000:
            raise RuntimeError(
                "Country API pagination exceeded 1000 pages."
            )

    # Save the raw API information for diagnostics.
    try:
        DEBUG_API.write_text(
            json.dumps(
                {
                    "fetched_at": datetime.now().isoformat(),
                    "total_countries": len(all_countries),
                    "countries": [
                        {
                            "id": c.country_id,
                            "code": c.code,
                            "api_text": c.api_text,
                            "english_name": c.english_name,
                            "khmer_name": c.khmer_name,
                        }
                        for c in all_countries
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Warning: could not save API debug file: {exc}")

    print()
    print(f"TOTAL COUNTRIES FOUND: {len(all_countries)}")

    if not all_countries:
        raise RuntimeError(
            "Cambodia Post country API returned zero countries."
        )

    return all_countries


# ============================================================
# PAGE HELPERS
# ============================================================

def find_country_select(page: Page):
    """
    Find the actual Country select.

    Cambodia Post currently uses:

        <select id="country_id" name="country_id">

    and Select2 hides the native select.
    """

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
    """
    Locate the weight input.
    """

    selectors = [
        "input[placeholder*='បញ្ចូលទម្ងន់']",
        "input[name*='weight']",
        "input[id*='weight']",
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
    """
    Locate the Calculate button.
    """

    selectors = [
        "button",
        "input[type='button']",
        "input[type='submit']",
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
                    candidate.inner_text(timeout=1000)
                    if candidate.evaluate(
                        "(el) => el.tagName.toLowerCase() === 'button'"
                    )
                    else candidate.get_attribute("value") or ""
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


def save_debug(page: Page) -> None:
    """
    Save the current page for diagnostics.
    """

    try:
        DEBUG_HTML.write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Warning: could not save debug HTML: {exc}")

    try:
        page.screenshot(
            path=str(DEBUG_PNG),
            full_page=True,
        )
    except Exception as exc:
        print(f"Warning: could not save debug PNG: {exc}")


# ============================================================
# SELECT2 COUNTRY SELECTION
# ============================================================

def ensure_country_option(
    page: Page,
    country: Country,
) -> bool:
    """
    Add exactly one country option to the hidden native select.

    IMPORTANT:
    We deliberately do NOT use Playwright select_option().

    Select2 hides the native select and manages the selection
    through its own jQuery API.
    """

    select = find_country_select(page)

    if select is None:
        print("  -> Country select was not found.")
        return False

    try:
        result = page.evaluate(
            """
            ({countryId, apiText}) => {
                const select =
                    document.querySelector('#country_id') ||
                    document.querySelector('select[name="country_id"]');

                if (!select) {
                    return {
                        ok: false,
                        reason: "country select not found"
                    };
                }

                let option = Array.from(
                    select.options
                ).find(
                    o => String(o.value) === String(countryId)
                );

                if (!option) {
                    option = new Option(
                        apiText,
                        String(countryId),
                        false,
                        false
                    );

                    select.add(option);
                }

                return {
                    ok: true,
                    optionValue: option.value,
                    optionText: option.text
                };
            }
            """,
            {
                "countryId": country.country_id,
                "apiText": country.api_text,
            },
        )

        return bool(result and result.get("ok"))

    except Exception as exc:
        print(f"  -> Could not create country option: {exc}")
        return False


def select_country(
    page: Page,
    country: Country,
) -> bool:
    """
    Select a country through Select2's jQuery API.

    This avoids Playwright's select_option(), which was timing out
    because the Select2-hidden select was not exposing the injected
    option to Playwright's option-selection machinery.
    """

    print(f"  Selecting: {country.display_name}")

    if not ensure_country_option(page, country):
        return False

    try:
        result = page.evaluate(
            """
            ({countryId, apiText}) => {
                const select =
                    document.querySelector('#country_id') ||
                    document.querySelector('select[name="country_id"]');

                if (!select) {
                    return {
                        ok: false,
                        reason: "country select not found"
                    };
                }

                const value = String(countryId);

                let option = Array.from(
                    select.options
                ).find(
                    o => String(o.value) === value
                );

                if (!option) {
                    option = new Option(
                        apiText,
                        value,
                        true,
                        true
                    );

                    select.add(option);
                } else {
                    option.text = apiText;
                    option.selected = true;
                }

                select.value = value;

                // Trigger the native change event.
                select.dispatchEvent(
                    new Event("change", {
                        bubbles: true
                    })
                );

                // Then use jQuery if it is available.
                if (window.jQuery) {
                    const jq = window.jQuery(select);

                    jq.val(value);
                    jq.trigger("change");

                    // Select2-specific event.
                    jq.trigger({
                        type: "select2:select",
                        params: {
                            data: {
                                id: value,
                                text: apiText
                            }
                        }
                    });
                }

                return {
                    ok: true,
                    value: select.value,
                    opt
