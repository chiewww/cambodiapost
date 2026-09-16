import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


URL = "https://www.cambodiapost.com.kh/calculate/international"
OUTPUT_FILE = Path("output_cambodia.txt")

WEIGHT = "0.02"

# The website filters the country list when text is typed.
# Searching A-Z lets us discover the complete list without
# depending on the dropdown being open initially.
SEARCH_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

PAGE_TIMEOUT = 60_000
SHORT_TIMEOUT = 5_000
RESULT_TIMEOUT = 20_000


def clean_text(text):
    """Normalize whitespace."""
    return re.sub(r"\s+", " ", text or "").strip()


def visible_texts(locator):
    """Return cleaned text for visible elements represented by a locator."""
    results = []

    try:
        count = locator.count()
    except Exception:
        return results

    for i in range(count):
        try:
            item = locator.nth(i)

            if not item.is_visible():
                continue

            text = clean_text(item.inner_text())

            if text:
                results.append(text)
        except Exception:
            continue

    return results


def find_country_input(page):
    """
    Find the input used for the Country autocomplete/search field.

    The Cambodia Post page is dynamically generated, so we deliberately
    try several reasonable selectors rather than depending on one
    CSS class that could change.
    """

    selectors = [
        'input[placeholder*="Country" i]',
        'input[placeholder*="country" i]',
        'input[aria-label*="Country" i]',
        'input[name*="country" i]',
        'input[id*="country" i]',
        'input[formcontrolname*="country" i]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()

            for i in range(count):
                candidate = locator.nth(i)

                if candidate.is_visible():
                    return candidate
        except Exception:
            pass

    # Fallback: inspect visible text inputs.
    inputs = page.locator("input:visible")

    try:
        count = inputs.count()

        for i in range(count):
            candidate = inputs.nth(i)

            try:
                placeholder = clean_text(
                    candidate.get_attribute("placeholder") or ""
                )
                aria_label = clean_text(
                    candidate.get_attribute("aria-label") or ""
                )
                name = clean_text(
                    candidate.get_attribute("name") or ""
                )
                element_id = clean_text(
                    candidate.get_attribute("id") or ""
                )

                combined = (
                    f"{placeholder} {aria_label} "
                    f"{name} {element_id}"
                ).lower()

                if "country" in combined:
                    return candidate
            except Exception:
                continue
    except Exception:
        pass

    raise RuntimeError(
        "Could not find the Country input field."
    )


def find_weight_input(page):
    """Find the Weight(kg) input."""

    selectors = [
        'input[placeholder*="Weight" i]',
        'input[aria-label*="Weight" i]',
        'input[name*="weight" i]',
        'input[id*="weight" i]',
        'input[formcontrolname*="weight" i]',
        'input[type="number"]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()

            for i in range(count):
                candidate = locator.nth(i)

                if candidate.is_visible():
                    return candidate
        except Exception:
            pass

    # Fallback: visible inputs other than the country field.
    inputs = page.locator("input:visible")

    try:
        count = inputs.count()

        for i in range(count):
            candidate = inputs.nth(i)

            try:
                input_type = (
                    candidate.get_attribute("type") or ""
                ).lower()

                placeholder = clean_text(
                    candidate.get_attribute("placeholder") or ""
                ).lower()

                aria_label = clean_text(
                    candidate.get_attribute("aria-label") or ""
                ).lower()

                name = clean_text(
                    candidate.get_attribute("name") or ""
                ).lower()

                combined = (
                    f"{input_type} {placeholder} "
                    f"{aria_label} {name}"
                )

                if "weight" in combined or input_type == "number":
                    return candidate
            except Exception:
                continue
    except Exception:
        pass

    raise RuntimeError(
        "Could not find the Weight input field."
    )


def click_country_control(page):
    """
    Click the Country control to open its dropdown/autocomplete.

    The input itself may be the control, but clicking it is harmless
    when it is an autocomplete input.
    """

    country_input = find_country_input(page)

    try:
        country_input.click()
    except Exception:
        country_input.focus()

    page.wait_for_timeout(500)

    return country_input


def get_dropdown_options(page):
    """
    Collect visible dropdown option text.

    We intentionally inspect several common autocomplete/option
    structures because the site's frontend implementation may change.
    """

    selectors = [
        '[role="option"]:visible',
        '.dropdown-item:visible',
        '.select2-results__option:visible',
        '.ng-option:visible',
        'mat-option:visible',
        'li:visible',
    ]

    found = []

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()

            for i in range(count):
                item = locator.nth(i)

                try:
                    if not item.is_visible():
                        continue

                    text = clean_text(item.inner_text())

                    if not text:
                        continue

                    # Ignore obvious non-country UI entries.
                    lowered = text.lower()

                    ignored = {
                        "country",
                        "select",
                        "select country",
                        "no results found",
                        "loading...",
                    }

                    if lowered in ignored:
                        continue

                    found.append(text)
                except Exception:
                    continue
        except Exception:
            continue

    # Preserve order while removing duplicates.
    unique = []
    seen = set()

    for text in found:
        key = text.casefold()

        if key not in seen:
            seen.add(key)
            unique.append(text)

    return unique


def discover_countries(page):
    """
    Discover all country names by searching each alphabet letter.

    This follows the website behavior described by the user:
    countries appear after text is entered into the Country field.
    """

    country_input = find_country_input(page)

    all_countries = {}
    successful_searches = 0

    for letter in SEARCH_LETTERS:
        try:
            # Make sure the autocomplete is active.
            country_input.click()

            # Clear the previous search.
            country_input.fill("")

            # Type one letter.
            country_input.fill(letter)

            # Give the frontend time to filter/render.
            page.wait_for_timeout(700)

            # Wait briefly for an option if one exists.
            try:
                page.locator('[role="option"]:visible').first.wait_for(
                    state="visible",
                    timeout=2_000,
                )
            except Exception:
                pass

            options = get_dropdown_options(page)

            for country in options:
                all_countries[country.casefold()] = country

            if options:
                successful_searches += 1

        except Exception as exc:
            print(
                f"Warning: country search '{letter}' failed: {exc}"
            )

    # Clear the search field at the end.
    try:
        country_input.fill("")
        page.keyboard.press("Escape")
    except Exception:
        pass

    countries = list(all_countries.values())

    # Sort alphabetically, case-insensitively.
    countries.sort(key=lambda x: x.casefold())

    if not countries:
        raise RuntimeError(
            "No countries were discovered. "
            "The Country control or its autocomplete behavior "
            "may have changed."
        )

    print(
        f"Discovered {len(countries)} countries "
        f"from {successful_searches} alphabet searches."
    )

    return countries


def select_country(page, country):
    """
    Select a country from the autocomplete/dropdown.
    """

    country_input = find_country_input(page)

    # Open the autocomplete.
    country_input.click()

    # Search using the complete country name.
    country_input.fill(country)

    page.wait_for_timeout(700)

    # Try exact accessible option first.
    exact_selectors = [
        '[role="option"]:visible',
        '.dropdown-item:visible',
        '.select2-results__option:visible',
        '.ng-option:visible',
        'mat-option:visible',
    ]

    for selector in exact_selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()

            for i in range(count):
                option = locator.nth(i)

                if not option.is_visible():
                    continue

                text = clean_text(option.inner_text())

                if text.casefold() == country.casefold():
                    option.click()
                    page.wait_for_timeout(300)
                    return
        except Exception:
            continue

    # Fallback: use keyboard selection after typing.
    try:
        country_input.press("ArrowDown")
        country_input.press("Enter")
        page.wait_for_timeout(300)
        return
    except Exception:
        pass

    # Last fallback: click visible text.
    try:
        locator = page.get_by_text(
            country,
            exact=True,
        )

        count = locator.count()

        for i in range(count):
            item = locator.nth(i)

            if item.is_visible():
                item.click()
                page.wait_for_timeout(300)
                return
    except Exception:
        pass

    raise RuntimeError(
        f"Could not select country: {country}"
    )


def set_weight(page):
    """Enter exactly 0.02 kg."""

    weight_input = find_weight_input(page)

    weight_input.click()
    weight_input.fill("")
    weight_input.fill(WEIGHT)

    # Blur the field so any Angular/React/Vue change handler fires.
    try:
        weight_input.press("Tab")
    except Exception:
        page.mouse.click(10, 10)

    page.wait_for_timeout(300)


def find_calculate_button(page):
    """Find the Calculate button."""

    # English text.
    candidates = [
        page.get_by_role(
            "button",
            name=re.compile(r"calculate", re.I),
        ),
        page.get_by_text(
            re.compile(r"calculate", re.I),
            exact=False,
        ),
    ]

    # Khmer text visible on the current page is also accepted.
    candidates.append(
        page.get_by_role(
            "button",
            name=re.compile(r"គណនា"),
        )
    )

    for locator in candidates:
        try:
            count = locator.count()

            for i in range(count):
                candidate = locator.nth(i)

                if candidate.is_visible():
                    return candidate
        except Exception:
            continue

    # Fallback: inspect buttons.
    buttons = page.locator("button:visible")

    try:
        count = buttons.count()

        for i in range(count):
            button = buttons.nth(i)

            try:
                text = clean_text(button.inner_text()).lower()

                if (
                    "calculate" in text
                    or "គណនា" in text
                ):
                    return button
            except Exception:
                continue
    except Exception:
        pass

    raise RuntimeError(
        "Could not find the Calculate button."
    )


def get_page_text(page):
    """Return the visible page text."""

    try:
        return clean_text(page.locator("body").inner_text())
    except Exception:
        return ""


def wait_for_calculation(page):
    """
    Wait for the Calculate request/result.

    The page currently displays a Loading... element while the
    calculation is being performed, so wait for it to disappear
    when possible, then allow a short rendering period.
    """

    try:
        loading = page.get_by_text(
            re.compile(r"Loading\.\.\.", re.I)
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

    page.wait_for_timeout(1_500)


def has_error_message(page, body_text):
    """
    Detect an error message after Calculate.

    We check both visible DOM elements and common error words.
    """

    error_patterns = [
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

    # First inspect common error containers.
    selectors = [
        '[role="alert"]:visible',
        '.alert-danger:visible',
        '.alert-warning:visible',
        '.error:visible',
        '.errors:visible',
        '.invalid-feedback:visible',
        '.text-danger:visible',
        '.toast:visible',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()

            for i in range(count):
                item = locator.nth(i)

                if not item.is_visible():
                    continue

                text = clean_text(item.inner_text())

                if text:
                    lowered = text.casefold()

                    for pattern in error_patterns:
                        if re.search(
                            pattern,
                            lowered,
                            re.IGNORECASE,
                        ):
                            return True, text
        except Exception:
            continue

    # Inspect the page text.
    lowered_body = body_text.casefold()

    for pattern in error_patterns:
        if re.search(
            pattern,
            lowered_body,
            re.IGNORECASE,
        ):
            return True, pattern

    return False, ""


def extract_letter_service_text(page, body_text):
    """
    Extract the text associated with the Letter service.

    The exact markup can change, so this searches the rendered page
    rather than relying on one CSS class.
    """

    # First try elements whose text contains Letter.
    letter_selectors = [
        "text=Letter",
        '[class*="letter" i]',
        '[id*="letter" i]',
    ]

    for selector in letter_selectors:
        try:
            locator = page.locator(selector)

            count = locator.count()

            for i in range(count):
                item = locator.nth(i)

                if not item.is_visible():
                    continue

                text = clean_text(item.inner_text())

                if "letter" not in text.casefold():
                    continue

                # The useful result is often contained in a parent card,
                # table row, or service block.
                for level in range(1, 5):
                    try:
                        parent = item.locator(
                            "/.." * level
                        )

                        parent_text = clean_text(
                            parent.inner_text()
                        )

                        if parent_text:
                            if (
                                "price" in parent_text.casefold()
                                or "khr" in parent_text.casefold()
                                or "letter" in parent_text.casefold()
                            ):
                                return parent_text
                    except Exception:
                        continue

                return text
        except Exception:
            continue

    # Fallback: extract a window around "Letter" from the page text.
    match = re.search(
        r"letter.{0,500}",
        body_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        return clean_text(match.group(0))

    return ""


def letter_has_price(page, body_text):
    """
    Determine whether the Letter service contains a Price (KHR).

    We require both:
      - Letter
      - a Price/KHR value associated with Letter

    This deliberately does NOT treat unrelated prices elsewhere
    on the page as a valid Letter price.
    """

    letter_text = extract_letter_service_text(
        page,
        body_text,
    )

    if not letter_text:
        return False, ""

    lowered = letter_text.casefold()

    # The site may render the label as:
    # Price (KHR)
    # Price KHR
    # KHR
    # or a Khmer equivalent.
    price_label_patterns = [
        r"price\s*\(\s*khr\s*\)",
        r"price\s+khr",
        r"price",
        r"khr",
        r"៛",
        r"រៀល",
    ]

    has_price = any(
        re.search(
            pattern,
            lowered,
            flags=re.IGNORECASE,
        )
        for pattern in price_label_patterns
    )

    if not has_price:
        return False, letter_text

    # A price should normally contain digits.
    has_number = bool(
        re.search(
            r"\d[\d,.\s]*",
            letter_text,
        )
    )

    if not has_number:
        return False, letter_text

    return True, letter_text


def test_country(page, country):
    """
    Test one country exactly in the requested order:

      1. Select country
      2. Enter 0.02
      3. Click Calculate
      4. Inspect result
    """

    print(f"Testing: {country}")

    select_country(page, country)

    # Step 2: weight
    set_weight(page)

    # Step 3: Calculate
    calculate_button = find_calculate_button(page)
    calculate_button.click()

    # Step 4: wait for and inspect result
    wait_for_calculation(page)

    body_text = get_page_text(page)

    error_found, error_text = has_error_message(
        page,
        body_text,
    )

    if error_found:
        print(
            f"  -> SUSPENDED (error: {error_text})"
        )
        return True, "error"

    # If Letter is missing, destination is suspended.
    letter_text = extract_letter_service_text(
        page,
        body_text,
    )

    if not letter_text:
        print("  -> SUSPENDED (Letter service missing)")
        return True, "letter_missing"

    # If Letter exists but has no Price (KHR), suspended.
    price_found, service_text = letter_has_price(
        page,
        body_text,
    )

    if not price_found:
        print(
            "  -> SUSPENDED "
            "(Letter Price (KHR) missing)"
        )
        print(f"     Letter result: {service_text}")
        return True, "letter_price_missing"

    print("  -> ACTIVE (Letter price found)")
    return False, "active"


def write_output(countries, suspended):
    """Write the final monitoring file."""

    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    lines = []

    lines.append(
        "Cambodia Post International Shipping Monitor"
    )
    lines.append(
        f"Checked: {now}"
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
        lines.append(country)

    lines.append("")
    lines.append(
        "LIST 2 - SUSPENDED DESTINATIONS"
    )
    lines.append(
        f"Total suspended destinations: {len(suspended)}"
    )
    lines.append("")

    if suspended:
        for country in suspended:
            lines.append(country)
    else:
        lines.append("None")

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main():
    print("Starting Cambodia Post monitor...")
    print(f"URL: {URL}")

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

        page.set_default_timeout(PAGE_TIMEOUT)

        try:
            print("Opening Cambodia Post...")
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            page.wait_for_timeout(3_000)

            # LIST 1
            print("Discovering countries...")
            countries = discover_countries(page)

            # LIST 2
            suspended = []

            print(
                f"Testing {len(countries)} countries..."
            )

            for index, country in enumerate(
                countries,
                start=1,
            ):
                print(
                    f"[{index}/{len(countries)}] "
                    f"{country}"
                )

                try:
                    is_suspended, reason = test_country(
                        page,
                        country,
                    )

                    if is_suspended:
                        suspended.append(country)

                except Exception as exc:
                    # A technical failure is NOT automatically treated
                    # as a postal suspension. We record it loudly and
                    # continue with the next country.
                    print(
                        f"  -> ERROR testing {country}: "
                        f"{exc}"
                    )

                    # Reload the calculator before continuing.
                    try:
                        page.goto(
                            URL,
                            wait_until="domcontentloaded",
                            timeout=PAGE_TIMEOUT,
                        )
                        page.wait_for_timeout(2_000)
                    except Exception as reload_exc:
                        print(
                            f"  -> Reload failed: "
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

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
