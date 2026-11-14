# AI Crypto Signal Agent — 10 Coins (Long/Short → Telegram)

Binance data + 1h trend + 15m entry wala signal agent. Har 15 minute scan karta hai,
rules match hone par Telegram par LONG/SHORT signal bhejta hai, aur har signal ka
result journal mein track karta hai taake **real win-rate** pata chale.

Coins: TRX, DOGE, ADA, XLM, HBAR, CRO, SHIB, PEPE, DOT, VET (USDT pairs).

---

## 1. Pehle ye samajh lein (important)

- Ye **auto-trading bot nahi** hai. Ye signal deta hai — order aap khud lagayenge.
- Koi bhi bot **60–70% accuracy guarantee nahi** kar sakta. Jo kar sakte hain:
  1. strict rules (kam lekin high-quality signals),
  2. har signal ka record,
  3. backtest se real win-rate ka pata.
- Is repo mein `scripts/backtest.py` aur `scripts/tune.py` isi liye hain. Number khud verify karein.
- Signal ka matlab: Entry, Stop Loss, TP1/TP2/TP3. **Stop loss ke bina trade kabhi na karein.**
- Per trade **1% se zyada risk na karein** (default 1%).

---

## 2. Agent ka logic (default rules)

**Trend filter (1h + 4h)**
- LONG: EMA50 > EMA200, price EMA50 ke upar, EMA50 rising (1h).
- SHORT: ulta.
- **4h alignment (naya):** 1h candles se 4h resample karke EMA50/EMA200 check hota hai.
  Sirf wahi signals aate hain jahan 4h trend bhi same direction mein ho (chop mein skip).
  Sirf last *completed* 4h candle use hoti hai — koi lookahead nahi.

**MMC (Mirror Market Concept) layer — naya**
- **BOS / CHoCH:** 15m par purane swing high/low ka fresh break (structure shift).
- **FVG (Fair Value Gap):** displacement ke baad bana unfilled imbalance, jismein price
  wapas rebalance karne aa raha ho.
- **Liquidity sweep:** swing extreme ke paar wick jaakar close wapas range mein (stop-hunt).
- **Premium / discount:** 1h dealing range (60 candles) mein price ki position —
  LONG discount mein, SHORT premium mein.
- **QFL (Quantity Following Line):** jis chhoti base candle se bada impulse shuru hua,
  uski origin line par price ka retest + hold. Confirmation point.
- **QB (Quantity Box):** usi origin ka demand/supply box — price box ke andar aakar
  direction mein close ho. Confirmation point.
- QFL/QB ka combined test (45 din, train + out-of-sample): `QFL_REQUIRE=1` par OOS
  win-rate **63.8%** (194 signals, +0.25R) vs **62.7%** (567 signals) inke bagair.
  Train half mein bhi behtar (60.9% vs 55.2%) — yani sirf ek period ki tareef nahi.
  Is liye **default ab `1` hai**; zyada signals chahiye to `QFL_REQUIRE=0` karein.
- In sab ka score hai; `MMC_MIN_POINTS` sirf **core** MMC points (BOS/CHoCH, FVG,
  sweep, discount/premium) par lagta hai. QFL/QB sirf confirmation points hain,
  inke dum par weak setup pass nahi hota.
- **Displacement candle** aur **order block** bhi test kiye gaye, lekin 45-din data mein
  unka koi measurable edge nahi mila — isliye score se hata diye (README ke end mein
  measurement details hain).

**Entry timing (15m)**
- Pullback hokar EMA20 reclaim (LONG) ya rally hokar EMA20 se reject (SHORT).
- MACD histogram signal ki direction mein aur momentum build ho rahi ho.
- RSI healthy zone mein (overbought/oversold chase nahi).
- Volume 20-bar average ka >= 1.2x.
- Pichle 3 candles mein 3.5 ATR se zyada ka move ho to skip (pump chase nahi).

**BTC filter**
- BTC 1h bearish ho to LONG nahi; BTC 1h bullish ho to SHORT nahi.

**Hard filters (signal reject)**
- ATR% 0.25% se kam (dead market) ya 3% se zyada (crazy volatility).
- Stop loss 0.5% se tight ya 3% se wide.
- RSI15 > 75 (LONG) / < 25 (SHORT) = overextended.

**Risk / levels**
- Stop = recent 20-candle swing + 0.5 ATR buffer (kam se kam 1.2 ATR door).
- TP1 = 1R, TP2 = 2R, TP3 = 3R.
- Suggested management: TP1 par 50% book karein, SL breakeven par le aayein, baaki TP2 tak.

**Guards**
- Ek coin par 4 ghante mein dobara signal nahi (cooldown).
- Din mein max 6 signals, ek run mein max 2, ek direction mein max 2
  (taake market dump mein 6 correlated shorts na aayein).

---

## 3. Telegram bot setup (5 minute)

1. Telegram par **@BotFather** ko message karein → `/newbot` → naam + username do.
2. BotFather **token** dega (`123456:ABC...`). Isay copy karein.
3. Apne bot ko Telegram par search karein aur **/start** dabayein.
4. Chat ID nikalne ke liye browser mein kholen:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   `"chat":{"id":123456789,...}` — yehi `TELEGRAM_CHAT_ID` hai.
   (Group ke liye bot ko group mein add karein, phir wahi URL check karein — id negative hogi.)

---

## 4. Local test (laptop par)

**Windows:** folder mein `run.bat` par double click.

Ya command line se:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
notepad .env          # token + chat id daalein
.venv\Scripts\python -m agent.main
```

Sirf logic test karna ho (Telegram par kuch na jaye) to `.env` mein `DRY_RUN=1` rakhein.

Backtest (past data par win-rate):

```bash
.venv\Scripts\python scripts/backtest.py --days 30
```

Multiple configs ka comparison with out-of-sample (train/OOS) check:

```bash
.venv\Scripts\python scripts/tune.py --days 45
```

---

## 5. Cloud deploy — GitHub Actions (free, laptop band ho to bhi chalta hai)

1. GitHub par **private** repository banayein aur ye folder push karein.
2. Repo → **Settings → Secrets and variables → Actions → Secrets**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. (Optional) **Variables** tab mein: `EQUITY_USDT`, `RISK_PER_TRADE_PCT`, `MIN_SCORE`.
4. **Actions** tab → *Crypto Signal Agent* → **Enable workflow**.
5. Test: *Run workflow* dabayein. 1–2 minute mein Telegram par message aana chahiye.

Workflow har 15 min par chalta hai (`.github/workflows/signals.yml`) aur
`data/journal.json` ko repo mein commit karta hai — is se history aur stats save rehte hain.

**Zaroori notes**
- GitHub cron kabhi 2–10 minute late chal sakta hai — normal hai.
- Repo 60 din bilkul inactive ho to GitHub schedule band kar deta hai. Journal commit
  khud activity create karta hai, phir bhi mahine mein ek baar Actions tab check kar lein.
- Binance kuch countries mein block hai. Code 5 different Binance hosts try karta hai
  (`data-api.binance.vision` pehle). Sab fail hon to log mein error dikhega.
- **CRO Binance par listed nahi hai**, is liye CRO ka data automatically MEXC
  (Binance-compatible API) se aata hai. Baaki 9 coins Binance se.
- Journal commit ke liye workflow ko `contents: write` permission chahiye (already set).

---

## 6. Settings (`.env` ya GitHub Variables)

| Variable | Default | Matlab |
|---|---|---|
| `MIN_SCORE` | 8 | Core rules (9) mein se kitne match chahiye |
| `MMC_FILTER` | 1 | 1 = MMC confluence zaroori, 0 = off |
| `MMC_MIN_POINTS` | 1 | Core MMC points ka minimum (BOS/CHoCH 3, FVG 2, sweep 1, discount 1) |
| `QFL_FILTER` / `QB_FILTER` | 1 / 1 | QFL/QB confirmation points on/off |
| `QFL_REQUIRE` | 1 | 1 = har signal par QFL ya QB zaroori (kam signals, behtar win-rate) |
| `CCP_FILTER` | 1 | CcP strong candle (engulfing/rejection) confirmation |
| `ROS_FILTER` | 0 | 1 = opposite 1h swing paas ho to trade skip (room check) |
| `HTF_FILTER` | 1 | 1 = 4h trend same direction mein hona chahiye |
| `NEWS_ENABLED` | 1 | 1 = Hinglish news digest Telegram par |
| `NEWS_INTERVAL_HOURS` | 1 | Kitne ghante mein ek news digest |
| `NEWS_LOOKBACK_HOURS` | 24 | Kitne ghante purani news tak include ho |
| `NEWS_MAX_CRYPTO` / `NEWS_MAX_MACRO` | 4 / 3 | Crypto aur forex/macro items ki limit |
| `TRADE_JOURNAL_PATH` | data/trade_journal.json | Aap ki personal P&L journal ka file |
| `MAX_SIGNALS_PER_DAY` | 6 | Roz max signals |
| `MAX_NEW_PER_RUN` | 2 | Ek scan (15 min) mein max naye signals |
| `MAX_PER_SIDE_PER_RUN` | 2 | Ek direction (LONG/SHORT) mein max signals per scan |
| `COOLDOWN_HOURS` | 4 | Same coin par dobara signal ka gap |
| `BTC_FILTER` | 1 | BTC ke against trade block |
| `BTC_STRICT` | 0 | 1 = sirf BTC ke saath aligned trades |
| `EQUITY_USDT` | 100 | Position size calculate karne ke liye (optional) |
| `RISK_PER_TRADE_PCT` | 1 | Per trade risk % |
| `STOP_PAD_ATR` / `MIN_STOP_ATR` | 0.5 / 1.2 | Stop loss swing ke neeche kitna ATR buffer |
| `MIN_RISK_PCT` / `MAX_RISK_PCT` | 0.5 / 3.0 | Stop distance ki allowed range |
| `MAX_HOLD_HOURS` | 72 | Itne ghante mein TP/SL na lage to time-exit |
| `DRY_RUN` | 0 | 1 = Telegram par bhejne ke bajaye print |

Tuning ke baad `scripts/tune.py` ki OOS win-rate dekh kar `MIN_SCORE` adjust karein.

### Backtest results (last 30 days, 10 coins, Nov 2026) — final config (`QFL_REQUIRE=1`)

| Coin | Signals | Win rate | Avg R |
|---|---|---|---|
| CRO | 18 | 76.5% | +0.54 |
| SHIB | 21 | 75.0% | +0.59 |
| DOT | 15 | 73.3% | +0.17 |
| HBAR | 23 | 72.7% | +0.43 |
| PEPE | 3 | 66.7% | +0.00 |
| ADA | 20 | 65.0% | +0.23 |
| XLM | 21 | 57.1% | +0.14 |
| VET | 18 | 55.6% | +0.22 |
| DOGE | 18 | 50.0% | +0.03 |
| TRX | 1 | 100.0% | +1.50 |
| **TOTAL** | **158** | **65.8%** | **+0.30** |

- Win = TP1 hit before SL (management: 50% at TP1, SL→breakeven, rest at TP2).
- Break-even win rate is model mein 51% hai (avg win +0.97R). Fees/slippage
  (~0.1% per side) include nahi hain — real number is se thora kam hoga.
- **Out-of-sample check (45 din, train/OOS split):** final config **63.8% OOS**
  (194 signals, +0.25R), train half 60.9%. Isi system ka purana, bina-QFL version
  **62.7% OOS** (567 signals, +0.18R), train 55.2%. Yani nayi filter dono halves
  mein better hai — 4 guna kam signals ke saath.
- **Caveat:** is month mein 156 SHORT vs 2 LONG aaye — market bearish tha. Trend-following
  system sirf ek regime mein test hua hai. LONG side ka sample itna chhota hai ke us par
  bharosa na karein.
- Chhote sample (TRX 1, PEPE 3) par bharosa na karein.

**Har MMC rule ka alag measurement (45 din, 770 baseline signals, win rate 59.2%):**

| Rule | Is rule ke saath | Iske bina | Faisla |
|---|---|---|---|
| BOS/CHoCH (structure break) | 65.0% | 57.8% | score +3 |
| FVG rebalance | 60.6% | 59.1% | score +2 |
| Liquidity sweep | 62.5% | 58.9% | score +1 |
| Premium/discount zone | 64.8% | 53.9% | score +1 |
| 4h trend alignment | 60.6% | 56.0% | hard filter |
| Displacement candle | 63.6% | 63.1% | edge nahi — hata diya |
| Order block | 62.1% | 63.5% | edge nahi — hata diya |
| QFL + QB (AND-gate, `QFL_REQUIRE=1`) | 63.8% (OOS) | 62.7% (core gate) | **default hard filter** |

**Accuracy tuning grid (45 din, OOS par focus — `scripts/tune.py` se reproduce hota hai):**

| Config | Signals | Train WR | OOS WR | Avg R |
|---|---|---|---|---|
| `QFL_REQUIRE=1` (final default) | 194 | 60.9% | **63.8%** | +0.25 |
| Purana default (core gate) | 567 | 55.2% | 62.7% | +0.18 |
| `QFL_REQUIRE=1` + `BTC_STRICT=1` | 187 | 60.7% | 63.5% | +0.25 |
| `QFL_REQUIRE=1` + `ROS_FILTER=1` | 114 | 54.8% | 63.9% | +0.16 |
| `MIN_SCORE=7` + `QFL_REQUIRE=1` | 339 | 58.9% | 60.9% | +0.22 |

- `ROS_FILTER=1` (opposite swing ki room) se 80 signals kam ho gaye lekin win-rate sirf
  0.1 point barha — is liye default `0`. Wajah: room check bahut se A+ setups bhi kaat deta hai.
- `BTC_STRICT=1` se farq na hone ke barabar (63.5% vs 63.8%) — default `0`.
- `MIN_SCORE=9` + require: 66 signals, train 63.6% **magar OOS 56.8%** — yeh classic
  overfitting hai (train par achha, naye data par kharab). Isi liye strict karne ke bajaye
  `MIN_SCORE=8` / `MMC_MIN_POINTS=1` rakha gaya.
- `MMC_MIN_POINTS=2` + require: sirf 28 signals, OOS 57.9% — sample itna chhota ke
  faisla nahi ho sakta, aur number behtar bhi nahi.
- 194 signals par 63.8% ka matlab ±5 point ka error margin (statistics). Is liye hum
  70%+ ka dawa nahi karte.
- QB akela requirement rakhne par OOS 56.9% aaya (76 signals) — isliye QB ko hard gate
  banane ke bajaye "QFL **ya** QB" rakha gaya.

Apna khud ka number dekhna ho to: `.venv\Scripts\python scripts/backtest.py --days 30`

---

## 7. Signal ka format

```
🔴 SHORT — Cardano (ADA)
📍 Entry: 0.45210
🛑 Stop:  0.43800  (-3.10%)
🎯 TP1: 0.43800 (1R) ...
🧠 Confidence: 72% (13/18 rules)
📊 15m RSI 47 | Volume 1.3x
✅ Reasons: ...
```

`Confidence` = kitne rules match hue (core 9 + MMC max 9 = 18). Ye probability nahi,
sirf rule-count hai.

---

## 8. News digest (Hinglish) — naya

Agent har `NEWS_INTERVAL_HOURS` (default **1 ghanta**) par Telegram par ek Hinglish news
digest bhejta hai — crypto, forex aur global markets/macro sab ek message mein.
Agent khud interval sambhalta hai (`data/journal.json` mein `last_news_at`), is liye
15-minute scan ke bawajood news har 1 ghante par hi aati hai — na kam, na doubar.

- **Sources (public RSS):** Cointelegraph, CoinDesk, Decrypt (crypto); ForexLive (forex);
  CNBC Markets (macro/stocks).
- **Format:** har item ki Hinglish line (topic + event + bullish/bearish), neeche original
  English headline aur link — taake translation par andha bharosa na karein.
- **Hinglish rule-based hai**, AI translation nahi. Keyword map se banti hai
  (ETF, rate cut, hack, inflation, record high etc.). Isi liye English headline saath aata hai.
- **Duplicate / purani news nahi:** title-hash se dedupe, `NEWS_LOOKBACK_HOURS` window,
  aur journal mein `news_seen` list save hoti hai.
- Weekend par forex/macro feeds slow hote hain (market band) — crypto items tab bhi aate hain.

Sample:

```
🪙 CRYPTO
• Bitcoin: ETF, paisa andar aaya, record high — bullish 🟢
  EN: Bitcoin ETF sees record inflows as price hits new high
  CoinDesk — https://www.coindesk.com/...
```

Band karna ho to `.env` mein `NEWS_ENABLED=0`.

---

## 9. Apni personal P&L journal (Telegram par hi)

Agent ka apna journal (`data/journal.json`) signals ki history rakhta hai. Uske alawa ek
**alag personal journal** hai (`data/trade_journal.json`) jisme aap apne asli profit/loss
likh sakte hain — sab kuch **Telegram par hi**, koi website ya Excel nahi.

Bot ko message karein (sirf aap ki chat ID accept hoti hai, baaki logon ke messages
ignore ho jate hain):

| Command | Kaam |
|---|---|
| `/add LONG DOGE +2.5 TP2 hit` | naya trade add (LONG/SHORT, % ya USDT) |
| `/list` | aakhri 10 trades |
| `/stats` | total trades, win-rate, net %, average, best/worst |
| `/del 3` | 3 number wali entry delete |
| `/help` | commands ki list |

Number ka format:
- `+2.5` = 2.5% profit, `-1` = 1% loss
- `2.5` (plus ke bagair) bhi chalta hai; `%` aur `R` laga dein to bhi chalega (`+2.5%`)
- Entry hamesha **percent** mein save hoti hai, is liye stats sab trades ko barabar
  compare kar sakta hai (account size badalne se number kharab nahi hota)

Kaam kaise karta hai:
- Agent har 15-minute scan mein pehle Telegram commands check karta hai, phir signal
  scan karta hai.
- **Turant reply** chahiye (25 second ke andar, scan ka intezaar nahi) to laptop par
  `run_journal.bat` double-click karein ya:
  ```bash
  .venv\Scripts\python scripts/trade_bot.py
  ```
  Ye sirf journal commands sunta hai, trading se koi taluq nahi.
- Reply foran Telegram par aata hai aur `data/trade_journal.json` mein save hota hai.
  GitHub Actions par bhi ye file roz commit hoti hai, is liye data zaya nahi hota.
- **Ek waqt mein ek hi jagah likhein:** agar cloud (GitHub) par agent chal raha hai to
  rozana ka `/add` wahi se karein — laptop wala `run_journal.bat` sirf tab chalayein jab
  cloud band ho, warna dono ki copy alag ho sakti hai.
- Telegram ko "safe place" samajhne ki ek wajah: message aap ke apne bot ke through
  jaata hai, koi third-party app install nahi karni parti.

Sample reply:

```
✅ Trade add ho gaya #7: LONG DOGE +2.50%
━━━━━━━━━━━━━━━━
Trades: 7 | Win: 5 | Loss: 2
Net: +8.40% | Avg: +1.20%
Win rate: 71.4%
Best: +4.10% | Worst: -1.00%
```

---

## 10. Structure

```
agent/
  config.py      settings (.env)
  data.py        Binance klines (free public API)
  indicators.py  EMA / RSI / MACD / ATR / volume / 4h trend
  strategy.py    multi-timeframe rules -> LONG/SHORT decision
  mmc.py         MMC detectors (BOS/CHoCH, FVG, sweep, discount/premium, QFL, QB, CcP, ROS)
  news.py        crypto + forex + macro RSS -> Hinglish digest
  trade_journal.py  Telegram commands se aap ki personal P&L journal
  risk.py        SL/TP + position size
  outcomes.py    trade management simulation (TP1 50%, SL->BE, TP2)
  tracker.py     open signals ka result update
  journal.py     data/journal.json (history + stats)
  notifier.py    Telegram message
  main.py        ek scan cycle (commands -> news -> signals)
scripts/
  backtest.py    past data par win-rate
  tune.py        config comparison + out-of-sample
  trade_bot.py   sirf journal commands sunne wala instant bot
```

---

## 11. PDF rules integrate karna

Jab aap apne rules PDF mein dein, in files mein change hoga:

- `agent/strategy.py` → scoring conditions (trend, entry, filters)
- `agent/risk.py` → SL/TP logic
- `agent/config.py` → naye thresholds
- Phir `scripts/tune.py` chala kar win-rate compare karenge (purane vs naye rules).

---

## 12. Disclaimer

Ye project educational hai, financial advice nahi. Crypto mein capital loss ka pura risk hai.
Pehle paper-trade ya minimum size se test karein. Past backtest future returns guarantee nahi karta.
