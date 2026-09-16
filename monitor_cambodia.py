import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from babel import Locale
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

URL = "https://www.cambodiapost.com.kh/calculate/international"

OUTPUT_FILE = Path("output_cambodia.txt")

WEIGHT = "0.02"

PAGE_TIMEOUT = 60_000
RESULT_TIMEOUT = 30_000

COUNTRY_SEARCH_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

DEBUG_HTML = Path("debug_cambodiapost.html")
DEBUG_PNG = Path("debug_cambodiapost.png")


# ============================================================================
# COUNTRY NAME TRANSLATION
# ============================================================================

EN_LOCALE = Locale("en")
KM_LOCALE = Locale("km")

EN_TERRITORIES = dict(EN_LOCALE.territories)
KM_TERRITORIES = dict(KM_LOCALE.territories)


def normalize_name(value: str) -> str:
    """
    Clean whitespace and invisible characters.
    """
    if not value:
        return ""

    value = value.replace("\u200b", "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_for_lookup(value: str) -> str:
    """
    Normalize a country name for comparison.
    """
    value = normalize_name(value)

    value = re.sub(
        r"\s*[\(\[\{]\s*[A-Za-z]{2,3}\s*[\)\]\}]\s*$",
        "",
        value,
    )

    return value.casefold().strip()


def build_country_name_maps():
    """
    Build Khmer -> English and English -> English country mappings
    using Babel's localized territory data.
    """
    khmer_to_english = {}
    english_to_english = {}

    for code, english_name in EN_TERRITORIES.items():
        if not code or not english_name:
            continue

        english_name = normalize_name(english_name)

        khmer_name = KM_TERRITORIES.get(code)

        if khmer_name:
            khmer_to_english[
                normalize_for_lookup(khmer_name)
            ] = english_name

        english_to_english[
            normalize_for_lookup(english_name)
        ] = english_name

    return khmer_to_english, english_to_english


KHMER_TO_ENGLISH, ENGLISH_TO_ENGLISH = build_country_name_maps()


def english_from_code(code: str) -> str:
    """
    Convert an ISO alpha-2 country code into its English name.
    """
    if not code:
        return ""

    return normalize_name(
        EN_TERRITORIES.get(code.upper(), "")
    )


def find_iso_code_in_value(value: str) -> str:
    """
    Try to find an ISO alpha-2 country code in an option value.

    Examples:
        US
        KH
        country-US
        country_US
        /country/US
    """
    if not value:
        return ""

    value = normalize_name(value)

    # Direct two-letter ISO code.
    if re.fullmatch(r"[A-Za-z]{2}", value):
        code = value.upper()

        if code in EN_TERRITORIES:
            return code

    # Look for a two-letter code inside the value.
    matches = re.findall(
        r"(?<![A-Za-z])([A-Za-z]{2})(?![A-Za-z])",
        value,
    )

    for match in matches:
        code = match.upper()

        if code in EN_TERRITORIES:
            return code

    return ""


def english_country_name(
    cambodian_name: str,
    value: str = "",
) -> str:
    """
    Determine the English country name.

    Priority:
      1. ISO country code from option value.
      2. Khmer country name.
      3. Existing English country name.
      4. Latin/English fallback.
    """
    original = normalize_name(cambodian_name)

    # ------------------------------------------------------------
    # Try the option value.
    # ------------------------------------------------------------
    code = find_iso_code_in_value(value)

    if code:
        english = english_from_code(code)

        if english:
            return english

    # ------------------------------------------------------------
    # Try exact Khmer name.
    # ------------------------------------------------------------
    lookup = normalize_for_lookup(original)

    if lookup in KHMER_TO_ENGLISH:
        return KHMER_TO_ENGLISH[lookup]

    # ------------------------------------------------------------
    # Already English.
    # ------------------------------------------------------------
    if lookup in ENGLISH_TO_ENGLISH:
        return ENGLISH_TO_ENGLISH[lookup]

    # ------------------------------------------------------------
    # If the website already supplied Latin characters,
    # preserve them as the English name.
    # ------------------------------------------------------------
    if re.search(r"[A-Za-z]", original):
        return original

    # ------------------------------------------------------------
    # If no translation was found, clearly indicate that rather
    # than incorrectly treating the Khmer name as English.
    # ------------------------------------------------------------
    return "[English translation not found]"


# ============================================================================
# COUNTRY DATA
# ============================================================================

@dataclass
class Country:
    """
    Stores the exact country name shown by Cambodia Post,
    its English translation, and the option value if available.
    """

    website_name: str
    english_name: str
    value: str = ""

    @property
    def output_name(self) -> str:
        return f"{self.website_name} — {self.english_name}"


# ============================================================================
# PLACEHOLDER DETECTION
# ============================================================================

def is_country_placeholder(text: str) -> bool:
    """
    Return True if text is a country-field placeholder rather than
    an actual country.

    Important:
        ជ្រើសរើសប្រទេស = Select a country
    """
    if not text:
        return True

    normalized = normalize_for_lookup(text)

    placeholder_values = {
        "country",
        "select",
        "select country",
        "choose country",
        "please select",
        "please select country",
        "ជ្រើសរើសប្រទេស",
        "ជ្រើសរើស",
        "ប្រទេស",
    }

    if normalized in {
        normalize_for_lookup(value)
        for value in placeholder_values
    }:
        return True

    # Additional Khmer placeholder checks.
    if "ជ្រើសរើសប្រទេស" in text:
        return True

    if "ជ្រើសរើស" in text and "ប្រទេស" in text:
        return True

    if "select country" in normalized:
        return True

    if "choose country" in normalized:
        return True

    return False


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def clean_text(value: str) -> str:
    if not value:
        return ""

    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def visible(locator) -> bool:
    try:
        return locator.is_visible()
    except Exception:
        return False


def get_body_text(page) -> str:
    try:
        return clean_text(
            page.locator("body").inner_text()
        )
    except Exception:
        return ""


def save_diagnostics(page):
    """
    Save HTML and screenshot for GitHub Actions debugging.
    """
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


# ============================================================================
# FIND COUNTRY FIELD
# ============================================================================

def find_country_select(page):
    """
    Find a native HTML <select> country field.
    """
    selects = page.locator("select:visible")

    try:
        count = selects.count()
    except Exception:
        count = 0

    candidates = []

    for i in range(count):
        select = selects.nth(i)

        try:
            attrs = select.evaluate(
                """
                el => ({
                    id: el.id || "",
                    name: el.name || "",
                    aria: el.getAttribute("aria-label") || "",
                    title: el.getAttribute("title") || "",
                    placeholder: el.getAttribute("placeholder") || "",
                    text: el.parentElement
                        ? el.parentElement.innerText
                        : ""
                })
                """
            )
        except Exception:
            attrs = {}

        combined = " ".join(
            str(attrs.get(key, ""))
            for key in [
                "id",
                "name",
                "aria",
                "title",
                "placeholder",
                "text",
            ]
        ).casefold()

        if (
            "country" in combined
            or "ប្រទេស" in combined
        ):
            candidates.append(select)

    if candidates:
        return candidates[0]

    # If there is only one visible select, use it.
    if count == 1:
        return selects.nth(0)

    return None


def find_country_combobox(page):
    """
    Find a custom autocomplete/combobox country field.
    """
    selectors = [
        '[role="combobox"]:visible',
        'input[placeholder*="country" i]:visible',
        'input[aria-label*="country" i]:visible',
        'input[name*="country" i]:visible',
        'input[id*="country" i]:visible',
        'input[formcontrolname*="country" i]:visible',

        'input[placeholder*="ប្រទេស" i]:visible',
        'input[aria-label*="ប្រទេស" i]:visible',
        'input[name*="ប្រទេស" i]:visible',
        'input[id*="ប្រទេស" i]:visible',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):
            candidate = locator.nth(i)

            if visible(candidate):
                return candidate

    # Broader fallback.
    inputs = page.locator("input:visible")

    try:
        count = inputs.count()
    except Exception:
        count = 0

    for i in range(count):
        candidate = inputs.nth(i)

        try:
            attrs = candidate.evaluate(
                """
                el => ({
                    id: el.id || "",
                    name: el.name || "",
                    placeholder:
                        el.getAttribute("placeholder") || "",
                    aria:
                        el.getAttribute("aria-label") || "",
                    parentText:
                        el.parentElement
                            ? el.parentElement.innerText
                            : ""
                })
                """
            )
        except Exception:
            attrs = {}

        combined = " ".join(
            str(attrs.get(key, ""))
            for key in [
                "id",
                "name",
                "placeholder",
                "aria",
                "parentText",
            ]
        ).casefold()

        if (
            "country" in combined
            or "ប្រទេស" in combined
        ):
            return candidate

    return None


def find_country_control(page):
    """
    Return:
        ("select", locator)
    or:
        ("combobox", locator)
    """
    select = find_country_select(page)

    if select is not None:
        return "select", select

    combobox = find_country_combobox(page)

    if combobox is not None:
        return "combobox", combobox

    save_diagnostics(page)

    raise RuntimeError(
        "Could not find the Country input field."
    )


# ============================================================================
# NATIVE SELECT COUNTRY DISCOVERY
# ============================================================================

def countries_from_native_select(select):
    """
    Read all real country options from a native <select>.

    The placeholder ជ្រើសរើសប្រទេស is explicitly excluded.
    """
    countries = []

    options = select.locator("option")

    try:
        count = options.count()
    except Exception:
        count = 0

    seen = set()

    for i in range(count):
        option = options.nth(i)

        try:
            text = clean_text(option.inner_text())
        except Exception:
            text = ""

        try:
            value = clean_text(
                option.get_attribute("value") or ""
            )
        except Exception:
            value = ""

        # ------------------------------------------------------------
        # IMPORTANT:
        # Ignore the "Select a country" placeholder.
        # ------------------------------------------------------------
        if is_country_placeholder(text):
            continue

        if not text:
            continue

        # Ignore disabled placeholders.
        try:
            if option.is_disabled():
                continue
        except Exception:
            pass

        key = normalize_for_lookup(text)

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)

        english_name = english_country_name(
            text,
            value,
        )

        countries.append(
            Country(
                website_name=text,
                english_name=english_name,
                value=value,
            )
        )

    return countries


# ============================================================================
# CUSTOM DROPDOWN OPTION DISCOVERY
# ============================================================================

def get_visible_options(page):
    """
    Find visible options from common autocomplete/dropdown implementations.
    """
    selectors = [
        '[role="option"]:visible',
        'li[role="option"]:visible',
        'mat-option:visible',
        '.dropdown-item:visible',
        '.select-option:visible',
        '.option:visible',
    ]

    results = []

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):
            item = locator.nth(i)

            if not visible(item):
                continue

            try:
                text = clean_text(
                    item.inner_text()
                )
            except Exception:
                text = ""

            # --------------------------------------------------------
            # IMPORTANT:
            # Never return "Select a country" as an option.
            # --------------------------------------------------------
            if is_country_placeholder(text):
                continue

            if text:
                results.append(text)

    # Deduplicate while preserving order.
    unique = []
    seen = set()

    for text in results:
        key = normalize_for_lookup(text)

        if not key:
            continue

        if is_country_placeholder(text):
            continue

        if key in seen:
            continue

        seen.add(key)
        unique.append(text)

    return unique


def discover_countries_from_combobox(
    page,
    combobox,
):
    """
    Discover all countries from a custom country autocomplete.

    Cambodia Post may show an empty dropdown until a letter is typed.
    Therefore we search A-Z.
    """
    discovered = {}

    for letter in COUNTRY_SEARCH_LETTERS:
        try:
            combobox.click()

            # Clear previous search.
            try:
                combobox.fill("")
            except Exception:
                combobox.press("Control+A")
                combobox.press("Backspace")

            combobox.fill(letter)

            page.wait_for_timeout(500)

            options = get_visible_options(page)

            for option_text in options:
                if is_country_placeholder(option_text):
                    continue

                key = normalize_for_lookup(option_text)

                if not key:
                    continue

                if key not in discovered:
                    discovered[key] = Country(
                        website_name=option_text,
                        english_name=english_country_name(
                            option_text
                        ),
                        value="",
                    )

        except Exception as exc:
            print(
                f"Country search '{letter}' failed: {exc}"
            )
            continue

    # ------------------------------------------------------------
    # Final search with no text.
    # ------------------------------------------------------------
    try:
        combobox.click()
        combobox.fill("")

        page.wait_for_timeout(500)

        options = get_visible_options(page)

        for option_text in options:
            if is_country_placeholder(option_text):
                continue

            key = normalize_for_lookup(option_text)

            if key and key not in discovered:
                discovered[key] = Country(
                    website_name=option_text,
                    english_name=english_country_name(
                        option_text
                    ),
                    value="",
                )

    except Exception:
        pass

    return list(discovered.values())


# ============================================================================
# COUNTRY DISCOVERY
# ============================================================================

def discover_countries(page):
    """
    Detect the country control and discover all countries.
    """
    control_type, control = find_country_control(page)

    print(
        f"Country control detected: {control_type}"
    )

    if control_type == "select":
        countries = countries_from_native_select(
            control
        )
    else:
        countries = discover_countries_from_combobox(
            page,
            control,
        )

    # ------------------------------------------------------------
    # Final safety filter.
    # ------------------------------------------------------------
    countries = [
        country
        for country in countries
        if not is_country_placeholder(
            country.website_name
        )
    ]

    if not countries:
        save_diagnostics(page)

        raise RuntimeError(
            "Country field was found, but no actual country "
            "options were discovered. The placeholder "
            "ជ្រើសរើសប្រទេស was not counted as a country."
        )

    # Sort by English name.
    countries.sort(
        key=lambda country: (
            normalize_for_lookup(
                country.english_name
            ),
            normalize_for_lookup(
                country.website_name
            ),
        )
    )

    return countries


# ============================================================================
# COUNTRY SELECTION
# ============================================================================

def select_country(
    page,
    country: Country,
):
    """
    Select one actual country.

    IMPORTANT:
    The placeholder "ជ្រើសរើសប្រទេស" is never selected.
    """
    control_type, control = find_country_control(page)

    if control_type == "select":

        # --------------------------------------------------------
        # First try option value.
        # --------------------------------------------------------
        if country.value:
            try:
                control.select_option(
                    value=country.value
                )

                page.wait_for_timeout(300)

                return
            except Exception:
                pass

        # --------------------------------------------------------
        # Then try exact visible label.
        # --------------------------------------------------------
        try:
            control.select_option(
                label=country.website_name
            )

            page.wait_for_timeout(300)

            return
        except Exception:
            pass

        raise RuntimeError(
            f"Could not select country: "
            f"{country.website_name}"
        )

    # ----------------------------------------------------------------
    # CUSTOM COMBOBOX
    # ----------------------------------------------------------------

    control.click()

    try:
        control.fill("")
    except Exception:
        control.press("Control+A")
        control.press("Backspace")

    # Search the exact Cambodian country name.
    try:
        control.fill(
            country.website_name
        )
    except Exception:
        control.type(
            country.website_name
        )

    page.wait_for_timeout(500)

    selectors = [
        '[role="option"]:visible',
        'li[role="option"]:visible',
        'mat-option:visible',
        '.dropdown-item:visible',
        '.select-option:visible',
        '.option:visible',
    ]

    for selector in selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):
            option = locator.nth(i)

            if not visible(option):
                continue

            try:
                text = clean_text(
                    option.inner_text()
                )
            except Exception:
                text = ""

            # Never click the placeholder.
            if is_country_placeholder(text):
                continue

            if (
                normalize_for_lookup(text)
                == normalize_for_lookup(
                    country.website_name
                )
            ):
                option.click()

                page.wait_for_timeout(300)

                return

    # ----------------------------------------------------------------
    # Exact visible text fallback.
    # ----------------------------------------------------------------
    exact_candidates = page.get_by_text(
        country.website_name,
        exact=True,
    )

    try:
        count = exact_candidates.count()
    except Exception:
        count = 0

    for i in range(count):
        candidate = exact_candidates.nth(i)

        if not visible(candidate):
            continue

        try:
            candidate.click()

            page.wait_for_timeout(300)

            return
        except Exception:
            continue

    raise RuntimeError(
        f"Could not select country: "
        f"{country.website_name}"
    )


# ============================================================================
# WEIGHT FIELD
# ============================================================================

def find_weight_input(page):
    """
    Find the Weight(kg) field.
    """
    selectors = [
        'input[placeholder*="weight" i]:visible',
        'input[aria-label*="weight" i]:visible',
        'input[name*="weight" i]:visible',
        'input[id*="weight" i]:visible',
        'input[formcontrolname*="weight" i]:visible',

        'input[placeholder*="ទម្ងន់" i]:visible',
        'input[aria-label*="ទម្ងន់" i]:visible',
        'input[name*="ទម្ងន់" i]:visible',
        'input[id*="ទម្ងន់" i]:visible',

        'input[type="number"]:visible',
    ]

    for selector in selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):
            candidate = locator.nth(i)

            if visible(candidate):
                return candidate

    return None


def set_weight(page):
    """
    Enter exactly 0.02 kg.
    """
    weight_input = find_weight_input(page)

    if weight_input is None:
        save_diagnostics(page)

        raise RuntimeError(
            "Could not find the Weight input field."
        )

    weight_input.click()

    try:
        weight_input.fill(WEIGHT)
    except Exception:
        weight_input.press("Control+A")
        weight_input.press("Backspace")
        weight_input.type(WEIGHT)

    try:
        weight_input.press("Tab")
    except Exception:
        pass

    page.wait_for_timeout(200)


# ============================================================================
# CALCULATE BUTTON
# ============================================================================

def find_calculate_button(page):
    """
    Find the Calculate button.
    """
    selectors = [
        'button:visible',
        'input[type="submit"]:visible',
        'input[type="button"]:visible',
    ]

    for selector in selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):
            candidate = locator.nth(i)

            try:
                tag_name = candidate.evaluate(
                    "el => el.tagName.toLowerCase()"
                )

                if tag_name == "button":
                    text = clean_text(
                        candidate.inner_text()
                    )
                else:
                    text = clean_text(
                        candidate.get_attribute(
                            "value"
                        )
                        or candidate.get_attribute(
                            "aria-label"
                        )
                        or ""
                    )
            except Exception:
                text = ""

            if (
                "calculate" in text.casefold()
                or "គណនា" in text
            ):
                return candidate

    # Accessible-name fallback.
    try:
        button = page.get_by_role(
            "button",
            name=re.compile(
                r"calculate|គណនា",
                re.IGNORECASE,
            ),
        )

        if visible(button):
            return button
    except Exception:
        pass

    return None


def click_calculate(page):
    button = find_calculate_button(page)

    if button is None:
        save_diagnostics(page)

        raise RuntimeError(
            "Could not find the Calculate button."
        )

    button.click()


# ============================================================================
# WAIT FOR CALCULATION
# ============================================================================

def wait_for_calculation(page):
    """
    Wait for calculation/loading to finish.
    """
    loading_selectors = [
        'text=Loading',
        'text=loading',
        '[aria-busy="true"]',
        '.loading',
        '.spinner',
        '.loader',
    ]

    for selector in loading_selectors:

        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                locator.first.wait_for(
                    state="hidden",
                    timeout=RESULT_TIMEOUT,
                )

        except Exception:
            pass

    # Allow result to render.
    page.wait_for_timeout(2_000)


# ============================================================================
# FIND LETTER SERVICE
# ============================================================================

def find_letter_service(page):
    """
    Find the Letter service result.
    """
    selectors = [
        "text=Letter",
        "text=letter",
    ]

    candidates = []

    for selector in selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):

            candidate = locator.nth(i)

            if not visible(candidate):
                continue

            try:
                text = clean_text(
                    candidate.inner_text()
                )
            except Exception:
                continue

            if "letter" not in text.casefold():
                continue

            candidates.append(
                (
                    len(text),
                    candidate,
                    text,
                )
            )

    # Prefer the smallest useful result block.
    candidates.sort(
        key=lambda item: item[0]
    )

    for _, candidate, text in candidates:

        lowered = text.casefold()

        if (
            "price" in lowered
            or "khr" in lowered
            or "៛" in text
            or "រៀល" in text
            or re.search(r"\d", text)
        ):
            return text

    # Fallback to body text.
    body = get_body_text(page)

    if "letter" in body.casefold():
        return body

    return ""


# ============================================================================
# ERROR DETECTION
# ============================================================================

def detect_error(page):
    """
    Detect a displayed calculation/service error.
    """
    error_selectors = [
        '[role="alert"]:visible',
        ".alert-danger:visible",
        ".alert-error:visible",
        ".error:visible",
        ".text-danger:visible",
        ".invalid-feedback:visible",
    ]

    error_patterns = [
        r"\berror\b",
        r"something went wrong",
        r"calculation failed",
        r"\bfailed\b",
        r"\bcannot\b",
        r"\bunable\b",
        r"not available",
        r"service unavailable",
        r"suspended",
        r"no service",

        r"មិនអាច",
        r"មិនមាន",
        r"ផ្អាក",
        r"កំហុស",
    ]

    for selector in error_selectors:

        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        for i in range(count):

            candidate = locator.nth(i)

            if not visible(candidate):
                continue

            try:
                text = clean_text(
                    candidate.inner_text()
                )
            except Exception:
                text = ""

            if text:
                return text

    body = get_body_text(page)

    for pattern in error_patterns:

        if re.search(
            pattern,
            body,
            re.IGNORECASE,
        ):
            return body

    return ""


# ============================================================================
# LETTER PRICE CHECK
# ============================================================================

def letter_has_price(
    letter_text: str,
) -> bool:
    """
    Check whether Letter contains a displayed price.
    """
    if not letter_text:
        return False

    text = clean_text(
        letter_text
    )

    has_price_label = bool(
        re.search(
            r"price\s*(?:\(\s*khr\s*\))?",
            text,
            re.IGNORECASE,
        )
    )

    has_khr = bool(
        re.search(
            r"\bkhr\b|៛|រៀល",
            text,
            re.IGNORECASE,
        )
    )

    has_number = bool(
        re.search(
            r"\d[\d,\.\s]*",
            text,
        )
    )

    return (
        has_price_label
        or has_khr
    ) and has_number


# ============================================================================
# RESULT EVALUATION
# ============================================================================

def evaluate_result(page):
    """
    Determine whether the destination is suspended.

    Suspended if:
      1. Error message appears.
      2. Letter service is missing.
      3. Letter service exists but has no Price (KHR).
    """
    error = detect_error(page)

    if error:
        return (
            True,
            "Error message displayed",
        )

    letter_text = find_letter_service(
        page
    )

    if not letter_text:
        return (
            True,
            "Letter service missing",
        )

    if not letter_has_price(
        letter_text
    ):
        return (
            True,
            "Letter service has no Price (KHR)",
        )

    return (
        False,
        "Letter service has a displayed price",
    )


# ============================================================================
# TEST ONE COUNTRY
# ============================================================================

def test_country(
    page,
    country: Country,
):
    """
    Required order:

        1. Select country
        2. Enter 0.02 kg
        3. Click Calculate
        4. Check result
    """
    print(
        f"Testing: "
        f"{country.website_name} — "
        f"{country.english_name}"
    )

    # ------------------------------------------------------------
    # 1. Select country
    # ------------------------------------------------------------
    select_country(
        page,
        country,
    )

    # ------------------------------------------------------------
    # 2. Enter weight
    # ------------------------------------------------------------
    set_weight(page)

    # ------------------------------------------------------------
    # 3. Click Calculate
    # ------------------------------------------------------------
    click_calculate(page)

    # ------------------------------------------------------------
    # 4. Wait and inspect result
    # ------------------------------------------------------------
    wait_for_calculation(page)

    suspended, reason = evaluate_result(
        page
    )

    if suspended:

        print(
            f"  SUSPENDED: "
            f"{country.website_name} — "
            f"{country.english_name} "
            f"({reason})"
        )

    else:

        print(
            f"  ACTIVE: "
            f"{country.website_name} — "
            f"{country.english_name}"
        )

    return suspended, reason


# ============================================================================
# WRITE OUTPUT FILE
# ============================================================================

def write_output(
    countries,
    suspended,
):
    """
    Write the final monitoring text file.
    """
    checked = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    lines = []

    lines.append(
        "Cambodia Post International Shipping Monitor"
    )

    lines.append(
        f"Checked: {checked}"
    )

    lines.append(
        f"Website: {URL}"
    )

    lines.append(
        f"Weight tested: {WEIGHT} kg"
    )

    lines.append("")

    # ========================================================================
    # LIST 1
    # ========================================================================

    lines.append(
        "LIST 1 - ALL COUNTRIES"
    )

    lines.append(
        f"Total countries: {len(countries)}"
    )

    lines.append("")

    for country in countries:
        lines.append(
            country.output_name
        )

    lines.append("")

    # ========================================================================
    # LIST 2
    # ========================================================================

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
            country.output_name
        )

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("")
    print("=" * 60)
    print("MONITORING COMPLETE")
    print("=" * 60)
    print(
        f"Countries found: {len(countries)}"
    )
    print(
        f"Suspended destinations: "
        f"{len(suspended)}"
    )
    print(
        f"Output file: {OUTPUT_FILE}"
    )
    print("=" * 60)


# ============================================================================
# MAIN
# ============================================================================

def main():
    countries = []
    suspended = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="en-US",
        )

        page.set_default_timeout(
            PAGE_TIMEOUT
        )

        try:

            # ================================================================
            # OPEN WEBSITE
            # ================================================================

            print(
                "Opening Cambodia Post "
                "international calculator..."
            )

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            page.wait_for_timeout(
                3_000
            )

            # ================================================================
            # DISCOVER COUNTRIES
            # ================================================================

            print(
                "Discovering countries..."
            )

            countries = discover_countries(
                page
            )

            print(
                f"Discovered "
                f"{len(countries)} countries."
            )

            print("")
            print(
                "Countries discovered:"
            )

            for country in countries:

                print(
                    f"  {country.website_name} "
                    f"— "
                    f"{country.english_name}"
                )

            # ================================================================
            # TEST COUNTRIES
            # ================================================================

            print("")
            print(
                "Testing countries..."
            )
            print("")

            for index, country in enumerate(
                countries,
                start=1,
            ):

                print(
                    f"[{index}/{len(countries)}] "
                    f"{country.website_name} "
                    f"— "
                    f"{country.english_name}"
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

                except Exception as exc:

                    # --------------------------------------------------------
                    # IMPORTANT:
                    # A technical Playwright failure is NOT automatically
                    # considered a suspended destination.
                    # --------------------------------------------------------

                    print(
                        f"  TECHNICAL ERROR: "
                        f"{exc}"
                    )

                    # Reload for a clean calculator state.
                    try:

                        page.goto(
                            URL,
                            wait_until=(
                                "domcontentloaded"
                            ),
                            timeout=(
                                PAGE_TIMEOUT
                            ),
                        )

                        page.wait_for_timeout(
                            2_000
                        )

                    except Exception as reload_exc:

                        print(
                            f"  Could not reload "
                            f"page: "
                            f"{reload_exc}"
                        )

                        continue

            # ================================================================
            # WRITE OUTPUT
            # ================================================================

            write_output(
                countries,
                suspended,
            )

        except Exception as exc:

            print("")
            print("=" * 60)
            print("MONITOR FAILED")
            print("=" * 60)
            print(str(exc))
            print("=" * 60)

            save_diagnostics(page)

            raise

        finally:

            browser.close()


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    main()
