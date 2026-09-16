import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "https://www.cambodiapost.com.kh/calculate/international"
OUTPUT_FILE = Path("output_cambodia.txt")

WEIGHT = "0.02"

PAGE_TIMEOUT = 60_000
RESULT_TIMEOUT = 30_000

# The website's country control is currently represented as a Select
# control in the rendered page.  We still support autocomplete/combobox
# controls because the implementation may change.
COUNTRY_SEARCH_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def visible(locator):
    try:
        return locator.is_visible()
    except Exception:
        return False


def get_body_text(page):
    try:
        return clean_text(page.locator("body").inner_text())
    except Exception:
        return ""


def save_diagnostics(page, reason):
    """
    Save diagnostic files inside the GitHub Actions workspace.

    These are useful if Cambodia Post changes its page structure.
    They are intentionally not committed to the repository.
    """
    try:
        Path("debug_cambodiapost.html").write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Could not save HTML diagnostic: {exc}")

    try:
        page.screenshot(
            path="debug_cambodiapost.png",
            full_page=True,
        )
    except Exception as exc:
        print(f"Could not save screenshot diagnostic: {exc}")

    print(f"Diagnostic information saved because: {reason}")


# ---------------------------------------------------------------------
# COUNTRY CONTROL
# ---------------------------------------------------------------------

def find_country_select(page):
    """
    Look for a native HTML select associated with Country.
    """

    selects = page.locator("select:visible")

    try:
        count = selects.count()
    except Exception:
        return None

    for i in range(count):
        select = selects.nth(i)

        try:
            name = clean_text(
                select.get_attribute("name") or ""
            ).lower()

            element_id = clean_text(
                select.get_attribute("id") or ""
            ).lower()

            aria = clean_text(
                select.get_attribute("aria-label") or ""
            ).lower()

            title = clean_text(
                select.get_attribute("title") or ""
            ).lower()

            combined = (
                f"{name} {element_id} "
                f"{aria} {title}"
            )

            if "country" in combined:
                return select

            # Inspect the parent text.
            parent_text = clean_text(
                select.locator("xpath=..").inner_text()
            ).lower()

            if "country" in parent_text:
                return select

        except Exception:
            continue

    # If there is only one visible select on this page,
    # it is very likely the country selector.
    try:
        if count == 1:
            return selects.first
    except Exception:
        pass

    return None


def find_country_combobox(page):
    """
    Find a custom Country combobox/autocomplete control.
    """

    selectors = [
        '[role="combobox"]:visible',
        'input[placeholder*="Country" i]:visible',
        'input[aria-label*="Country" i]:visible',
        'input[name*="country" i]:visible',
        'input[id*="country" i]:visible',
        '[class*="country" i] input:visible',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            candidate = locator.nth(i)

            if not visible(candidate):
                continue

            try:
                attributes = " ".join(
                    [
                        candidate.get_attribute("name") or "",
                        candidate.get_attribute("id") or "",
                        candidate.get_attribute("placeholder") or "",
                        candidate.get_attribute("aria-label") or "",
                    ]
                ).lower()

                if "country" in attributes:
                    return candidate
            except Exception:
                pass

            # For role=combobox, the surrounding label may identify it.
            try:
                parent_text = clean_text(
                    candidate.locator("xpath=..").inner_text()
                ).lower()

                if "country" in parent_text:
                    return candidate
            except Exception:
                pass

    return None


def find_country_control(page):
    """
    Return either a native select or a custom combobox.
    """

    select = find_country_select(page)

    if select is not None:
        print("Country control detected as a native SELECT.")
        return "select", select

    combobox = find_country_combobox(page)

    if combobox is not None:
        print("Country control detected as a COMBOBOX.")
        return "combobox", combobox

    # Last-resort inspection of all visible select/combobox elements.
    print("Could not identify Country control by attributes.")
    print("Visible SELECT count:", page.locator("select:visible").count())
    print(
        "Visible COMBOBOX count:",
        page.locator('[role="combobox"]:visible').count(),
    )

    save_diagnostics(
        page,
        "Country control could not be identified",
    )

    raise RuntimeError(
        "Could not find the Country control."
    )


# ---------------------------------------------------------------------
# COUNTRY DISCOVERY
# ---------------------------------------------------------------------

def countries_from_native_select(select):
    """
    Get all countries directly from a native SELECT.

    This is the preferred method because it gives us the complete
    list without having to type A-Z.
    """

    countries = []

    try:
        options = select.locator("option")
        count = options.count()
    except Exception:
        return countries

    for i in range(count):
        option = options.nth(i)

        try:
            text = clean_text(option.inner_text())
            value = clean_text(
                option.get_attribute("value") or ""
            )

            if not text:
                continue

            lower = text.casefold()

            ignored = {
                "country",
                "select",
                "select country",
                "please select",
                "please select country",
            }

            if lower in ignored:
                continue

            # Skip placeholder options.
            if not value and lower in ignored:
                continue

            countries.append(text)
        except Exception:
            continue

    # Remove duplicates while preserving order.
    unique = []
    seen = set()

    for country in countries:
        key = country.casefold()

        if key not in seen:
            seen.add(key)
            unique.append(country)

    unique.sort(key=str.casefold)

    return unique


def get_visible_options(page):
    """
    Return text from visible autocomplete options.
    """

    selectors = [
        '[role="option"]:visible',
        ".ng-option:visible",
        ".dropdown-item:visible",
        ".select2-results__option:visible",
        "mat-option:visible",
        "li:visible",
    ]

    found = []

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            item = locator.nth(i)

            if not visible(item):
                continue

            try:
                text = clean_text(item.inner_text())
            except Exception:
                continue

            if not text:
                continue

            lowered = text.casefold()

            if lowered in {
                "country",
                "select",
                "select country",
                "no results found",
                "loading...",
            }:
                continue

            found.append(text)

    unique = []
    seen = set()

    for item in found:
        key = item.casefold()

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def discover_countries_from_combobox(page, combobox):
    """
    Discover countries from a custom autocomplete control.

    Search A-Z because the website behavior described by the user
    filters countries based on entered letters.
    """

    found = {}

    for letter in COUNTRY_SEARCH_LETTERS:
        print(f"Searching Country with: {letter}")

        try:
            combobox.click()

            # Clear existing text.
            try:
                combobox.fill("")
            except Exception:
                combobox.press("Control+A")
                combobox.press("Backspace")

            combobox.fill(letter)

            page.wait_for_timeout(800)

            options = get_visible_options(page)

            for country in options:
                found[country.casefold()] = country

        except Exception as exc:
            print(
                f"Warning: search {letter} failed: {exc}"
            )

    countries = list(found.values())
    countries.sort(key=str.casefold)

    return countries


def discover_countries(page):
    """
    Discover the complete country list.
    """

    control_type, control = find_country_control(page)

    if control_type == "select":
        countries = countries_from_native_select(control)

        print(
            f"Found {len(countries)} countries in SELECT."
        )

    else:
        countries = discover_countries_from_combobox(
            page,
            control,
        )

        print(
            f"Found {len(countries)} countries "
            f"through autocomplete."
        )

    if not countries:
        save_diagnostics(
            page,
            "Country control was found but no countries were discovered",
        )

        raise RuntimeError(
            "Country control was found, but no countries "
            "were discovered."
        )

    return countries


# ---------------------------------------------------------------------
# COUNTRY SELECTION
# ---------------------------------------------------------------------

def select_country(page, country):
    """
    Select exactly one country.
    """

    control_type, control = find_country_control(page)

    if control_type == "select":
        print(f"Selecting country with SELECT: {country}")

        # Try selecting by visible label first.
        try:
            control.select_option(label=country)
            page.wait_for_timeout(400)
            return
        except Exception:
            pass

        # Some sites have duplicated/modified labels.
        options = control.locator("option")

        try:
            count = options.count()
        except Exception:
            count = 0

        for i in range(count):
            option = options.nth(i)

            try:
                text = clean_text(option.inner_text())

                if text.casefold() == country.casefold():
                    value = option.get_attribute("value")

                    control.select_option(
                        value=value
                    )

                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue

        raise RuntimeError(
            f"Could not select country from SELECT: {country}"
        )

    # Custom autocomplete.
    print(
        f"Selecting country with COMBOBOX: {country}"
    )

    control.click()

    try:
        control.fill(country)
    except Exception:
        control.press("Control+A")
        control.press("Backspace")
        control.type(country)

    page.wait_for_timeout(800)

    # Look for exact matching option.
    selectors = [
        '[role="option"]:visible',
        ".ng-option:visible",
        ".dropdown-item:visible",
        ".select2-results__option:visible",
        "mat-option:visible",
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            option = locator.nth(i)

            if not visible(option):
                continue

            try:
                text = clean_text(option.inner_text())
            except Exception:
                continue

            if text.casefold() == country.casefold():
                option.click()
                page.wait_for_timeout(400)
                return

    # Keyboard fallback.
    try:
        control.press("ArrowDown")
        control.press("Enter")
        page.wait_for_timeout(400)
        return
    except Exception:
        pass

    raise RuntimeError(
        f"Could not select country: {country}"
    )


# ---------------------------------------------------------------------
# WEIGHT
# ---------------------------------------------------------------------

def find_weight_input(page):
    """
    Find the Weight field.
    """

    selectors = [
        'input[placeholder*="Weight" i]:visible',
        'input[aria-label*="Weight" i]:visible',
        'input[name*="weight" i]:visible',
        'input[id*="weight" i]:visible',
        'input[formcontrolname*="weight" i]:visible',
        'input[type="number"]:visible',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            candidate = locator.nth(i)

            if not visible(candidate):
                continue

            try:
                attributes = " ".join(
                    [
                        candidate.get_attribute("name") or "",
                        candidate.get_attribute("id") or "",
                        candidate.get_attribute("placeholder") or "",
                        candidate.get_attribute("aria-label") or "",
                    ]
                ).lower()

                if (
                    "weight" in attributes
                    or "kg" in attributes
                ):
                    return candidate
            except Exception:
                continue

    # The current page exposes one obvious weight input.
    inputs = page.locator("input:visible")

    try:
        count = inputs.count()
    except Exception:
        count = 0

    candidates = []

    for i in range(count):
        candidate = inputs.nth(i)

        try:
            input_type = (
                candidate.get_attribute("type") or ""
            ).lower()

            placeholder = (
                candidate.get_attribute("placeholder")
                or ""
            ).lower()

            if (
                input_type == "number"
                or "weight" in placeholder
                or "kg" in placeholder
            ):
                candidates.append(candidate)
        except Exception:
            continue

    if candidates:
        return candidates[-1]

    raise RuntimeError(
        "Could not find the Weight input field."
    )


def set_weight(page):
    weight_input = find_weight_input(page)

    print(f"Entering weight: {WEIGHT}")

    weight_input.click()
    weight_input.fill(WEIGHT)

    # Trigger blur/change handlers.
    try:
        weight_input.press("Tab")
    except Exception:
        pass

    page.wait_for_timeout(300)


# ---------------------------------------------------------------------
# CALCULATE
# ---------------------------------------------------------------------

def find_calculate_button(page):
    """
    Find the Calculate button.

    The current rendered page exposes the button through its
    Khmer label rather than necessarily through the English word.
    """

    # Try English and Khmer accessible names.
    patterns = [
        re.compile(r"calculate", re.IGNORECASE),
        re.compile(r"គណនា"),
    ]

    for pattern in patterns:
        try:
            locator = page.get_by_role(
                "button",
                name=pattern,
            )

            count = locator.count()

            for i in range(count):
                button = locator.nth(i)

                if visible(button):
                    return button
        except Exception:
            continue

    # Inspect all visible buttons.
    buttons = page.locator("button:visible")

    try:
        count = buttons.count()
    except Exception:
        count = 0

    for i in range(count):
        button = buttons.nth(i)

        try:
            text = clean_text(
                button.inner_text()
            ).casefold()

            if (
                "calculate" in text
                or "គណនា" in text
            ):
                return button
        except Exception:
            continue

    # Some implementations use an input submit button.
    submits = page.locator(
        'input[type="submit"]:visible, '
        'input[type="button"]:visible'
    )

    try:
        count = submits.count()
    except Exception:
        count = 0

    for i in range(count):
        button = submits.nth(i)

        try:
            text = " ".join(
                [
                    button.get_attribute("value") or "",
                    button.get_attribute("aria-label") or "",
                ]
            ).casefold()

            if (
                "calculate" in text
                or "គណនា" in text
            ):
                return button
        except Exception:
            continue

    raise RuntimeError(
        "Could not find the Calculate button."
    )


def wait_for_calculation(page):
    """
    Wait for the calculation response.
    """

    # Wait for Loading to appear/disappear if the site uses it.
    try:
        loading = page.get_by_text(
            re.compile(
                r"loading",
                re.IGNORECASE,
            )
        )

        if loading.count() > 0:
            try:
                loading.first.wait_for(
                    state="visible",
                    timeout=3_000,
                )
            except Exception:
                pass

            try:
                loading.first.wait_for(
                    state="hidden",
                    timeout=RESULT_TIMEOUT,
                )
            except Exception:
                pass
    except Exception:
        pass

    # Give the result component time to render.
    page.wait_for_timeout(2_000)


# ---------------------------------------------------------------------
# RESULT ANALYSIS
# ---------------------------------------------------------------------

def find_letter_service(page):
    """
    Find the Letter service/result.

    Returns the most useful containing element text.
    """

    # Search text nodes/elements containing Letter.
    selectors = [
        "text=Letter",
        '[class*="letter" i]',
        '[id*="letter" i]',
        "tr",
        "div",
        "td",
    ]

    candidates = []

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            element = locator.nth(i)

            if not visible(element):
                continue

            try:
                text = clean_text(
                    element.inner_text()
                )
            except Exception:
                continue

            if not text:
                continue

            if "letter" in text.casefold():
                candidates.append(
                    (len(text), text)
                )

    if not candidates:
        return ""

    # Prefer the smallest useful container containing Letter.
    candidates.sort(key=lambda x: x[0])

    for length, text in candidates:
        lowered = text.casefold()

        if (
            "price" in lowered
            or "khr" in lowered
            or "៛" in text
            or re.search(r"\d", text)
        ):
            return text

    return candidates[0][1]


def detect_error(page):
    """
    Detect an actual result/error message.
    """

    error_selectors = [
        '[role="alert"]:visible',
        ".alert-danger:visible",
        ".alert-warning:visible",
        ".error:visible",
        ".errors:visible",
        ".invalid-feedback:visible",
        ".text-danger:visible",
        ".toast:visible",
    ]

    patterns = [
        r"\berror\b",
        r"something went wrong",
        r"failed",
        r"cannot",
        r"unable",
        r"not available",
        r"service unavailable",
        r"suspended",
        r"no service",
        r"គ្មាន",
        r"មិនអាច",
        r"កំហុស",
    ]

    for selector in error_selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            element = locator.nth(i)

            if not visible(element):
                continue

            try:
                text = clean_text(
                    element.inner_text()
                )
            except Exception:
                continue

            if not text:
                continue

            for pattern in patterns:
                if re.search(
                    pattern,
                    text,
                    flags=re.IGNORECASE,
                ):
                    return True, text

    return False, ""


def letter_has_price(letter_text):
    """
    Check whether the Letter service contains Price (KHR).

    We require Letter to have a price-like KHR result and a numeric
    value. A generic number somewhere else on the page is not enough.
    """

    if not letter_text:
        return False

    lowered = letter_text.casefold()

    has_price_label = (
        bool(
            re.search(
                r"price\s*\(\s*khr\s*\)",
                lowered,
                flags=re.IGNORECASE,
            )
        )
        or bool(
            re.search(
                r"price\s+khr",
                lowered,
                flags=re.IGNORECASE,
            )
        )
        or "price" in lowered
        or "khr" in lowered
        or "៛" in letter_text
        or "រៀល" in letter_text
    )

    if not has_price_label:
        return False

    # There must be a numeric price.
    return bool(
        re.search(
            r"\d[\d,.\s]*",
            letter_text,
        )
    )


def evaluate_result(page):
    """
    Apply the user's exact suspension rules:

    1. Error message -> suspended.
    2. Letter missing -> suspended.
    3. Letter exists but Price (KHR) missing -> suspended.
    4. Otherwise active.
    """

    error_found, error_text = detect_error(page)

    if error_found:
        return True, "error", error_text

    letter_text = find_letter_service(page)

    if not letter_text:
        return (
            True,
            "letter_missing",
            "",
        )

    if not letter_has_price(letter_text):
        return (
            True,
            "letter_price_missing",
            letter_text,
        )

    return (
        False,
        "active",
        letter_text,
    )


# ---------------------------------------------------------------------
# COUNTRY TEST
# ---------------------------------------------------------------------

def test_country(page, country):
    """
    Follow the required order exactly:

    1) select a country
    2) enter 0.02 kg
    3) click Calculate
    4) inspect the result
    """

    print("")
    print("----------------------------------------")
    print(f"Testing: {country}")
    print("----------------------------------------")

    # 1) Select country
    select_country(page, country)

    # 2) Enter 0.02
    set_weight(page)

    # 3) Click Calculate
    calculate_button = find_calculate_button(page)

    print("Clicking Calculate...")
    calculate_button.click()

    # 4) Inspect result
    wait_for_calculation(page)

    suspended, reason, details = evaluate_result(page)

    if suspended:
        print(
            f"SUSPENDED: {country} "
            f"({reason})"
        )

        if details:
            print(
                f"Result details: {details[:500]}"
            )

        return True

    print(f"ACTIVE: {country}")

    if details:
        print(
            f"Letter result: {details[:500]}"
        )

    return False


# ---------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------

def write_output(countries, suspended):
    """
    Create output_cambodia.txt.
    """

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    lines = [
        "Cambodia Post International Shipping Monitor",
        f"Checked: {timestamp}",
        f"Website: {URL}",
        f"Weight tested: {WEIGHT} kg",
        "",
        "LIST 1 - ALL COUNTRIES",
        f"Total countries: {len(countries)}",
        "",
    ]

    lines.extend(countries)

    lines.extend(
        [
            "",
            "LIST 2 - SUSPENDED DESTINATIONS",
            f"Total suspended destinations: "
            f"{len(suspended)}",
            "",
        ]
    )

    if suspended:
        lines.extend(suspended)
    else:
        lines.append("None")

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    print("Starting Cambodia Post monitor...")
    print(f"URL: {URL}")
    print(f"Weight: {WEIGHT} kg")

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
            PAGE_TIMEOUT
        )

        try:
            print("")
            print("Opening Cambodia Post...")

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            page.wait_for_timeout(4_000)

            print("")
            print("Discovering countries...")

            countries = discover_countries(page)

            print("")
            print("========================================")
            print(
                f"TOTAL COUNTRIES FOUND: {len(countries)}"
            )
            print("========================================")

            for country in countries:
                print(country)

            print("")
            print(
                "Beginning destination testing..."
            )

            suspended = []

            for index, country in enumerate(
                countries,
                start=1,
            ):
                print("")
                print(
                    f"[{index}/{len(countries)}]"
                )

                try:
                    is_suspended = test_country(
                        page,
                        country,
                    )

                    if is_suspended:
                        suspended.append(country)

                except Exception as exc:
                    print("")
                    print(
                        f"TECHNICAL ERROR testing "
                        f"{country}: {exc}"
                    )

                    # Do NOT classify a technical failure as
                    # suspended. Reload the calculator and continue.
                    try:
                        print(
                            "Reloading Cambodia Post "
                            "calculator..."
                        )

                        page.goto(
                            URL,
                            wait_until="domcontentloaded",
                            timeout=PAGE_TIMEOUT,
                        )

                        page.wait_for_timeout(3_000)

                    except Exception as reload_exc:
                        print(
                            f"Reload failed: "
                            f"{reload_exc}"
                        )

            write_output(
                countries,
                suspended,
            )

            print("")
            print("========================================")
            print("MONITOR COMPLETE")
            print("========================================")
            print(
                f"Total countries: {len(countries)}"
            )
            print(
                f"Suspended destinations: "
                f"{len(suspended)}"
            )
            print(
                f"Output file: {OUTPUT_FILE}"
            )
            print("========================================")

        except Exception:
            # Save diagnostics for failures occurring before
            # country testing begins.
            save_diagnostics(
                page,
                "Fatal monitor error",
            )
            raise

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
