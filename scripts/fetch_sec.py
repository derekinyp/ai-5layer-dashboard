import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

TAIPEI_TZ = timezone(timedelta(hours=8))
SEC_HEADERS = {
    "User-Agent": "DerekLinResearch derekinyp@gmail.com",
    "Accept": "application/json",
}

SEC_COMPANIES = [
    ("MSFT", "L2 雲端", "0000789019"),
    ("GOOGL", "L2 雲端", "0001652044"),
    ("AMZN", "L2 雲端", "0001018724"),
    ("META", "L2 雲端", "0001326801"),
    ("ORCL", "L2 雲端", "0001341439"),
    ("NVDA", "L1 / L3", "0001045810"),
    ("AMD", "L3 晶片", "0000002488"),
    ("AVGO", "L3 晶片", "0001730168"),
    ("MU", "L4 記憶體", "0000723125"),
    ("TSM", "L6 代工", "0001046179"),
    ("AMAT", "L7a 設備", "0000006951"),
    ("LRCX", "L7a 設備", "0000707549"),
    ("KLAC", "L7a 設備", "0000319201"),
    ("ASML", "L7a 設備", "0000937966"),
    ("CRWV", "反射性", "0001769628"),
]

WATCH_FORMS = {"10-K", "10-Q", "8-K", "6-K", "20-F"}


def parse_sec_recent(raw_bytes: bytes, cutoff_date: str) -> str:
    try:
        obj = json.loads(raw_bytes.decode("utf-8"))
        recent = obj.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        if not forms:
            return "JSON 結構無 recent 欄位"
        hits = [
            f"{f}({d})"
            for f, d in zip(forms[:30], dates[:30])
            if d >= cutoff_date and f in WATCH_FORMS
        ]
        if hits:
            return "★ 近10日有新申報：" + ", ".join(hits)
        return f"近10日無新 8-K/6-K/10-Q/10-K（最新：{forms[0]} {dates[0]}）"
    except Exception as e:
        return f"SEC 解析失敗：{e}"


def main():
    now = datetime.now(TAIPEI_TZ)
    now_str = now.strftime("%Y-%m-%d %H:%M")
    date_tag = now.strftime("%Y-%m-%d")
    cutoff_10d = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    os.makedirs("sec_cache", exist_ok=True)
    rows = []

    for ticker, layer, cik in SEC_COMPANIES:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        name = f"SEC EDGAR 申報監控：{ticker}"
        filename = f"sec-{ticker.lower()}-{date_tag}.json"
        req = urllib.request.Request(url, headers=SEC_HEADERS)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                code = resp.getcode()
                raw = resp.read()
        except urllib.error.HTTPError as e:
            code = e.code
            raw = e.read()
        except Exception as e:
            rows.append([now_str, "自動抓取(GH)", layer, name, url, "ERR", "—", "—", f"抓取失敗：{e}"])
            continue

        sha256 = hashlib.sha256(raw).hexdigest()
        if code == 200:
            with open(os.path.join("sec_cache", filename), "wb") as f:
                f.write(raw)
            note = parse_sec_recent(raw, cutoff_10d)
            path = f"GitHub Artifact (sec-cache-{date_tag})/{filename}"
        else:
            note = f"HTTP 非 200（狀態 {code}）"
            path = "—"

        print(f"[{code}] {ticker}: {note}")
        rows.append([now_str, "自動抓取(GH)", layer, name, url, code, path, sha256, note])
        time.sleep(0.25)

    webhook_url = os.environ["GAS_WEBHOOK_URL"]
    token = os.environ["GAS_POST_TOKEN"]
    payload = json.dumps({"token": token, "rows": rows}).encode("utf-8")

    post_req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(post_req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        print("GAS 回應:", body)
        result = json.loads(body)
        if not result.get("ok"):
            raise SystemExit(f"回寫 Google Sheets 失敗：{result}")


if __name__ == "__main__":
    main()
