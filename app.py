import streamlit as st
import requests
import json
import datetime

st.set_page_config(
    page_title="⚽ BetSlip AI",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] {
    background: linear-gradient(160deg, #0a1628 0%, #0d2137 60%, #0a1628 100%) !important;
    color: #e8f0fe !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d3320 0%, #071a10 100%) !important;
    border-right: 2px solid #2e8b57 !important;
}
[data-testid="stSidebar"] * { color: #e8f0fe !important; }
h1,h2,h3 { font-family:'Bebas Neue',sans-serif !important; letter-spacing:2px; }
p,div,label,span { font-family:'DM Sans',sans-serif !important; }
.stButton>button {
    background: linear-gradient(135deg,#1a5c2e,#2e8b57) !important;
    color:white !important; font-family:'Bebas Neue',sans-serif !important;
    font-size:1rem !important; letter-spacing:2px !important;
    border:none !important; border-radius:8px !important;
    transition:all 0.2s !important; width:100% !important;
}
.stButton>button:hover { background:linear-gradient(135deg,#2e8b57,#3daa6e) !important; }
.stTabs [data-baseweb="tab-list"] { background:rgba(0,0,0,0.3) !important; border-radius:10px !important; padding:4px !important; }
.stTabs [data-baseweb="tab"] { background:transparent !important; color:#7a8fa6 !important; font-family:'DM Sans',sans-serif !important; font-weight:600 !important; border-radius:8px !important; }
.stTabs [aria-selected="true"] { background:#1a5c2e !important; color:white !important; }
div[data-testid="stMetricValue"] { color:#f5a623 !important; font-family:'Bebas Neue',sans-serif !important; font-size:1.5rem !important; }
div[data-testid="stMetricLabel"] { color:#7a8fa6 !important; font-size:0.75rem !important; text-transform:uppercase; }
.stSelectbox>div>div, .stNumberInput>div>div>input, .stDateInput>div>div>input {
    background:rgba(0,0,0,0.4) !important; border:1px solid #2e8b57 !important;
    color:#e8f0fe !important; border-radius:8px !important;
}
</style>
""", unsafe_allow_html=True)

LEAGUES = {
    "bundesliga":       ("🇩🇪", "Bundesliga"),
    "la_liga":          ("🇪🇸", "La Liga"),
    "serie_a":          ("🇮🇹", "Serie A"),
    "ligue_1":          ("🇫🇷", "Ligue 1"),
    "eredivisie":       ("🇳🇱", "Eredivisie"),
    "epl":              ("🏴", "Premier League"),
    "champions_league": ("🏆", "Champions League"),
}

# The Odds API sport keys for each league
ODDS_API_SPORT_KEYS = {
    "bundesliga":       "soccer_germany_bundesliga",
    "la_liga":          "soccer_spain_la_liga",
    "serie_a":          "soccer_italy_serie_a",
    "ligue_1":          "soccer_france_ligue_one",
    "eredivisie":       "soccer_netherlands_eredivisie",
    "epl":              "soccer_epl",
    "champions_league": "soccer_uefa_champs_league",
}

def fetch_real_odds(odds_api_key, leagues, target_date):
    """
    Fetch real fixtures + odds from The Odds API.
    Tries Toto.nl specifically first (bookmakers=toto).
    Falls back to eu region if Toto has no coverage for that league.
    Markets fetched: h2h (1X2), totals (over/under), btts (both teams to score).
    """
    fixtures = []
    errors   = []

    def odds_to_pct(o):
        if o and o > 1:
            return round(100 / o)
        return 0

    def extract_markets(bookmakers, home, away):
        """Pull 1X2, totals and btts from bookmaker list."""
        result = {
            "homeOdds": None, "awayOdds": None, "drawOdds": None,
            "over25": None,   "under25": None,
            "bttsYes": None,  "bttsNo": None,
        }
        found_h2h = False
        for bm in bookmakers:
            for mkt in bm.get("markets", []):
                mkey = mkt.get("key","")
                if mkey == "h2h" and not found_h2h:
                    for o in mkt.get("outcomes", []):
                        if o["name"] == home:    result["homeOdds"] = o["price"]
                        elif o["name"] == away:  result["awayOdds"] = o["price"]
                        elif o["name"] == "Draw": result["drawOdds"] = o["price"]
                    if result["homeOdds"]:
                        found_h2h = True
                elif mkey == "totals" and result["over25"] is None:
                    for o in mkt.get("outcomes", []):
                        if o.get("name") == "Over"  and abs(o.get("point",0) - 2.5) < 0.1:
                            result["over25"] = o["price"]
                        elif o.get("name") == "Under" and abs(o.get("point",0) - 2.5) < 0.1:
                            result["under25"] = o["price"]
                elif mkey == "btts" and result["bttsYes"] is None:
                    for o in mkt.get("outcomes", []):
                        if o.get("name") == "Yes": result["bttsYes"] = o["price"]
                        elif o.get("name") == "No":  result["bttsNo"]  = o["price"]
        return result

    for lid in leagues:
        sport_key = ODDS_API_SPORT_KEYS.get(lid)
        if not sport_key:
            continue
        flag, name = LEAGUES[lid]
        try:
            # ── Use session cache to avoid burning API quota ──────────────
            cache       = st.session_state.odds_cache
            cache_date  = st.session_state.odds_cache_date
            today       = datetime.date.today()

            # Invalidate cache if it's from a previous day OR api key changed
            cache_api_key = st.session_state.get("odds_cache_api_key", "")
            if cache_date != today or cache_api_key != odds_api_key:
                st.session_state.odds_cache         = {}
                st.session_state.odds_cache_date    = today
                st.session_state.odds_cache_api_key = odds_api_key
                cache = {}

            if sport_key in cache:
                events = cache[sport_key]
            else:
                base_params = {
                    "apiKey":     odds_api_key,
                    "regions":    "eu",
                    "markets":    "h2h,totals,btts",
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                }
                resp = requests.get(
                    f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
                    params=base_params, timeout=15
                )
                if resp.status_code == 401:
                    raise RuntimeError("Invalid Odds API key")
                if resp.status_code == 429:
                    raise RuntimeError("Odds API rate limit reached (429) — free plan quota used up. Wait until next month or upgrade your plan at the-odds-api.com")
                if resp.status_code == 422:
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"Odds API error {resp.status_code}")
                events = resp.json()
                st.session_state.odds_cache[sport_key] = events

            # Filter events for target_date; if none found, use the nearest future date
            def get_ev_date(ev):
                try:
                    return datetime.datetime.fromisoformat(
                        ev.get("commence_time","").replace("Z","+00:00")
                    ).date()
                except Exception:
                    return None

            today = datetime.date.today()
            target_events = [e for e in events if get_ev_date(e) == target_date]
            if not target_events:
                future = [e for e in events if (get_ev_date(e) or today) >= today]
                if future:
                    nearest = min(get_ev_date(e) for e in future if get_ev_date(e))
                    target_events = [e for e in future if get_ev_date(e) == nearest]
                else:
                    target_events = events

            for ev in target_events:
                home = ev.get("home_team","")
                away = ev.get("away_team","")
                mkts = extract_markets(ev.get("bookmakers",[]), home, away)

                home_pct = odds_to_pct(mkts["homeOdds"])
                away_pct = odds_to_pct(mkts["awayOdds"])

                # Best bet — picks strongest value available on Toto
                if mkts["homeOdds"] and mkts["awayOdds"]:
                    candidates = [
                        ("Home Win",  mkts["homeOdds"]),
                        ("Away Win",  mkts["awayOdds"]),
                    ]
                    if mkts["drawOdds"]:
                        candidates.append(("Draw", mkts["drawOdds"]))
                    if mkts["over25"]:
                        candidates.append(("Over 2.5", mkts["over25"]))
                    if mkts["bttsYes"]:
                        candidates.append(("BTTS Yes", mkts["bttsYes"]))
                    best_label, best_price = min(candidates, key=lambda x: x[1])
                    best_bet = f"{best_label} @ {best_price}"
                else:
                    best_bet = "Home Win"

                try:
                    ct = ev.get("commence_time","")
                    t  = datetime.datetime.fromisoformat(ct.replace("Z","+00:00"))
                    kick_off  = t.strftime("%H:%M")
                    match_date_str = t.strftime("%d %b %Y")
                except Exception:
                    kick_off = "--:--"
                    match_date_str = ""

                fixtures.append({
                    "time":        kick_off,
                    "matchDate":   match_date_str,
                    "league":      name,
                    "flag":        flag,
                    "home":        home,
                    "away":        away,
                    "homeWinPct":  home_pct,
                    "awayWinPct":  away_pct,
                    "homeOdds":    mkts["homeOdds"],
                    "awayOdds":    mkts["awayOdds"],
                    "drawOdds":    mkts["drawOdds"],
                    "over25":      mkts["over25"],
                    "under25":     mkts["under25"],
                    "bttsYes":     mkts["bttsYes"],
                    "bttsNo":      mkts["bttsNo"],
                    "bestBet":     best_bet,
                })

        except RuntimeError:
            raise
        except Exception as e:
            errors.append(f"{name}: {e}")

    return fixtures, errors
SLIP_TYPES = {
    "fortress":   ("🏰", "Fortress",      "6 strongest favourites"),
    "goals":      ("⚽", "Goals Machine", "Over goals & BTTS markets"),
    "protection": ("🛡️", "Protection",    "Draw No Bet & Double Chance"),
    "mixed":      ("🌍", "Mixed Best",    "Best pick per league"),
    "insane":     ("🤪", "INSANE",        "12 legs – 50,000x+ dream"),
    "bonus":      ("⭐", "Claude's Pick", "Best balance selection"),
}
SLIP_ACCENTS = {
    "fortress": "#1a5c2e", "goals": "#e67e22", "protection": "#1a3a6e",
    "mixed": "#2e8b57",    "bonus": "#c8960c",  "insane": "#c0392b",
}




# ── Prompts ──────────────────────────────────────────────────────────────────
FIXTURES_PROMPT = """You must respond with ONLY a JSON object. No text before or after. No markdown. No explanation. Just the raw JSON.

{"date":"","summary":"","fixtures":[{"time":"","league":"","flag":"","home":"","away":"","homeWinPct":0,"awayWinPct":0,"bestBet":""}]}

Max 8 fixtures. Fill all fields. Start your response with { and end with }"""

SLIP_PROMPT = """You must respond with ONLY a JSON object. No text before or after. No markdown. No explanation. Just the raw JSON.

{"type":"","title":"","subtitle":"","estimatedOdds":"","risk":"Low-Medium","riskColor":"green","legs":5,"selections":[{"num":1,"match":"","league":"","flag":"","selection":"","odds":0,"prob":"","reasoning":""}],"analysis":["",""]}

Rules:
- ONLY pick selections that exist in the fixtures context as real available odds fields: homeOdds, awayOdds, drawOdds, over25, under25, bttsYes, bttsNo
- Map each selection to one of these market labels: "Home Win", "Away Win", "Draw", "Over 2.5", "Under 2.5", "BTTS Yes", "BTTS No"
- Set the "odds" field to the exact decimal odd from the fixture (e.g. 1.85)
- If oddsSource is "toto" on the fixture, those are the real Toto.nl odds — use them
- Reasoning max 6 words. Exactly 2 analysis strings. INSANE=10 legs, others=5 legs.
- estimatedOdds = product of all selection odds rounded to 1 decimal followed by "x"
- Start your response with { and end with }"""

def api_call(api_key, system, user_msg):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
              "system": system, "messages": [{"role": "user", "content": user_msg}]},
        timeout=60
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text[:200]}")
    text = resp.json()["content"][0]["text"].strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    if "```" in text:
        for part in text.split("```"):
            part = part.lstrip("json").strip()
            try:
                return json.loads(part)
            except:
                continue

    # Extract JSON by finding outermost { }
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            # Try trimming from end until valid
            for i in range(end, start, -1):
                if text[i] == "}":
                    try:
                        return json.loads(text[start:i+1])
                    except:
                        continue

    raise RuntimeError(f"Could not parse response. Raw: {text[:200]}")

def call_claude(api_key, date_str, leagues, slip_types, odds_api_key="", target_date=None):
    league_names = [f"{LEAGUES[l][0]} {LEAGUES[l][1]}" for l in leagues if l in LEAGUES]
    league_str   = ", ".join(league_names)

    real_fixtures = []
    odds_warnings = []
    using_real    = False

    # ── Step 1: Try The Odds API if key provided ──────────────────────────────
    if odds_api_key and odds_api_key.strip():
        try:
            real_fixtures, odds_warnings = fetch_real_odds(odds_api_key.strip(), leagues, target_date)
            using_real = len(real_fixtures) > 0
        except RuntimeError as e:
            odds_warnings.append(str(e))

    # ── Step 2: Build fixtures context for Claude ─────────────────────────────
    if using_real:
        actual_dates = list({f.get("matchDate","") for f in real_fixtures if f.get("matchDate")})
        date_note = f" · Showing matches on {actual_dates[0]}" if len(actual_dates) == 1 else ""
        fix_context   = real_fixtures
        date_display  = date_str
        summary_text  = f"📡 Real Toto.nl odds · {len(real_fixtures)} matches found{date_note}"
    else:
        # Fall back to AI-generated fixtures
        fix_data     = api_call(api_key, FIXTURES_PROMPT,
            f"Date: {date_str}\nLeagues: {league_str}\nGenerate max 10 fixtures as JSON.")
        fix_context  = fix_data.get("fixtures", [])
        date_display = fix_data.get("date", date_str)
        summary_text = fix_data.get("summary", "AI-generated fixtures")

    # ── Step 3: Generate each slip using real or AI fixture context ───────────
    slips = []
    for stype in slip_types:
        if stype not in SLIP_TYPES:
            continue
        icon, name, desc = SLIP_TYPES[stype]
        legs = 10 if stype == "insane" else 5
        try:
            fixtures_for_prompt = fix_context[:8]
            real_note = (
                "IMPORTANT: These are REAL fixtures with actual Toto.nl odds where oddsSource='toto', "
                "or eu-region odds as fallback. Each fixture contains available markets: "
                "homeOdds (Home Win), awayOdds (Away Win), drawOdds (Draw), "
                "over25 (Over 2.5 goals), under25 (Under 2.5 goals), bttsYes (BTTS Yes), bttsNo (BTTS No). "
                "ONLY build selections from markets where the odds value is NOT null. "
                "Use the exact team names and exact odds values from the fixture data.\n"
                if using_real else ""
            )
            slip = api_call(api_key, SLIP_PROMPT,
                f"Date: {date_str}\nLeagues: {league_str}\n"
                f"Slip type: {name} ({desc})\n"
                f"Type key: {stype}\n"
                f"Legs: {legs}\n"
                f"{real_note}"
                f"Fixtures context: {json.dumps(fixtures_for_prompt)}\n"
                f"Generate ONE {name} slip as JSON.")
            slip["type"] = stype
            slips.append(slip)
        except Exception:
            continue

    return {
        "date":         date_display,
        "summary":      summary_text,
        "fixtures":     fix_context,
        "slips":        slips,
        "using_real":   using_real,
        "odds_warnings": odds_warnings,
    }

if "result"      not in st.session_state: st.session_state.result      = None
if "saved_bets"  not in st.session_state: st.session_state.saved_bets  = []
if "odds_cache"  not in st.session_state: st.session_state.odds_cache  = {}
if "odds_cache_date"    not in st.session_state: st.session_state.odds_cache_date    = None
if "odds_cache_api_key" not in st.session_state: st.session_state.odds_cache_api_key = ""

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:16px 0 8px;">
        <div style="font-size:2.5rem;">⚽</div>
        <div style="font-family:'Bebas Neue',sans-serif;font-size:1.6rem;letter-spacing:3px;">BetSlip AI</div>
        <div style="font-size:0.75rem;color:#7a8fa6;letter-spacing:1px;">POWERED BY CLAUDE</div>
    </div>
    <hr style="border-color:rgba(46,139,87,0.4);margin:10px 0;">
    """, unsafe_allow_html=True)

    try:
        secret_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except:
        secret_key = ""
    if secret_key:
        st.success("✅ Claude API key ready")
        api_key = secret_key
    else:
        st.markdown("**🔑 Claude API Key**")
        api_key = st.text_input("Claude API Key", type="password", placeholder="sk-ant-...", label_visibility="collapsed")

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)

    # ── Odds API Key ──────────────────────────────────────────────────────────
    try:
        secret_odds = st.secrets.get("ODDS_API_KEY", "")
    except:
        secret_odds = ""
    if secret_odds:
        st.success("✅ Odds API key ready (real matches!)")
        odds_api_key = secret_odds
    else:
        st.markdown("**📡 The Odds API Key**")
        st.markdown("<div style='font-size:0.72rem;color:#7a8fa6;margin-bottom:4px;'>Optional – enables real fixtures & odds.<br>Get free key at <b>the-odds-api.com</b></div>", unsafe_allow_html=True)
        odds_api_key = st.text_input("Odds API Key", type="password", placeholder="Paste key here...", label_visibility="collapsed")

    if odds_api_key:
        st.markdown("<div style='font-size:0.72rem;color:#7ecf9e;'>⚡ Real match mode active</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='font-size:0.72rem;color:#f5a623;'>🤖 AI fixture mode (no Odds API key)</div>", unsafe_allow_html=True)

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    st.markdown("**📅 Match Date**")
    match_date = st.date_input("Match Date", value=datetime.date.today(), label_visibility="collapsed")

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    st.markdown("**🏆 Leagues**")
    selected_leagues = [lid for lid,(flag,name) in LEAGUES.items()
                        if st.checkbox(f"{flag} {name}", value=(lid in ["bundesliga","la_liga","serie_a","ligue_1","eredivisie"]), key=f"l_{lid}")]

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    st.markdown("**🎰 Slip Types**")
    selected_slips = [sid for sid,(icon,name,desc) in SLIP_TYPES.items()
                      if st.checkbox(f"{icon} {name}", value=(sid != "insane"), key=f"s_{sid}", help=desc)]

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    generate_btn = st.button("🤖 GENERATE SLIPS")
    st.markdown("""<div style="margin-top:12px;padding:8px;background:rgba(192,57,43,0.15);
        border:1px solid rgba(192,57,43,0.3);border-radius:8px;font-size:0.72rem;color:#ff8a7a;text-align:center;">
        ⚠️ Entertainment only. Gamble responsibly. 18+</div>""", unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:28px 0 14px;">
    <div style="font-family:'Bebas Neue',sans-serif;font-size:2.8rem;letter-spacing:4px;
                background:linear-gradient(135deg,#2e8b57,#f5a623);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
        BETSLIP AI GENERATOR
    </div>
    <div style="color:#7a8fa6;font-size:0.85rem;margin-top:4px;letter-spacing:2px;">
        🇩🇪 · 🇪🇸 · 🇮🇹 · 🇫🇷 · 🇳🇱 · 🏴 · 🏆
    </div>
</div>""", unsafe_allow_html=True)

if generate_btn:
    if not api_key:
        st.error("⚠️ Enter your Anthropic API key in the sidebar.")
    elif not selected_leagues:
        st.error("⚠️ Select at least one league.")
    elif not selected_slips:
        st.error("⚠️ Select at least one slip type.")
    else:
        date_str = match_date.strftime("%A %d %B %Y")
        mode_label = "real matches 📡" if odds_api_key else "AI fixtures 🤖"
        with st.spinner(f"⏳ Fetching {mode_label} and building slips for {date_str}..."):
            try:
                st.session_state.result = call_claude(
                    api_key, date_str, selected_leagues, selected_slips,
                    odds_api_key=odds_api_key, target_date=match_date
                )
            except Exception as e:
                st.error(f"❌ {e}")
                st.session_state.result = None

# ── MAIN TABS ─────────────────────────────────────────────────────────────────
tab_slips, tab_tracker = st.tabs(["🎰 Slips", "📊 Bet Tracker"])

# ════════════════════════ TAB 1 — SLIPS ══════════════════════════════════════
with tab_slips:
    if not st.session_state.result:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;">
            <div style="font-size:4rem;">⚽</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:1.5rem;letter-spacing:2px;color:#3d5a40;margin-bottom:8px;">READY TO GENERATE</div>
            <div style="color:#7a8fa6;font-size:0.88rem;">Pick a date, choose leagues & slips, then hit Generate.</div>
        </div>""", unsafe_allow_html=True)
    else:
        data     = st.session_state.result
        slips    = data.get("slips", [])
        fixtures = data.get("fixtures", [])
        using_real   = data.get("using_real", False)
        odds_warnings = data.get("odds_warnings", [])

        # Mode badge
        if using_real:
            st.markdown("""
            <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(46,139,87,0.2);
                        border:1px solid #2e8b57;border-radius:20px;padding:4px 12px;
                        font-size:0.78rem;font-weight:600;color:#7ecf9e;margin-bottom:10px;">
                📡 LIVE DATA — Real fixtures from The Odds API
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(245,166,35,0.15);
                        border:1px solid rgba(245,166,35,0.4);border-radius:20px;padding:4px 12px;
                        font-size:0.78rem;font-weight:600;color:#f5a623;margin-bottom:10px;">
                🤖 AI MODE — Add Odds API key for real matches
            </div>""", unsafe_allow_html=True)

        for w in odds_warnings:
            st.warning(f"⚠️ Odds API: {w}")

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1a5c2e,#2e8b57);border-radius:12px;
                    padding:16px 20px;margin-bottom:18px;border:1px solid rgba(245,166,35,0.3);">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:1.5rem;letter-spacing:2px;">
                📅 {data.get('date','')}
            </div>
            <div style="font-size:0.88rem;color:rgba(255,255,255,0.85);margin-top:4px;">
                {data.get('summary','')}
            </div>
        </div>""", unsafe_allow_html=True)

        if slips:
            labels = [f"{SLIP_TYPES.get(s.get('type',''),('🎰',))[0]} {s.get('title','')[:14]}" for s in slips]
            labels.append("📋 Fixtures")
            tabs = st.tabs(labels)

            for i, (tab, slip) in enumerate(zip(tabs[:-1], slips)):
                with tab:
                    stype  = slip.get("type","")
                    icon   = SLIP_TYPES.get(stype,("🎰",))[0]
                    color  = SLIP_ACCENTS.get(stype,"#2e8b57")
                    is_ins = stype == "insane"

                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg,{color},{color}bb);border-radius:10px;
                                padding:14px 18px;margin-bottom:12px;
                                {'border:2px solid #f5a623;' if is_ins else ''}">
                        <div style="font-family:'Bebas Neue',sans-serif;font-size:1.4rem;letter-spacing:2px;">
                            {icon} {slip.get('title','')}
                        </div>
                        <div style="font-size:0.82rem;opacity:0.85;">{slip.get('subtitle','')}</div>
                        {'<div style="background:rgba(255,255,255,0.15);border-radius:5px;padding:5px 10px;margin-top:6px;font-size:0.8rem;font-weight:600;">⚠️ STAKE €1–€5 MAX — Dream slip!</div>' if is_ins else ''}
                    </div>""", unsafe_allow_html=True)

                    c1, c2, c3 = st.columns(3)
                    c1.metric("📈 Est. Odds", slip.get("estimatedOdds","?"))
                    c2.metric("📋 Legs", slip.get("legs", len(slip.get("selections",[]))))
                    c3.metric("⚠️ Risk", slip.get("risk","?"))
                    st.markdown("---")

                    for s in slip.get("selections",[]):
                        sel_color = "#ff8a7a" if is_ins else "#7ecf9e"
                        odds_val  = s.get("odds", "")
                        odds_disp = f"@ {odds_val}" if odds_val else s.get("prob","")
                        st.markdown(f"""
                        <div style="display:flex;align-items:center;padding:9px 12px;border-radius:7px;
                                    margin-bottom:4px;background:rgba(255,255,255,0.03);
                                    border:1px solid rgba(255,255,255,0.05);">
                            <div style="width:24px;height:24px;border-radius:50%;background:{color};
                                        display:flex;align-items:center;justify-content:center;
                                        font-size:0.72rem;font-weight:800;flex-shrink:0;margin-right:10px;">
                                {s.get('num','')}
                            </div>
                            <div style="flex:1;">
                                <div style="font-weight:600;font-size:0.86rem;color:#e8f0fe;">{s.get('match','')}</div>
                                <div style="font-size:0.74rem;color:#7a8fa6;margin-top:1px;">
                                    {s.get('flag','')} {s.get('league','')} · {s.get('reasoning','')}
                                </div>
                            </div>
                            <div style="font-weight:700;color:{sel_color};margin:0 12px;font-size:0.86rem;white-space:nowrap;">
                                {s.get('selection','')}
                            </div>
                            <div style="font-weight:700;color:#f5a623;font-size:0.86rem;white-space:nowrap;">
                                {odds_disp}
                            </div>
                        </div>""", unsafe_allow_html=True)

                    analysis = slip.get("analysis",[])
                    if analysis:
                        st.markdown("---")
                        for line in analysis:
                            st.markdown(f"""
                            <div style="background:rgba(255,255,255,0.03);border-left:3px solid {color};
                                        border-radius:6px;padding:7px 12px;margin-bottom:5px;
                                        font-size:0.86rem;color:#c8d8e8;">{line}</div>""", unsafe_allow_html=True)

                    # ── PLACE BET ──────────────────────────────────────────
                    st.markdown("---")
                    st.markdown("#### 💰 Save This Bet")
                    pc1, pc2, pc3 = st.columns([2,2,1])
                    with pc1:
                        stake = st.number_input("Stake (€)", min_value=0.5, max_value=10000.0,
                                                value=5.0, step=0.5, key=f"stake_{i}")
                    with pc2:
                        try:
                            default_odds = float(slip.get("estimatedOdds","10x").replace("x","").split("–")[0].strip())
                        except:
                            default_odds = 10.0
                        odds_input = st.number_input("Odds (multiplier)", min_value=1.0,
                                                     value=default_odds, step=1.0, key=f"odds_{i}")
                    with pc3:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                        save_btn = st.button("💾 SAVE", key=f"save_{i}")

                    potential = round(stake * odds_input, 2)
                    st.markdown(f"<div style='font-size:0.82rem;color:#7a8fa6;margin-top:-8px;'>Potential return: <span style='color:#f5a623;font-weight:700;'>€{potential}</span></div>", unsafe_allow_html=True)

                    if save_btn:
                        bet = {
                            "id": len(st.session_state.saved_bets) + 1,
                            "date": data.get("date",""),
                            "slip_type": stype,
                            "title": slip.get("title",""),
                            "stake": stake,
                            "odds": odds_input,
                            "potential": potential,
                            "result": "⏳ Pending",
                            "profit": None,
                            "saved_at": datetime.datetime.now().strftime("%d %b %Y %H:%M"),
                            "selections": [f"{s.get('match','')} → {s.get('selection','')}" for s in slip.get("selections",[])]
                        }
                        st.session_state.saved_bets.append(bet)
                        st.success(f"✅ Saved! Stake €{stake} · Potential win €{potential} · Check Bet Tracker tab")

            # Fixtures tab
            with tabs[-1]:
                st.markdown("#### 📋 All Fixtures")
                for f in fixtures:
                    src_badge = ""
                    over25   = f.get("over25")
                    bttsYes  = f.get("bttsYes")
                    extra_mkts = ""
                    if over25:
                        extra_mkts += f" · <span style='color:#7ecf9e;'>O2.5 {over25}</span>"
                    if bttsYes:
                        extra_mkts += f" · <span style='color:#7ecf9e;'>BTTS {bttsYes}</span>"

                    st.markdown(f"""
                    <div style="padding:9px 12px;border-radius:7px;margin-bottom:5px;
                                background:rgba(255,255,255,0.03);font-size:0.83rem;">
                        <div style="display:flex;align-items:center;">
                            <div style="width:48px;color:#7a8fa6;">{f.get('time','')}</div>
                            <div style="width:110px;color:#aaa;">{f.get('flag','')} {f.get('league','')}{src_badge}</div>
                            <div style="flex:1;font-weight:600;">
                                {f.get('home','')} <span style="color:#7ecf9e;font-size:0.74rem;">({f.get('homeWinPct','?')}%)</span>
                            </div>
                            <div style="width:22px;text-align:center;color:#555;">vs</div>
                            <div style="flex:1;font-weight:600;">
                                {f.get('away','')} <span style="color:#aaa;font-size:0.74rem;">({f.get('awayWinPct','?')}%)</span>
                            </div>
                        </div>
                        <div style="margin-top:4px;padding-left:158px;font-size:0.76rem;color:#aaa;">
                            1X2:
                            <span style='color:#e8f0fe;font-weight:600;'>{f.get('homeOdds','—')}</span> /
                            <span style='color:#e8f0fe;font-weight:600;'>{f.get('drawOdds','—')}</span> /
                            <span style='color:#e8f0fe;font-weight:600;'>{f.get('awayOdds','—')}</span>
                            {extra_mkts}
                        </div>
                    </div>""", unsafe_allow_html=True)

# ════════════════════════ TAB 2 — BET TRACKER ════════════════════════════════
with tab_tracker:
    st.markdown("""
    <div style="font-family:'Bebas Neue',sans-serif;font-size:1.8rem;letter-spacing:2px;
                margin-bottom:16px;color:#f5a623;">📊 BET TRACKER</div>""", unsafe_allow_html=True)

    bets = st.session_state.saved_bets

    if not bets:
        st.markdown("""
        <div style="text-align:center;padding:50px 20px;">
            <div style="font-size:3rem;">📋</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:1.2rem;letter-spacing:2px;color:#3d5a40;margin-bottom:6px;">NO BETS SAVED YET</div>
            <div style="color:#7a8fa6;font-size:0.86rem;">Generate slips and click "Save" to track your bets here.</div>
        </div>""", unsafe_allow_html=True)
    else:
        # Stats
        total_staked    = sum(b["stake"] for b in bets)
        total_potential = sum(b["potential"] for b in bets)
        won  = [b for b in bets if b["result"] == "✅ Won"]
        lost = [b for b in bets if b["result"] == "❌ Lost"]
        net  = sum(b["profit"] or 0 for b in bets if b["profit"] is not None)

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("📋 Bets",         len(bets))
        c2.metric("💶 Staked",       f"€{total_staked:.2f}")
        c3.metric("🏆 Won",          len(won))
        c4.metric("❌ Lost",         len(lost))
        c5.metric("💰 Net P/L",      f"€{net:.2f}")

        st.markdown("---")

        for idx, bet in enumerate(reversed(bets)):
            real_idx = len(bets) - 1 - idx
            result   = bet["result"]
            color    = SLIP_ACCENTS.get(bet.get("slip_type",""), "#2e8b57")
            icon     = SLIP_TYPES.get(bet.get("slip_type",""), ("🎰",))[0]

            label = f"{icon} {bet['title']}  ·  €{bet['stake']} stake  ·  Pot. €{bet['potential']}  ·  {result}  ·  {bet['saved_at']}"
            with st.expander(label):
                col_info, col_action = st.columns([3, 1])

                with col_info:
                    st.markdown(f"**📅** {bet['date']}  |  **Odds:** {bet['odds']}x  |  **Potential:** €{bet['potential']}")
                    st.markdown("**🎯 Selections:**")
                    for sel in bet.get("selections",[]):
                        st.markdown(f"- {sel}")
                    if bet.get("profit") is not None:
                        p = bet["profit"]
                        pstr = f"+€{p:.2f}" if p >= 0 else f"-€{abs(p):.2f}"
                        color_p = "#7ecf9e" if p >= 0 else "#ff8a7a"
                        st.markdown(f"**💰 P/L:** <span style='color:{color_p};font-weight:700;font-size:1rem;'>{pstr}</span>", unsafe_allow_html=True)

                with col_action:
                    st.markdown("**Update result:**")
                    opts = ["⏳ Pending","✅ Won","❌ Lost"]
                    new_result = st.selectbox("Result", opts,
                                              index=opts.index(result),
                                              key=f"res_{real_idx}",
                                              label_visibility="collapsed")
                    if new_result != result:
                        st.session_state.saved_bets[real_idx]["result"] = new_result
                        if new_result == "✅ Won":
                            profit = round(bet["stake"] * bet["odds"] - bet["stake"], 2)
                            st.session_state.saved_bets[real_idx]["profit"] = profit
                            st.success(f"🏆 +€{profit}")
                        elif new_result == "❌ Lost":
                            st.session_state.saved_bets[real_idx]["profit"] = -bet["stake"]
                        else:
                            st.session_state.saved_bets[real_idx]["profit"] = None
                        st.rerun()

                    if st.button("🗑️ Delete", key=f"del_{real_idx}"):
                        st.session_state.saved_bets.pop(real_idx)
                        st.rerun()
