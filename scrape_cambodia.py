#!/usr/bin/env python3
"""
Cambodia Post international letter checker.

- Reads every destination from https://www.cambodiapost.com.kh/select2/getAllCountries
- Opens https://www.cambodiapost.com.kh/calculate/international (English)
- Enters weight 0.02 kg for each destination, clicks Calculate
- "Letter" service present   -> available (price + estimated delivery time)
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
COUNTRIES_URL = BASE + "/select2/getAllCountries"
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

# ISO 3166 two-letter codes for each Postcrossing number (used as a fallback,
# because Cambodia Post names contain spelling variations / typos).
ISO_RAW = (
    "1 AF,2 AX,3 AL,4 DZ,5 AS,6 AD,7 AO,8 AI,9 AQ,10 AG,11 AR,12 AM,13 AW,14 AU,"
    "15 AT,16 AZ,17 BS,18 BH,19 BD,20 BB,21 BY,22 BE,23 BZ,24 BJ,25 BM,26 BT,"
    "27 BO,28 BQ,29 BA,30 BW,31 BR,32 IO,33 BN,34 BG,35 BF,36 BI,37 CV,38 KH,"
    "39 CM,40 CA,41 KY,42 CF,43 TD,44 CL,45 CN,46 CX,47 CC,48 CO,49 KM,50 CG,"
    "51 CD,52 CK,53 CR,54 CI,55 HR,56 CU,57 CW,58 CY,59 CZ,60 DK,61 DJ,62 DM,"
    "63 DO,64 EC,65 EG,66 SV,67 GQ,68 ER,69 EE,70 SZ,71 ET,72 FK,73 FO,74 FJ,"
    "75 FI,76 FR,77 GF,78 PF,79 TF,80 GA,81 GM,82 GE,83 DE,84 GH,85 GI,86 GR,"
    "87 GL,88 GD,89 GP,90 GU,91 GT,92 GG,93 GN,94 GW,95 GY,96 HT,97 HN,98 HK,"
    "99 HU,100 IS,101 IN,102 ID,103 IR,104 IQ,105 IE,106 IM,107 IL,108 IT,"
    "109 JM,110 JP,111 JE,112 JO,113 KZ,114 KE,115 KI,116 KP,117 KR,118 XK,"
    "119 KW,120 KG,121 LA,122 LV,123 LB,124 LS,125 LR,126 LY,127 LI,128 LT,"
    "129 LU,130 MO,131 MG,132 MW,133 MY,134 MV,135 ML,136 MT,137 MH,138 MQ,"
    "139 MR,140 MU,141 YT,142 MX,143 FM,144 MD,145 MC,146 MN,147 ME,148 MS,"
    "149 MA,150 MZ,151 MM,152 NA,153 NR,154 NP,155 NL,156 NC,157 NZ,158 NI,"
    "159 NE,160 NG,161 NU,162 NF,163 MP,164 MK,165 NO,166 OM,167 PK,168 PW,"
    "169 PS,170 PA,171 PG,172 PY,173 PE,174 PH,175 PN,176 PL,177 PT,178 PR,"
    "179 QA,180 RE,181 RO,182 RU,183 RW,184 BL,185 SH,186 KN,187 LC,188 MF,"
    "189 PM,190 VC,191 WS,192 SM,193 ST,194 SA,195 SN,196 RS,197 SC,198 SL,"
    "199 SG,200 SX,201 SK,202 SI,203 SB,204 SO,205 ZA,206 GS,207 SS,208 ES,"
    "209 LK,210 SD,211 SR,212 SJ,213 SE,214 CH,215 SY,216 TW,217 TJ,218 TZ,"
    "219 TH,220 TL,221 TG,222 TK,223 TO,224 TT,225 TN,226 TR,227 TM,228 TC,"
    "229 TV,230 UG,231 UA,232 AE,233 GB,234 UY,235 US,236 UM,237 UZ,238 VU,"
    "239 VA,240 VE,241 VN,242 VG,243 VI,244 WF,245 EH,246 YE,247 ZM,248 ZW"
)

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
PC_BY_ISO = {}    # ISO2 code -> number
for line in PC_RAW.strip().splitlines():
    num_s, name = line.split("|", 1)
    num = int(num_s)
    PC_NAME[num] = name.strip()
    for part in name.split("/"):
        PC_BY_NORM[norm(part)] = num
for k, v in ALIASES.items():
    PC_BY_NORM.setdefault(norm(k), v)
for pair in ISO_RAW.split(","):
    n_s, code = pair.strip().split(" ")
    PC_BY_ISO[code] = int(n_s)


def find_pc_number(name: str, code: str = ""):
    n = norm(name)
    by_name = PC_BY_NORM.get(n)
    if by_name is None:
        n2 = norm(re.sub(r"\(.*?\)", "", name))
        by_name = PC_BY_NORM.get(n2)
    by_code = PC_BY_ISO.get((code or "").upper())

    if by_name is not None:
        if by_code is not None and by_code != by_name:
            print(f"  [note] '{name}' ({code}): name->{by_name} but code->{by_code}; "
                  f"using name", file=sys.stderr)
        return by_name
    if by_code is not None:
        print(f"  [code match] '{name}' ({code}) -> {by_code}", file=sys.stderr)
        return by_code
    close = difflib.get_close_matches(n, PC_BY_NORM.keys(), n=1, cutoff=0.85)
    if close:
        print(f"  [fuzzy] '{name}' -> '{close[0]}'", file=sys.stderr)
        return PC_BY_NORM[close[0]]
    return None


def pretty_name(upper_name: str) -> str:
    s = upper_name.strip().title()
    for a, b in ((" And ", " and "), (" Of ", " of "), (" The ", " the "),
                 ("'S", "'s"), (" De ", " de "), (" Da ", " da ")):
        s = s.replace(a, b)
    return s


# --------------------------------------------------------------------------
# Destination list from the select2 JSON endpoint
# --------------------------------------------------------------------------
def fetch_countries(page):
    items, seen = [], set()
    p, last_page = 1, 1
    while p <= last_page:
        data = None
        for attempt in range(3):
            try:
                r = page.request.get(
                    COUNTRIES_URL,
                    params={"page": p},
                    headers={"Accept": "application/json",
                             "X-Requested-With": "XMLHttpRequest"},
                    timeout=30000,
                )
                if r.ok:
                    data = r.json()
                    break
                print(f"  page {p}: HTTP {r.status}", file=sys.stderr)
            except Exception as e:
                print(f"  page {p} attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(2)
        if data is None:
            raise RuntimeError(f"could not fetch country list page {p}")
        last_page = int(data.get("last_page", 1))
        for d in data.get("data", []):
            cid = d.get("id")
            text = (d.get("text") or "").strip()
            if cid is None or not text or cid in seen:
                continue
            seen.add(cid)
            m = re.match(r"^\s*([A-Za-z0-9]{2,3})\s*\((.*)\)\s*$", text)
            if m:
                code, raw_name = m.group(1).upper(), m.group(2)
            else:
                code, raw_name = "", text
            items.append({
                "id": cid,
                "text": text,
                "code": code,
                "name": pretty_name(raw_name),
                "raw_name": raw_name,
            })
        p += 1
    return items


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


def get_country_select(page):
    sel = page.locator("select.select2-hidden-accessible")
    if sel.count():
        return sel.first
    return page.locator("select").first


def set_country_inject(page, item):
    """Put the country into the (select2 / AJAX) <select> directly."""
    sel = get_country_select(page)
    sel.evaluate(
        """(el, a) => {
            el.innerHTML = '';
            const opt = new Option(a.text, String(a.id), true, true);
            el.appendChild(opt);
            el.value = String(a.id);
            if (window.jQuery) {
                window.jQuery(el).trigger('change');
                window.jQuery(el).trigger({type: 'select2:select',
                                           params: {data: {id: a.id, text: a.text}}});
            }
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        {"id": item["id"], "text": item["text"]},
    )


def set_country_ui(page, item):
    """Fallback: open the select2 box, type the name, click the result."""
    box = page.locator(".select2-selection, .select2-container").first
    box.click()
    search = page.locator("input.select2-search__field").first
    search.fill(item["raw_name"])
    opt = page.locator(".select2-results__option", has_text=item["text"]).first
    opt.wait_for(state="visible", timeout=8000)
    opt.click()


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
    time.sleep(0.8)


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


def check_country(page, item, attempt):
    """Returns dict: status in {available, suspended, noresult}"""
    load_form(page)
    if attempt == 1:
        set_country_ui(page, item)
    else:
        set_country_inject(page, item)

    w = find_weight_input(page)
    if w is None:
        raise RuntimeError("weight input not found")
    w.fill(WEIGHT)
    if not click_calculate(page):
        raise RuntimeError("Calculate button not found")

    deadline = time.time() + 12
    svc_rows, oops = [], False
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
        return {"status": "suspended", "reason": '"Oops" Pop up window showed up'}

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
    results = []  # (item, pc_number or None, result dict)
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

        # Switch site language to English (stored in session / cookie)
        try:
            page.goto(LANG_EN_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Language switch warning: {e}", file=sys.stderr)

        # Load the form once so we get session cookies for the JSON endpoint
        load_form(page)

        try:
            items = fetch_countries(page)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        if not items:
            print("ERROR: no destinations found", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(items)} destinations.")
        debug_left = 3

        for n, item in enumerate(items, 1):
            res = None
            for attempt in range(3):
                try:
                    r = check_country(page, item, attempt)
                    if r["status"] == "noresult":
                        if debug_left > 0 and attempt == 2:
                            debug_left -= 1
                            try:
                                body = page.inner_text("body")[:1500]
                            except Exception:
                                body = ""
                            print(f"[debug] no result for {item['name']}:\n{body}\n",
                                  file=sys.stderr)
                        time.sleep(1)
                        continue
                    res = r
                    break
                except Exception as e:
                    print(f"  attempt {attempt + 1} failed for {item['name']}: {e}",
                          file=sys.stderr)
                    time.sleep(2)

            pc = find_pc_number(item["raw_name"], item["code"])
            if res is None:
                errors.append(item["name"])
                results.append((item, pc, {"status": "error"}))
                print(f"[{n}/{len(items)}] {item['name']}: ERROR")
            else:
                results.append((item, pc, res))
                print(f"[{n}/{len(items)}] {item['name']}: {res['status']}")
            time.sleep(0.3)

        browser.close()

    if len(errors) > len(items) * MAX_ERROR_RATIO:
        print(f"Too many errors ({len(errors)}). Keeping the old output file.",
              file=sys.stderr)
        sys.exit(1)

    # ---------------------------------------------------------------- output
    def label(num):
        return f"{num}" if num is not None else "?"

    available, suspended, unchecked, unmatched = [], [], [], []
    seen_pc = set()
    for item, num, res in results:
        name = item["name"]
        if num is not None:
            seen_pc.add(num)
        else:
            unmatched.append(name)
        if res["status"] == "available":
            available.append(f"{label(num)}. {name} {res['price']} {res['est']}")
        elif res["status"] == "suspended":
            suspended.append(f"{label(num)}. {name} ({res['reason']})")
        else:
            unchecked.append(f"{label(num)}. {name}")

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
