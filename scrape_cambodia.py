#!/usr/bin/env python3
"""
Cambodia Post international letter checker.

- Opens https://www.cambodiapost.com.kh/calculate/international (English)
- Reads every destination from the country dropdown
- Enters weight 0.02 kg for each, clicks Calculate
- "Letter" service present  -> available (price + estimated delivery time)
- No "Letter" / "Oops" popup -> suspended
- Destinations in the Postcrossing master list but missing from Cambodia Post
  are listed separately (Postcrossing order)
- Writes output_cambodia.txt (no timestamps, so it only changes when data changes)
"""

import re
import sys
import time
import difflib
import unicodedata

from playwright.sync_api import sync_playwright

BASE = "https://www.cambodiapost.com.kh"
LANG_EN_URL = BASE + "/lang/en"
PAGE_URL = BASE + "/calculate/international"
WEIGHT = "0.02"
OUTPUT_FILE = "output_cambodia.txt"
MAX_ERROR_RATIO = 0.05  # if more than 5% of countries error out, keep old file

# --------------------------------------------------------------------------
# Postcrossing master list (number|name)
# --------------------------------------------------------------------------
PC_RAW = """
1|Afghanistan
2|Åland Islands
3|Albania
4|Algeria
5|American Samoa
6|Andorra
7|Angola
8|Anguilla
9|Antarctica
10|Antigua & Barbuda
11|Argentina
12|Armenia
13|Aruba
14|Australia
15|Austria
16|Azerbaijan
17|Bahamas
18|Bahrain
19|Bangladesh
20|Barbados
21|Belarus
22|Belgium
23|Belize
24|Benin
25|Bermuda
26|Bhutan
27|Bolivia
28|Bonaire, Sint Eustatius and Saba
29|Bosnia-Herzegovina
30|Botswana
31|Brazil
32|British Indian Ocean Territory
33|Brunei
34|Bulgaria
35|Burkina Faso
36|Burundi
37|Cabo Verde
38|Cambodia
39|Cameroon
40|Canada
41|Cayman Islands
42|Central African Republic
43|Chad
44|Chile
45|China
46|Christmas Island
47|Cocos Islands
48|Colombia
49|Comoros
50|Congo
51|Dem. Rep. Of Congo
52|Cook Islands
53|Costa Rica
54|Côte d'Ivoire
55|Croatia
56|Cuba
57|Curaçao
58|Cyprus
59|Czechia
60|Denmark
61|Djibouti
62|Dominica
63|Dominican Republic
64|Ecuador
65|Egypt
66|El Salvador
67|Equatorial Guinea
68|Eritrea
69|Estonia
70|Eswatini /Swaziland
71|Ethiopia
72|Falkland Islands /Malvinas
73|Faroe Islands
74|Fiji
75|Finland
76|France
77|French Guiana
78|French Polynesia
79|French Southern Territories
80|Gabon
81|Gambia
82|Georgia
83|Germany
84|Ghana
85|Gibraltar
86|Greece
87|Greenland
88|Grenada
89|Guadeloupe
90|Guam
91|Guatemala
92|Guernsey
93|Guinea
94|Guinea-Bissau
95|Guyana
96|Haiti
97|Honduras
98|Hong Kong
99|Hungary
100|Iceland
101|India
102|Indonesia
103|Iran
104|Iraq
105|Ireland
106|Isle of Man
107|Israel
108|Italy
109|Jamaica
110|Japan
111|Jersey
112|Jordan
113|Kazakhstan
114|Kenya
115|Kiribati
116|Korea(North)
117|Korea(South)
118|Kosovo
119|Kuwait
120|Kyrgyzstan
121|Laos
122|Latvia
123|Lebanon
124|Lesotho
125|Liberia
126|Libya
127|Liechtenstein
128|Lithuania
129|Luxembourg
130|Macao
131|Madagascar
132|Malawi
133|Malaysia
134|Maldives
135|Mali
136|Malta
137|Marshall Islands
138|Martinique
139|Mauritania
140|Mauritius
141|Mayotte
142|Mexico
143|Micronesia
144|Moldova
145|Monaco
146|Mongolia
147|Montenegro
148|Montserrat
149|Morocco
150|Mozambique
151|Myanmar
152|Namibia
153|Nauru / Naoero
154|Nepal
155|Netherlands
156|New Caledonia
157|New Zealand
158|Nicaragua
159|Niger
160|Nigeria
161|Niue
162|Norfolk Island
163|Northern Mariana Islands
164|North Macedonia
165|Norway
166|Oman
167|Pakistan
168|Palau
169|Palestine
170|Panama
171|Papua New Guinea
172|Paraguay
173|Peru
174|Philippines
175|Pitcairn
176|Poland
177|Portugal
178|Puerto Rico
179|Qatar
180|Réunion
181|Romania
182|Russia
183|Rwanda
184|Saint Barthélemy
185|Saint Helena, Ascension and Tristan da Cunha
186|Saint Kitts and Nevis
187|Saint Lucia
188|Saint Martin
189|Saint Pierre & Miquelon
190|Saint Vincent and the Grenadines
191|Samoa
192|San Marino
193|Sao Tome and Principe
194|Saudi Arabia
195|Senegal
196|Serbia
197|Seychelles
198|Sierra Leone
199|Singapore
200|Sint Maarten
201|Slovakia
202|Slovenia
203|Solomon Islands
204|Somalia
205|South Africa
206|South Georgia and S. Sandwich Islands
207|South Sudan
208|Spain
209|Sri Lanka
210|Sudan
211|Suriname
212|Svalbard and Jan Mayen
213|Sweden
214|Switzerland
215|Syria
216|Taiwan
217|Tajikistan
218|Tanzania
219|Thailand
220|Timor-Leste
221|Togo
222|Tokelau
223|Tonga
224|Trinidad and Tobago
225|Tunisia
226|Turkey
227|Turkmenistan
228|Turks and Caicos Islands
229|Tuvalu
230|Uganda
231|Ukraine
232|United Arab Emirates
233|United Kingdom
234|Uruguay
235|U.S.A.
236|U.S. Minor Outlying Islands
237|Uzbekistan
238|Vanuatu
239|Vatican
240|Venezuela
241|Vietnam
242|Virgin Islands (UK)
243|Virgin Islands of the USA
244|Wallis & Futuna
245|Western Sahara
246|Yemen
247|Zambia
248|Zimbabwe
"""

# Extra spellings Cambodia Post might use  ->  Postcrossing number
ALIASES = {
    "united states": 235, "united states of america": 235, "usa": 235, "us": 235,
    "united kingdom of great britain and northern ireland": 233,
    "great britain": 233, "uk": 233,
    "korea north": 116, "north korea": 116, "korea dem peoples republic of": 116,
    "democratic peoples republic of korea": 116, "korea democratic peoples republic": 116,
    "korea south": 117, "south korea": 117, "korea republic of": 117,
    "republic of korea": 117, "korea republic": 117,
    "russian federation": 182,
    "czech republic": 59,
    "turkiye": 226,
    "cape verde": 37,
    "ivory coast": 54, "cote d ivoire": 54,
    "republic of the congo": 50, "congo brazzaville": 50, "congo republic": 50,
    "democratic republic of the congo": 51, "congo kinshasa": 51,
    "congo dem rep": 51, "dr congo": 51, "drc": 51, "congo democratic republic": 51,
    "dem rep of congo": 51, "congo the democratic republic of the": 51,
    "burma": 151,
    "east timor": 220, "timor leste": 220,
    "macau": 130, "macau sar": 130,
    "hong kong sar": 98, "hong kong sar china": 98,
    "macedonia": 164, "republic of north macedonia": 164,
    "swaziland": 70, "eswatini": 70,
    "palestinian territory": 169, "palestinian territories": 169,
    "state of palestine": 169, "palestine state of": 169,
    "vatican city": 239, "holy see": 239, "vatican city state": 239,
    "brunei darussalam": 33,
    "lao pdr": 121, "lao peoples democratic republic": 121,
    "viet nam": 241,
    "iran islamic republic of": 103, "islamic republic of iran": 103,
    "syrian arab republic": 215,
    "tanzania united republic of": 218, "united republic of tanzania": 218,
    "moldova republic of": 144, "republic of moldova": 144,
    "micronesia federated states of": 143, "federated states of micronesia": 143,
    "bosnia and herzegovina": 29, "bosnia herzegovina": 29,
    "antigua and barbuda": 10,
    "british virgin islands": 242, "virgin islands british": 242,
    "virgin islands us": 243, "us virgin islands": 243,
    "united states virgin islands": 243, "virgin islands u s": 243,
    "saint helena": 185, "st helena": 185,
    "bonaire": 28, "bonaire sint eustatius and saba": 28,
    "cocos keeling islands": 47, "cocos islands": 47,
    "pitcairn islands": 175,
    "svalbard": 212,
    "south georgia and the south sandwich islands": 206,
    "wallis and futuna islands": 244,
    "saint martin french part": 188, "st martin": 188,
    "sint maarten dutch part": 200,
    "the gambia": 81, "the bahamas": 17,
    "the netherlands": 155, "holland": 155,
    "kyrgyz republic": 120,
    "united states minor outlying islands": 236,
    "falkland islands malvinas": 72, "falkland islands": 72,
    "nauru": 153,
    "saint pierre and miquelon": 189,
    "sao tome and principe": 193,
    "taiwan province of china": 216,
    "myanmar burma": 151,
    "reunion": 180,
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\bst\b", "saint", s)
    return s


PC_NAME = {}      # number -> display name
PC_BY_NORM = {}   # normalised name -> number
for line in PC_RAW.strip().splitlines():
    num_s, name = line.split("|", 1)
    num = int(num_s)
    PC_NAME[num] = name.strip()
    for part in name.split("/"):
        PC_BY_NORM[norm(part)] = num
for k, v in ALIASES.items():
    PC_BY_NORM.setdefault(norm(k), v)


def find_pc_number(name: str):
    n = norm(name)
    if n in PC_BY_NORM:
        return PC_BY_NORM[n]
    # also try without text in parentheses
    n2 = norm(re.sub(r"\(.*?\)", "", name))
    if n2 in PC_BY_NORM:
        return PC_BY_NORM[n2]
    close = difflib.get_close_matches(n, PC_BY_NORM.keys(), n=1, cutoff=0.9)
    if close:
        print(f"  [fuzzy] '{name}' -> '{close[0]}'", file=sys.stderr)
        return PC_BY_NORM[close[0]]
    return None


# --------------------------------------------------------------------------
# Page helpers
# --------------------------------------------------------------------------
ROWS_JS = """
() => Array.from(document.querySelectorAll('table tr'))
  .filter(r => r.offsetParent !== null)
  .map(r => Array.from(r.querySelectorAll('th,td'))
      .map(c => (c.innerText || '').trim().replace(/\\s+/g, ' ')))
"""

SERVICE_RE = re.compile(r"letter|(^|\W)ao($|\W)", re.I)
PRICE_RE = re.compile(r"[\d][\d,\.]*")
EST_RE = re.compile(r"day|ថ្ងៃ|\d+\s*(to|-|–)\s*\d+", re.I)


def get_rows(page):
    try:
        return page.evaluate(ROWS_JS)
    except Exception:
        return []


def oops_visible(page) -> bool:
    try:
        loc = page.get_by_text(re.compile(r"oops", re.I))
        for i in range(min(loc.count(), 5)):
            if loc.nth(i).is_visible():
                return True
    except Exception:
        pass
    return False


def dismiss_popups(page):
    try:
        page.keyboard.press("Escape")
        for label in ("OK", "Ok", "Close", "close", "×"):
            btn = page.locator(f'button:has-text("{label}")')
            for i in range(btn.count()):
                if btn.nth(i).is_visible():
                    btn.nth(i).click(timeout=1000)
                    break
    except Exception:
        pass


def find_country_select(page):
    """Return index of the <select> with the most options."""
    best_idx, best_n = None, 0
    sel = page.locator("select")
    for i in range(sel.count()):
        n = sel.nth(i).locator("option").count()
        if n > best_n:
            best_idx, best_n = i, n
    return best_idx


def read_options(page, idx):
    opts = page.locator("select").nth(idx).locator("option")
    out = []
    for i in range(opts.count()):
        val = opts.nth(i).get_attribute("value")
        txt = (opts.nth(i).inner_text() or "").strip()
        if val is None or val.strip() == "" or not txt:
            continue
        out.append((val, txt))
    return out


def set_country(page, idx, value):
    page.locator("select").nth(idx).evaluate(
        """(el, val) => {
            el.value = val;
            if (window.jQuery) { window.jQuery(el).val(val).trigger('change'); }
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )


def find_weight_input(page):
    for sel in ('input[name*="weight" i]', 'input[id*="weight" i]',
                'input[type="number"]', 'input[type="text"]'):
        loc = page.locator(sel)
        for i in range(loc.count()):
            if loc.nth(i).is_visible():
                return loc.nth(i)
    return None


def click_calculate(page):
    pat = re.compile(r"calculate|គណនា", re.I)
    for sel in ("button", "input[type=button]", "input[type=submit]", "a.btn", "a"):
        loc = page.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                txt = (el.inner_text() or "") + " " + (el.get_attribute("value") or "")
            except Exception:
                continue
            if pat.search(txt) and el.is_visible():
                el.click()
                return True
    btn = page.locator("button[type=submit]")
    if btn.count():
        btn.first.click()
        return True
    return False


def load_form(page):
    page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("select", state="attached", timeout=30000)
    time.sleep(0.5)


def parse_price(cells):
    for c in cells:
        if ("៛" in c or "KHR" in c.upper() or "riel" in c.lower()) and PRICE_RE.search(c):
            return PRICE_RE.search(c).group(0)
    for c in cells:
        if re.fullmatch(r"[\d][\d,\.]*", c.strip()):
            return c.strip()
    return None


def parse_estimate(cells):
    for c in cells:
        if EST_RE.search(c) and not re.fullmatch(r"letter.*", c, re.I):
            return c.strip()
    return None


def check_country(page, idx, value):
    """Returns dict: status in {available, suspended, error}"""
    load_form(page)
    set_country(page, idx, value)
    w = find_weight_input(page)
    if w is None:
        raise RuntimeError("weight input not found")
    w.fill(WEIGHT)
    if not click_calculate(page):
        raise RuntimeError("Calculate button not found")

    deadline = time.time() + 12
    rows, svc_rows, oops = [], [], False
    while time.time() < deadline:
        if oops_visible(page):
            oops = True
            break
        rows = get_rows(page)
        svc_rows = [r for r in rows if any(SERVICE_RE.search(c) for c in r)]
        if svc_rows:
            time.sleep(0.8)
            rows = get_rows(page)
            svc_rows = [r for r in rows if any(SERVICE_RE.search(c) for c in r)]
            break
        time.sleep(0.4)

    if oops:
        dismiss_popups(page)
        return {"status": "suspended", "reason": 'Oops" pop up window showed up'}

    if not svc_rows:
        return {"status": "noresult"}

    services = []
    letter_row = None
    for r in svc_rows:
        for c in r:
            if SERVICE_RE.search(c):
                services.append(c)
                if c.strip().lower() == "letter":
                    letter_row = r
                break

    if letter_row is None:
        return {
            "status": "suspended",
            "reason": "It has " + ", ".join(f'"{s}"' for s in services)
                      + ' but does not have "Letter" service',
        }

    price = parse_price(letter_row)
    est = parse_estimate(letter_row)
    return {
        "status": "available",
        "price": (price + " ៛") if price else "price not found",
        "est": est or "estimate not found",
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    results = []  # (cp_name, pc_number or None, result dict)
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        # Switch site language to English (stored in the session/cookie)
        try:
            page.goto(LANG_EN_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Language switch warning: {e}", file=sys.stderr)

        load_form(page)
        idx = find_country_select(page)
        if idx is None:
            print("ERROR: country dropdown not found", file=sys.stderr)
            sys.exit(1)
        options = read_options(page, idx)
        if not options:
            print("ERROR: no destinations found", file=sys.stderr)
            sys.exit(1)

        latin = sum(1 for _, t in options if re.search(r"[A-Za-z]", t))
        if latin < len(options) * 0.8:
            print("WARNING: destination names do not look English; "
                  "language switch may have failed.", file=sys.stderr)

        print(f"Found {len(options)} destinations.")
        debug_left = 3

        for n, (val, name) in enumerate(options, 1):
            res = None
            for attempt in range(3):
                try:
                    res = check_country(page, idx, val)
                    if res["status"] == "noresult":
                        if debug_left > 0 and attempt == 2:
                            debug_left -= 1
                            try:
                                body = page.inner_text("body")[:1500]
                            except Exception:
                                body = ""
                            print(f"[debug] no result for {name}:\n{body}\n", file=sys.stderr)
                        res = None
                        time.sleep(1)
                        continue
                    break
                except Exception as e:
                    print(f"  attempt {attempt + 1} failed for {name}: {e}", file=sys.stderr)
                    res = None
                    time.sleep(2)
            if res is None:
                errors.append(name)
                results.append((name, find_pc_number(name),
                                {"status": "error"}))
                print(f"[{n}/{len(options)}] {name}: ERROR")
            else:
                results.append((name, find_pc_number(name), res))
                print(f"[{n}/{len(options)}] {name}: {res['status']}")
            time.sleep(0.3)

        browser.close()

    if len(errors) > len(options) * MAX_ERROR_RATIO:
        print(f"Too many errors ({len(errors)}). Keeping the old output file.",
              file=sys.stderr)
        sys.exit(1)

    # ---------------------------------------------------------------- output
    def label(num):
        return f"{num}" if num is not None else "?"

    available, suspended, unchecked, unmatched = [], [], [], []
    seen_pc = set()
    for name, num, res in results:
        if num is not None:
            seen_pc.add(num)
        else:
            unmatched.append(name)
        if res["status"] == "available":
            available.append(f"{label(num)}. {name} {res['price']} {res['est']}")
        elif res["status"] == "suspended":
            suspended.append(f'{label(num)}. {name} ("{res["reason"]})'
                             if res["reason"].startswith('Oops')
                             else f'{label(num)}. {name} ({res["reason"]})')
        else:
            unchecked.append(f"{label(num)}. {name}")

    # fix Oops formatting: show as ("Oops" Pop up window showed up)
    suspended = [s.replace('("Oops" pop up', '("Oops" Pop up')
                  .replace('(Oops" pop up', '("Oops" Pop up')
                  .replace('"Oops" pop up', '"Oops" Pop up') for s in suspended]
    suspended = [re.sub(r'\(Oops" Pop up window showed up\)',
                        '("Oops" Pop up window showed up)', s) for s in suspended]

    missing = [f"{num}. {PC_NAME[num]}" for num in sorted(PC_NAME) if num not in seen_pc]

    lines = []
    lines.append("CAMBODIA POST - INTERNATIONAL LETTER SERVICE (weight 0.02 kg)")
    lines.append(f"Destinations on Cambodia Post list: {len(results)}")
    lines.append(f"Available: {len(available)} | Suspended: {len(suspended)} | "
                 f"Missing from Cambodia Post list: {len(missing)}")
    lines.append("")
    lines.append("=== AVAILABLE DESTINATIONS (Cambodia Post order) ===")
    lines.extend(available)
    lines.append("")
    lines.append('=== SUSPENDED DESTINATIONS - "Letter" service unavailable (Cambodia Post order) ===')
    lines.extend(suspended)
    lines.append("")
    lines.append("=== SUSPENDED DESTINATIONS - missing from Cambodia Post list (Postcrossing order) ===")
    lines.extend(missing)
    if unchecked:
        lines.append("")
        lines.append("=== NOT CHECKED (error, will retry next run) ===")
        lines.extend(unchecked)
    if unmatched:
        lines.append("")
        lines.append("=== NOT MATCHED TO POSTCROSSING LIST (add an alias in the script) ===")
        lines.extend(f"?. {n}" for n in unmatched)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
