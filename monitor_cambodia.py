import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Response,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# CONFIGURATION
# ============================================================

URL = "https://www.cambodiapost.com.kh/calculate/international"

OUTPUT_FILE = Path("output_cambodia.txt")

DEBUG_HTML = Path("debug_cambodiapost.html")
DEBUG_PNG = Path("debug_cambodiapost.png")
DEBUG_NETWORK = Path("debug_cambodiapost_network.txt")
DEBUG_DATA = Path("debug_cambodiapost_data.json")

WEIGHT = "0.02"

PAGE_TIMEOUT = 60_000
RESULT_TIMEOUT = 30_000

COUNTRY_DISCOVERY_TIMEOUT = 45_000


# ============================================================
# KHMER -> ENGLISH COUNTRY NAMES
# ============================================================

COUNTRY_TRANSLATIONS = {
    "អាល់ហ្សេរី": "Algeria",
    "អង់ហ្គោឡា": "Angola",
    "អាហ្សង់ទីន": "Argentina",
    "អាមេនី": "Armenia",
    "អូស្ត្រាលី": "Australia",
    "អូទ្រីស": "Austria",
    "អាស៊ែបៃហ្សង់": "Azerbaijan",
    "បង់ក្លាដែស": "Bangladesh",
    "បែលហ្សិក": "Belgium",
    "ប្រេស៊ីល": "Brazil",
    "ប្រ៊ុយណេ": "Brunei",
    "ប៊ុលហ្គារី": "Bulgaria",
    "កាណាដា": "Canada",
    "ឈីលី": "Chile",
    "ចិន": "China",
    "កូឡុំប៊ី": "Colombia",
    "កូតឌីវ័រ": "Cote d'Ivoire",
    "ក្រូអាត": "Croatia",
    "ស៊ីប": "Cyprus",
    "សាធារណរដ្ឋឆែក": "Czech Republic",
    "ឆែក": "Czech Republic",
    "ដាណឺម៉ាក": "Denmark",
    "ជីប៊ូទី": "Djibouti",
    "អេក្វាឌ័រ": "Ecuador",
    "អេហ្ស៊ីប": "Egypt",
    "អេស្តូនី": "Estonia",
    "អេត្យូពី": "Ethiopia",
    "ហ្វាំងឡង់": "Finland",
    "បារាំង": "France",
    "ហ្សកហ្ស៊ី": "Georgia",
    "អាល្លឺម៉ង់": "Germany",
    "ក្រិក": "Greece",
    "ហុងគ្រី": "Hungary",
    "ឥណ្ឌា": "India",
    "ឥណ្ឌូនេស៊ី": "Indonesia",
    "អ៊ីរ៉ង់": "Iran",
    "អ៊ីរ៉ាក់": "Iraq",
    "អៀរឡង់": "Ireland",
    "អ៊ីស្រាអែល": "Israel",
    "អ៊ីតាលី": "Italy",
    "ជប៉ុន": "Japan",
    "ហ្សកដានី": "Jordan",
    "កាហ្សាក់ស្ថាន": "Kazakhstan",
    "កេនយ៉ា": "Kenya",
    "កូរ៉េ": "South Korea",
    "កូរ៉េខាងត្បូង": "South Korea",
    "គុយវ៉ែត": "Kuwait",
    "ឡាវ": "Laos",
    "ឡាតវី": "Latvia",
    "លីបង់": "Lebanon",
    "លីទុយអានី": "Lithuania",
    "លុចសំបួ": "Luxembourg",
    "ម៉ាឡេស៊ី": "Malaysia",
    "ម៉ាល់ឌីវ": "Maldives",
    "ម៉ាល់តា": "Malta",
    "ម៉ិកស៊ិក": "Mexico",
    "ម៉ុងហ្គោលី": "Mongolia",
    "ម៉ារ៉ុក": "Morocco",
    "មីយ៉ាន់ម៉ា": "Myanmar",
    "នេប៉ាល់": "Nepal",
    "ហូឡង់": "Netherlands",
    "នូវែលសេឡង់": "New Zealand",
    "នីហ្សេរីយ៉ា": "Nigeria",
    "ន័រវែស": "Norway",
    "អូម៉ង់": "Oman",
    "ប៉ាគីស្ថាន": "Pakistan",
    "ប៉េរូ": "Peru",
    "ហ្វីលីពីន": "Philippines",
    "ប៉ូឡូញ": "Poland",
    "ព័រទុយហ្គាល់": "Portugal",
    "កាតា": "Qatar",
    "រូម៉ានី": "Romania",
    "រុស្ស៊ី": "Russia",
    "អារ៉ាប៊ីសាអូឌីត": "Saudi Arabia",
    "ស៊ែប៊ី": "Serbia",
    "សិង្ហបុរី": "Singapore",
    "ស្លូវ៉ាគី": "Slovakia",
    "ស្លូវេនី": "Slovenia",
    "អាហ្វ្រិកខាងត្បូង": "South Africa",
    "អេស្ប៉ាញ": "Spain",
    "ស្រីលង្កា": "Sri Lanka",
    "ស៊ូដង់": "Sudan",
    "ស៊ុយអែត": "Sweden",
    "ស្វីស": "Switzerland",
    "ស៊ីរី": "Syria",
    "តៃវ៉ាន់": "Taiwan",
    "តង់ហ្សានី": "Tanzania",
    "ថៃ": "Thailand",
    "ទុយនេស៊ី": "Tunisia",
    "តួកគី": "Turkey",
    "អ៊ុយក្រែន": "Ukraine",
    "អេមីរ៉ាតអារ៉ាប់រួម": "United Arab Emirates",
    "អង់គ្លេស": "United Kingdom",
    "ចក្រភពអង់គ្លេស": "United Kingdom",
    "សហរដ្ឋអាមេរិក": "United States",
    "អាមេរិក": "United States",
    "អ៊ុយរូហ្គាយ": "Uruguay",
    "អ៊ូសបេគីស្ថាន": "Uzbekistan",
    "វៀតណាម": "Vietnam",
    "យេម៉ែន": "Yemen",
    "សំប៊ី": "Zambia",
    "ហ្ស៊ីមបាវ៉េ": "Zimbabwe",
}


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Country:
    website_name: str
    english_name: str
    value: str = ""

    @property
    def display_name(self) -> str:
        if self.english_name and self.english_name != self.website_name:
            return f"{self.website_name} — {self.english_name}"

        return self.website_name


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def is_placeholder(text: str) -> bool:
    value = clean_text(text).lower()

    if not value:
        return True

    placeholders = {
        "select",
        "choose",
        "country",
        "ជ្រើសរើសប្រទេស",
        "ជ្រើសរើស",
        "select country",
        "please select",
        "-- select --",
        "---",
    }

    if value in placeholders:
        return True

    if "ជ្រើសរើសប្រទេស" in value:
        return True

    return False


def translate_country(name: str) -> str:
    name = clean_text(name)

    if not name:
        return ""

    if name in COUNTRY_TRANSLATIONS:
        return COUNTRY_TRANSLATIONS[name]

    # Sometimes the site contains punctuation around the name.
    simplified = re.sub(r"[៖:,，。.\-]+$", "", name).strip()

    if simplified in COUNTRY_TRANSLATIONS:
        return COUNTRY_TRANSLATIONS[simplified]

    # If the site already gives English, keep it.
    if re.fullmatch(r"[A-Za-z][A-Za-z .,'()&\-]+", name):
        return name

    return name


def normalize_country_key(name: str) -> str:
    return re.sub(r"\s+", " ", clean_text(name)).casefold()


# ============================================================
# NETWORK CAPTURE
# ============================================================

class NetworkCapture:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []

    def on_request(self, request) -> None:
        try:
            resource_type = request.resource_type

            if resource_type not in {
                "xhr",
                "fetch",
                "document",
                "script",
            }:
                return

            url = request.url

            self.records.append(
                {
                    "type": "request",
                    "resource_type": resource_type,
                    "method": request.method,
                    "url": url,
                }
            )
        except Exception:
            pass

    def on_response(self, response: Response) -> None:
        try:
            request = response.request
            resource_type = request.resource_type
            url = response.url

            if resource_type not in {"xhr", "fetch"}:
                return

            record = {
                "type": "response",
                "resource_type": resource_type,
                "status": response.status,
                "url": url,
                "content_type": response.headers.get("content-type", ""),
            }

            interesting = any(
                word in url.lower()
                for word in [
                    "country",
                    "countries",
                    "destination",
                    "calculate",
                    "international",
                    "price",
                    "service",
                ]
            )

            if interesting or response.status >= 400:
                try:
                    text = response.text()

                    if len(text) > 500_000:
                        text = text[:500_000]

                    record["body"] = text
                except Exception as exc:
                    record["body_error"] = str(exc)

            self.responses.append(record)

        except Exception:
            pass

    def save(self) -> None:
        combined = {
            "requests": self.records,
            "responses": self.responses,
        }

        DEBUG_NETWORK.write_text(
            json.dumps(
                combined,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


# ============================================================
# JAVASCRIPT DIAGNOSTICS
# ============================================================

def attach_console_diagnostics(page: Page) -> None:
    def on_console(message) -> None:
        try:
            if message.type in {"error", "warning"}:
                print(
                    f"[Browser {message.type.upper()}] "
                    f"{message.text}"
                )
        except Exception:
            pass

    def on_page_error(error) -> None:
        try:
            print(f"[Browser PAGE ERROR] {error}")
        except Exception:
            pass

    page.on("console", on_console)
    page.on("pageerror", on_page_error)


# ============================================================
# SAVE DEBUG INFORMATION
# ============================================================

def save_debug(page: Page, network: NetworkCapture | None = None) -> None:
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

    if network is not None:
        try:
            network.save()
        except Exception:
            pass


# ============================================================
# COUNTRY EXTRACTION FROM JSON
# ============================================================

COUNTRY_NAME_KEYS = {
    "country",
    "countryname",
    "country_name",
    "name",
    "displayname",
    "display_name",
    "title",
    "label",
    "description",
    "khmername",
    "khmer_name",
    "namekh",
    "name_kh",
    "nameen",
    "name_en",
    "englishname",
    "english_name",
}

VALUE_KEYS = {
    "id",
    "value",
    "code",
    "countrycode",
    "country_code",
    "iso",
    "iso2",
    "iso_code",
}


def looks_like_country_name(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    text = clean_text(value)

    if not text:
        return False

    if len(text) > 100:
        return False

    if is_placeholder(text):
        return False

    # Khmer text or ordinary English country-like text.
    has_khmer = bool(
        re.search(
            r"[\u1780-\u17ff]",
            text,
        )
    )

    has_latin = bool(
        re.search(
            r"[A-Za-z]",
            text,
        )
    )

    return has_khmer or has_latin


def object_to_country(obj: dict[str, Any]) -> Country | None:
    normalized = {
        str(key).strip().lower().replace("-", "_"): value
        for key, value in obj.items()
    }

    name_candidates: list[str] = []

    for key, value in normalized.items():
        compact = key.replace("_", "")

        if (
            key in COUNTRY_NAME_KEYS
            or compact in {
                "countryname",
                "displayname",
                "khmername",
                "englishname",
            }
        ):
            if looks_like_country_name(value):
                name_candidates.append(clean_text(value))

    if not name_candidates:
        return None

    # Prefer Khmer as website display name when present.
    khmer_names = [
        name
        for name in name_candidates
        if re.search(r"[\u1780-\u17ff]", name)
    ]

    english_names = [
        name
        for name in name_candidates
        if re.fullmatch(
            r"[A-Za-z][A-Za-z .,'()&\-]+",
            name,
        )
    ]

    website_name = (
        khmer_names[0]
        if khmer_names
        else name_candidates[0]
    )

    english_name = (
        english_names[0]
        if english_names
        else translate_country(website_name)
    )

    value = ""

    for key, candidate in normalized.items():
        if (
            key in VALUE_KEYS
            or key.replace("_", "") in {
                "countrycode",
                "isocode",
            }
        ):
            if candidate is not None:
                value = clean_text(candidate)
                break

    return Country(
        website_name=website_name,
        english_name=english_name,
        value=value,
    )


def recursively_find_country_objects(
    value: Any,
    results: list[Country],
) -> None:
    if isinstance(value, dict):
        country = object_to_country(value)

        if country is not None:
            results.append(country)

        for child in value.values():
            recursively_find_country_objects(
                child,
                results,
            )

    elif isinstance(value, list):
        for child in value:
            recursively_find_country_objects(
                child,
                results,
            )


def extract_countries_from_text(
    text: str,
) -> list[Country]:
    results: list[Country] = []

    if not text:
        return results

    # First try JSON.
    try:
        data = json.loads(text)

        recursively_find_country_objects(
            data,
            results,
        )

        if results:
            return deduplicate_countries(results)
    except Exception:
        pass

    # Look for arrays embedded inside JavaScript.
    candidate_patterns = [
        r"\[[^\]]{20,500000}\]",
        r"\{[^{}]{20,500000}\}",
    ]

    for pattern in candidate_patterns:
        try:
            matches = re.findall(
                pattern,
                text,
                flags=re.DOTALL,
            )
        except Exception:
            matches = []

        for candidate in matches[:100]:
            try:
                parsed = json.loads(candidate)

                recursively_find_country_objects(
                    parsed,
                    results,
                )
            except Exception:
                continue

    return deduplicate_countries(results)


def deduplicate_countries(
    countries: list[Country],
) -> list[Country]:
    result: list[Country] = []
    seen: set[str] = set()

    for country in countries:
        key = normalize_country_key(
            country.website_name
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(country)

    return result


# ============================================================
# EXTRACT COUNTRIES FROM LIVE DOM
# ============================================================

def countries_from_select(
    page: Page,
) -> list[Country]:
    result: list[Country] = []

    selects = page.locator("select")

    count = selects.count()

    for index in range(count):
        select = selects.nth(index)

        try:
            if not select.is_visible():
                continue
        except Exception:
            continue

        options = select.locator("option")

        option_count = options.count()

        print(
            f"Visible select #{index}: "
            f"{option_count} option(s)"
        )

        for option_index in range(option_count):
            option = options.nth(option_index)

            try:
                text = clean_text(
                    option.inner_text()
                )

                value = clean_text(
                    option.get_attribute("value")
                    or ""
                )

                disabled = (
                    option.get_attribute("disabled")
                    is not None
                )

                if disabled:
                    continue

                if is_placeholder(text):
                    continue

                if not text:
                    continue

                result.append(
                    Country(
                        website_name=text,
                        english_name=translate_country(text),
                        value=value,
                    )
                )
            except Exception:
                continue

    return deduplicate_countries(result)


def dump_select_information(page: Page) -> None:
    print("Inspecting Country select...")

    try:
        selects = page.locator("select")
        count = selects.count()

        print(f"Total select elements: {count}")

        for index in range(count):
            select = selects.nth(index)

            try:
                print(
                    f"  SELECT #{index}: "
                    f"name={select.get_attribute('name')!r}, "
                    f"id={select.get_attribute('id')!r}, "
                    f"class={select.get_attribute('class')!r}"
                )

                options = select.locator("option")

                for option_index in range(
                    min(options.count(), 20)
                ):
                    option = options.nth(option_index)

                    print(
                        "    OPTION:",
                        repr(
                            clean_text(
                                option.inner_text()
                            )
                        ),
                        "value=",
                        repr(
                            option.get_attribute(
                                "value"
                            )
                        ),
                    )
            except Exception:
                pass

    except Exception as exc:
        print(
            "Could not inspect selects:",
            exc,
        )


# ============================================================
# PERFORMANCE RESOURCE INSPECTION
# ============================================================

def get_performance_resources(
    page: Page,
) -> list[str]:
    try:
        resources = page.evaluate(
            """
            () => performance
                .getEntriesByType('resource')
                .map(x => x.name)
            """
        )

        return [
            clean_text(url)
            for url in resources
            if clean_text(url)
        ]

    except Exception:
        return []


def print_interesting_resources(
    page: Page,
) -> None:
    resources = get_performance_resources(page)

    interesting = []

    keywords = [
        "api",
        "country",
        "countries",
        "destination",
        "calculate",
        "international",
        "price",
        "service",
    ]

    for url in resources:
        lowered = url.lower()

        if any(
            keyword in lowered
            for keyword in keywords
        ):
            interesting.append(url)

    print(
        f"Interesting browser resources: "
        f"{len(interesting)}"
    )

    for url in interesting[:100]:
        print(
            "  ",
            url,
        )


# ============================================================
# SCRIPT SOURCE INSPECTION
# ============================================================

def inspect_script_sources(
    page: Page,
) -> list[str]:
    urls: list[str] = []

    try:
        scripts = page.locator(
            "script[src]"
        )

        count = scripts.count()

        print(
            f"Page has {count} external script(s)."
        )

        for index in range(count):
            script = scripts.nth(index)

            try:
                src = clean_text(
                    script.get_attribute("src")
                    or ""
                )

                if src:
                    urls.append(src)
            except Exception:
                continue

    except Exception:
        pass

    return urls


def search_loaded_scripts_for_api_hints(
    page: Page,
) -> list[str]:
    hints: list[str] = []

    scripts = inspect_script_sources(page)

    interesting_words = [
        "country",
        "countries",
        "destination",
        "calculate",
        "international",
        "/api/",
        "axios",
        "fetch(",
    ]

    for script_url in scripts:
        lowered = script_url.lower()

        if any(
            word in lowered
            for word in interesting_words
        ):
            hints.append(
                f"SCRIPT URL: {script_url}"
            )

    # Inspect inline scripts as well.
    try:
        inline_scripts = page.locator(
            "script:not([src])"
        )

        count = inline_scripts.count()

        for index in range(count):
            script = inline_scripts.nth(index)

            try:
                text = script.inner_text()

                if not text:
                    continue

                lowered = text.lower()

                if any(
                    word in lowered
                    for word in interesting_words
                ):
                    # Extract URL-like strings.
                    found_urls = re.findall(
                        r"""["']([^"']*(?:api|country|countries|calculate|international|destination)[^"']*)["']""",
                        text,
                        flags=re.IGNORECASE,
                    )

                    for found in found_urls:
                        hints.append(
                            f"INLINE SCRIPT HINT: {found}"
                        )
            except Exception:
                continue

    except Exception:
        pass

    return hints


# ============================================================
# COUNTRY DISCOVERY FROM NETWORK
# ============================================================

def countries_from_network(
    network: NetworkCapture,
) -> list[Country]:
    all_countries: list[Country] = []

    for response in network.responses:
        body = response.get("body", "")

        if not body:
            continue

        url = response.get("url", "")

        print(
            "Inspecting network response:",
            response.get("status"),
            url,
        )

        countries = extract_countries_from_text(
            body
        )

        if countries:
            print(
                f"  Found {len(countries)} "
                f"possible country record(s)"
            )

            all_countries.extend(
                countries
            )

    return deduplicate_countries(
        all_countries
    )


# ============================================================
# WAIT FOR DYNAMIC COUNTRY DATA
# ============================================================

def wait_for_dynamic_countries(
    page: Page,
    network: NetworkCapture,
) -> list[Country]:

    print(
        "Waiting for Cambodia Post's "
        "dynamic country data..."
    )

    deadline = (
        time.monotonic()
        + COUNTRY_DISCOVERY_TIMEOUT / 1000
    )

    last_count = -1

    while time.monotonic() < deadline:
        # Check real DOM first.
        dom_countries = countries_from_select(
            page
        )

        if dom_countries:
            print(
                f"Country options appeared in DOM: "
                f"{len(dom_countries)}"
            )

            return dom_countries

        # Check captured network responses.
        network_countries = countries_from_network(
            network
        )

        if network_countries:
            print(
                f"Countries found in network data: "
                f"{len(network_countries)}"
            )

            return network_countries

        current_count = len(network.responses)

        if current_count != last_count:
            print(
                f"Captured network responses: "
                f"{current_count}"
            )

            last_count = current_count

        # Try opening the country select.
        try:
            selects = page.locator("select")

            for index in range(selects.count()):
                select = selects.nth(index)

                try:
                    if select.is_visible():
                        select.click(
                            timeout=2_000
                        )

                        time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass

        time.sleep(1)

    return deduplicate_countries(
        countries_from_select(page)
        + countries_from_network(network)
    )


# ============================================================
# OPTIONAL DOM INJECTION
# ============================================================

def inject_discovered_country_options(
    page: Page,
    countries: list[Country],
) -> None:
    """
    If Cambodia Post's JavaScript API gives us the country list
    but the page fails to insert the options into the select,
    add the discovered options to the existing select.

    This is deliberately only a fallback.

    The site's own Calculate button/event handlers are still used.
    """

    if not countries:
        return

    print(
        "Injecting discovered country options "
        "into the existing select as a fallback..."
    )

    payload = [
        {
            "name": country.website_name,
            "english": country.english_name,
            "value": country.value,
        }
        for country in countries
    ]

    result = page.evaluate(
        """
        (countries) => {
            const selects = [
                ...document.querySelectorAll("select")
            ];

            if (!selects.length) {
                return {
                    ok: false,
                    reason: "no-select"
                };
            }

            let target = null;

            for (const select of selects) {
                const text =
                    (select.parentElement?.innerText || "")
                    .toLowerCase();

                const aria =
                    (
                        select.getAttribute("aria-label")
                        || ""
                    ).toLowerCase();

                const name =
                    (
                        select.getAttribute("name")
                        || ""
                    ).toLowerCase();

                const id =
                    (
                        select.getAttribute("id")
                        || ""
                    ).toLowerCase();

                if (
                    text.includes("country")
                    || text.includes("ប្រទេស")
                    || aria.includes("country")
                    || aria.includes("ប្រទេស")
                    || name.includes("country")
                    || id.includes("country")
                ) {
                    target = select;
                    break;
                }
            }

            if (!target) {
                target = selects[0];
            }

            const existing = [
                ...target.options
            ].map(option => option.value);

            let added = 0;

            for (const country of countries) {
                const value =
                    country.value
                    || country.name;

                if (
                    !value
                    || existing.includes(value)
                ) {
                    continue;
                }

                const option =
                    document.createElement("option");

                option.value = value;
                option.textContent = country.name;

                target.appendChild(option);

                added += 1;
            }

            target.dispatchEvent(
                new Event("input", {
                    bubbles: true
                })
            );

            target.dispatchEvent(
                new Event("change", {
                    bubbles: true
                })
            );

            return {
                ok: true,
                added,
                total: target.options.length
            };
        }
        """,
        payload,
    )

    print(
        "Country option injection result:",
        result,
    )


# ============================================================
# FIND COUNTRY SELECT
# ============================================================

def find_country_select(
    page: Page,
):
    selects = page.locator("select")

    count = selects.count()

    if count == 0:
        return None

    # Prefer a select whose surrounding text says Country.
    for index in range(count):
        select = selects.nth(index)

        try:
            if not select.is_visible():
                continue

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

    # Otherwise use first visible select.
    for index in range(count):
        select = selects.nth(index)

        try:
            if select.is_visible():
                return select
        except Exception:
            continue

    return None


# ============================================================
# DISCOVER COUNTRIES
# ============================================================

def discover_countries(
    page: Page,
    network: NetworkCapture,
) -> list[Country]:

    print(
        "============================================================"
    )
    print("COUNTRY DISCOVERY")
    print(
        "============================================================"
    )

    # Let initial JavaScript run.
    time.sleep(3)

    dump_select_information(page)

    countries = countries_from_select(page)

    if countries:
        print(
            f"Countries discovered directly from select: "
            f"{len(countries)}"
        )

        return countries

    print(
        "No actual country options in the select."
    )

    print(
        "Checking dynamic network/API data..."
    )

    countries = wait_for_dynamic_countries(
        page,
        network,
    )

    if countries:
        print(
            f"Countries discovered dynamically: "
            f"{len(countries)}"
        )

        # If the actual select still only has the placeholder,
        # add the dynamically discovered options.
        current_dom = countries_from_select(page)

        if not current_dom:
            inject_discovered_country_options(
                page,
                countries,
            )

            time.sleep(1)

            after_injection = countries_from_select(
                page
            )

            if after_injection:
                print(
                    "Country select now contains "
                    f"{len(after_injection)} option(s)."
                )

                return after_injection

        return countries

    print(
        "No countries found in the DOM or captured API data."
    )

    print_interesting_resources(page)

    hints = search_loaded_scripts_for_api_hints(
        page
    )

    if hints:
        print(
            "Possible API/script hints:"
        )

        for hint in hints[:100]:
            print(
                "  ",
                hint,
            )

    dump_select_information(page)

    save_debug(
        page,
        network,
    )

    raise RuntimeError(
        "Cambodia Post's Country select contains only "
        "the placeholder, and no country list could be "
        "found in the page or dynamic network data. "
        "Debug files were saved."
    )


# ============================================================
# COUNTRY SELECTION
# ============================================================

def select_country(
    page: Page,
    country: Country,
) -> None:

    select = find_country_select(page)

    if select is None:
        raise RuntimeError(
            "Country select could not be found."
        )

    # First try exact value.
    if country.value:
        try:
            select.select_option(
                value=country.value,
                timeout=5_000,
            )

            return
        except Exception:
            pass

    # Then exact label.
    try:
        select.select_option(
            label=country.website_name,
            timeout=5_000,
        )

        return
    except Exception:
        pass

    # Finally inspect all options and use normalized text.
    options = select.locator("option")

    target_key = normalize_country_key(
        country.website_name
    )

    for index in range(options.count()):
        option = options.nth(index)

        try:
            text = clean_text(
                option.inner_text()
            )

            if (
                normalize_country_key(text)
                == target_key
            ):
                value = (
                    option.get_attribute("value")
                    or text
                )

                select.select_option(
                    value=value,
                    timeout=5_000,
                )

                return

        except Exception:
            continue

    raise RuntimeError(
        f"Could not select country: "
        f"{country.website_name}"
    )


# ============================================================
# WEIGHT INPUT
# ============================================================

def find_weight_input(page: Page):
    selectors = [
        'input[placeholder*="បញ្ចូលទម្ងន់"]',
        'input[placeholder*="weight" i]',
        'input[name*="weight" i]',
        'input[id*="weight" i]',
        'input[type="number"]',
        'input[type="text"]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

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
    weight: str,
) -> None:

    weight_input = find_weight_input(page)

    if weight_input is None:
        raise RuntimeError(
            "Weight input could not be found."
        )

    weight_input.fill(weight)

    # Trigger input/change events.
    try:
        weight_input.press("Tab")
    except Exception:
        pass


# ============================================================
# CALCULATE BUTTON
# ============================================================

def find_calculate_button(page: Page):
    selectors = [
        "button",
        'input[type="button"]',
        'input[type="submit"]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()

            for index in range(count):
                button = locator.nth(index)

                if not button.is_visible():
                    continue

                text = clean_text(
                    button.inner_text()
                ).lower()

                value = clean_text(
                    button.get_attribute("value")
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
# RESULT DETECTION
# ============================================================

def page_text(page: Page) -> str:
    try:
        return clean_text(
            page.locator("body").inner_text()
        )
    except Exception:
        return ""


def contains_error_message(
    text: str,
) -> bool:

    lowered = text.lower()

    error_patterns = [
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
        "មិនអាចផ្ញើ",
        "ផ្អាក",
        "មិនទាន់មាន",
    ]

    for pattern in error_patterns:
        if pattern.lower() in lowered:
            return True

    return False


def find_letter_section(
    page: Page,
) -> str:

    text = page_text(page)

    lines = [
        clean_text(line)
        for line in text.splitlines()
        if clean_text(line)
    ]

    relevant: list[str] = []

    for index, line in enumerate(lines):
        if re.search(
            r"\bLetter\b",
            line,
            flags=re.IGNORECASE,
        ):
            start = max(0, index - 2)
            end = min(
                len(lines),
                index + 6,
            )

            relevant.extend(
                lines[start:end]
            )

    return "\n".join(
        dict.fromkeys(relevant)
    )


def letter_has_price(
    section: str,
) -> bool:

    if not section:
        return False

    lowered = section.lower()

    price_words = [
        "price",
        "khr",
        "៛",
        "រៀល",
    ]

    has_price_label = any(
        word in lowered
        for word in price_words
    )

    if not has_price_label:
        return False

    # Detect an amount such as:
    # 2,600
    # 2600
    # 2 600
    # 2.600
    has_number = bool(
        re.search(
            r"\b\d{1,3}(?:[,\s.]\d{3})+\b|\b\d{3,}\b",
            section,
        )
    )

    return has_number


def analyze_result(
    page: Page,
) -> tuple[bool, str]:

    # Give the page a moment to render the result.
    deadline = (
        time.monotonic()
        + RESULT_TIMEOUT / 1000
    )

    last_text = ""

    while time.monotonic() < deadline:
        text = page_text(page)

        if text:
            last_text = text

            section = find_letter_section(
                page
            )

            if contains_error_message(text):
                return (
                    True,
                    "Error message detected",
                )

            if not re.search(
                r"\bLetter\b",
                text,
                flags=re.IGNORECASE,
            ):
                # Keep waiting because result may
                # still be rendering.
                time.sleep(0.5)
                continue

            if not letter_has_price(section):
                return (
                    True,
                    "Letter service is displayed "
                    "but Price (KHR) is missing",
                )

            return (
                False,
                "Letter service with Price (KHR) detected",
            )

        time.sleep(0.5)

    # Final check.
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
        "Price (KHR) was not displayed for Letter",
    )


# ============================================================
# TEST ONE COUNTRY
# ============================================================

def test_country(
    page: Page,
    country: Country,
) -> tuple[bool, str]:

    print(
        f"Testing: {country.display_name}"
    )

    # --------------------------------------------------------
    # REQUIRED ORDER:
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
        WEIGHT,
    )

    calculate_button = find_calculate_button(
        page
    )

    if calculate_button is None:
        raise RuntimeError(
            "Calculate button could not be found."
        )

    calculate_button.click()

    suspended, reason = analyze_result(
        page
    )

    if suspended:
        print(
            f"  -> SUSPENDED: {reason}"
        )
    else:
        print(
            f"  -> ACTIVE: {reason}"
        )

    return suspended, reason


# ============================================================
# TEST ALL COUNTRIES
# ============================================================

def test_all_countries(
    page: Page,
    countries: list[Country],
) -> list[Country]:

    suspended: list[Country] = []

    total = len(countries)

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
            f"[{index}/{total}] "
            f"{country.display_name}"
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
                f"  -> TECHNICAL ERROR: {exc}"
            )

            # Reload before continuing.
            # A technical Playwright/page error is NOT
            # automatically treated as a suspended destination.
            try:
                page.reload(
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                time.sleep(2)

            except Exception:
                pass

            # Re-inject country options if necessary.
            try:
                select = find_country_select(
                    page
                )

                if select is not None:
                    options = select.locator(
                        "option"
                    )

                    if options.count() <= 1:
                        print(
                            "  Country options disappeared "
                            "after reload."
                        )

            except Exception:
                pass

    return suspended


# ============================================================
# OUTPUT
# ============================================================

def write_output(
    countries: list[Country],
    suspended: list[Country],
) -> None:

    checked = datetime.now(
        timezone.utc
    ).astimezone()

    lines: list[str] = []

    lines.append(
        "Cambodia Post International Shipping Monitor"
    )

    lines.append(
        f"Checked: {checked.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )

    lines.append(
        f"Website: {URL}"
    )

    lines.append(
        f"Weight tested: {WEIGHT} kg"
    )

    lines.append("")

    lines.append(
        "LIST 1 - ALL COUNTRIES"
    )

    lines.append(
        f"Total countries: {len(countries)}"
    )

    lines.append("")

    for country in countries:
        lines.append(
            country.display_name
        )

    lines.append("")

    lines.append(
        "LIST 2 - SUSPENDED DESTINATIONS"
    )

    lines.append(
        f"Total suspended destinations: {len(suspended)}"
    )

    lines.append("")

    for country in suspended:
        lines.append(
            country.display_name
        )

    OUTPUT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "============================================================"
    )
    print(
        "OUTPUT WRITTEN"
    )
    print(
        "============================================================"
    )

    print(
        f"All countries: {len(countries)}"
    )

    print(
        f"Suspended destinations: "
        f"{len(suspended)}"
    )

    print(
        f"Output file: {OUTPUT_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    network = NetworkCapture()

    with sync_playwright() as playwright:

        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
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

        # ----------------------------------------------------
        # Capture network before opening the page.
        # ----------------------------------------------------

        page.on(
            "request",
            network.on_request,
        )

        page.on(
            "response",
            network.on_response,
        )

        attach_console_diagnostics(
            page
        )

        try:

            print(
                "Opening Cambodia Post international calculator..."
            )

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            # Give application JavaScript time to initialize.
            time.sleep(5)

            print(
                f"Page loaded: {page.url}"
            )

            # ------------------------------------------------
            # Show useful network information.
            # ------------------------------------------------

            print_interesting_resources(
                page
            )

            # ------------------------------------------------
            # Discover all countries.
            # ------------------------------------------------

            countries = discover_countries(
                page,
                network,
            )

            countries = deduplicate_countries(
                countries
            )

            if not countries:
                raise RuntimeError(
                    "Country discovery returned zero countries."
                )

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
                    f"{country.display_name}"
                    f" [value={country.value!r}]"
                )

            # Save discovered data for diagnostics.
            try:
                DEBUG_DATA.write_text(
                    json.dumps(
                        [
                            {
                                "website_name": c.website_name,
                                "english_name": c.english_name,
                                "value": c.value,
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

            # ------------------------------------------------
            # IMPORTANT:
            # Reload the page before actual testing.
            #
            # This ensures each test starts from a fresh
            # calculator state.
            # ------------------------------------------------

            print()
            print(
                "Reloading calculator before country tests..."
            )

            page.reload(
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            time.sleep(4)

            # Check whether options are still present.
            current_options = countries_from_select(
                page
            )

            if not current_options:
                # The page may again have failed to populate
                # the select. Use the discovered country data.
                print(
                    "Country options are absent after reload."
                )

                inject_discovered_country_options(
                    page,
                    countries,
                )

                time.sleep(1)

            # ------------------------------------------------
            # Test every country.
            # ------------------------------------------------

            suspended = test_all_countries(
                page,
                countries,
            )

            # ------------------------------------------------
            # Write output.
            # ------------------------------------------------

            write_output(
                countries,
                suspended,
            )

            network.save()

            print()
            print(
                "Monitor completed successfully."
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
                page,
                network,
            )

            print()
            print(
                "Debug files created:"
            )

            print(
                f"  {DEBUG_HTML}"
            )

            print(
                f"  {DEBUG_PNG}"
            )

            print(
                f"  {DEBUG_NETWORK}"
            )

            if DEBUG_DATA.exists():
                print(
                    f"  {DEBUG_DATA}"
                )

            raise

        finally:

            try:
                network.save()
            except Exception:
                pass

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
