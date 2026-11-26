#!/usr/bin/env python3
"""프로젝트PM 발행 현황판 빌드.

channels.json의 각 채널 피드(RSS, 사이트맵)를 읽어 날짜별 발행 여부를 판정하고
정적 index.html 한 장을 만든다. 표준 라이브러리만 사용한다.

사용법:
    python build.py --out build            # 실제 피드 확인
    python build.py --out build --sample   # 피드 대신 예시 데이터(화면 점검용)
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import random
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (compatible; pm-dashboard/1.0)"
PAST_DAYS = 10   # 오늘 포함 과거 표시 일수
FUTURE_DAYS = 3  # 앞으로 표시 일수
WEEK = "월화수목금토일"

STATUS = {
    "done":    ("완료", "✓"),
    "miss":    ("누락", "✕"),
    "wait":    ("대기", "◷"),
    "plan":    ("예정", "○"),
    "off":     ("쉬는 날", "·"),
    "unknown": ("기록 범위 밖", "?"),
    "error":   ("확인 실패", "!"),
    "manual":  ("수동 관리", "–"),
}


# ---------- 피드 읽기 ----------

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), {k.lower(): v for k, v in r.headers.items()}


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    d = None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
            if m:
                d = dt.datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=KST)
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return d.astimezone(KST)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(data):
    """RSS 2.0과 Atom을 모두 읽는다."""
    posts = []
    for el in ET.fromstring(data).iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = link = date = None
        for c in el:
            n = _local(c.tag)
            if n == "title":
                title = html.unescape(html.unescape((c.text or "").strip()))
            elif n == "link":
                href = c.get("href")
                if href:
                    if c.get("rel", "alternate") == "alternate":
                        link = href
                elif c.text:
                    link = c.text.strip()
            elif n in ("pubDate", "published", "date") and date is None:
                date = parse_date(c.text)
            elif n == "updated" and date is None:
                date = parse_date(c.text)
        if date:
            posts.append({"title": title or "(제목 없음)", "url": link or "", "at": date})
    return posts


def parse_sitemap(data):
    out = []
    for el in ET.fromstring(data).iter():
        if _local(el.tag) != "url":
            continue
        loc = lm = None
        date_only = False
        for c in el:
            n = _local(c.tag)
            if n == "loc":
                loc = (c.text or "").strip()
            elif n == "lastmod":
                lm = parse_date(c.text)
                date_only = len((c.text or "").strip()) == 10
        if lm:
            out.append({"title": loc, "url": loc, "at": lm, "date_only": date_only})
    return out


def check_channel(ch):
    c = ch.get("check", {})
    kind = c.get("type", "manual")
    res = {"ok": False, "manual": kind == "manual", "error": "", "posts": []}
    if res["manual"]:
        res["ok"] = True
        return res
    try:
        if kind == "rss":
            data, headers = fetch(c["url"])
            res["posts"] = parse_feed(data)
            if not res["posts"]:
                # 글이 하나도 없는 피드는 RSS 비공개·공개 글 없음일 가능성이 높아 누락 대신 확인 실패로 본다
                raise ValueError("피드가 비어 있음 — 블로그의 RSS 공개 설정이나 공개 글 여부 확인 필요")
        elif kind == "site":
            posts = []
            if c.get("sitemap"):
                try:
                    data, _ = fetch(c["sitemap"])
                    posts = parse_sitemap(data)
                except Exception:  # 사이트맵이 없으면 Last-Modified로 대신한다
                    posts = []
            if not posts and c.get("page"):
                _, headers = fetch(c["page"])
                lm = parse_date(headers.get("last-modified"))
                if lm:
                    posts = [{"title": "사이트 갱신", "url": c["page"], "at": lm}]
            by_day = {}
            for p in posts:
                k = p["at"].date()
                if k not in by_day or p["at"] > by_day[k]["at"]:
                    by_day[k] = p
            page = c.get("page") or ch.get("url", "")
            res["posts"] = [{"title": "사이트 갱신", "url": page, "at": p["at"],
                             "date_only": p.get("date_only", False)} for p in by_day.values()]
        else:
            raise ValueError(f"알 수 없는 확인 방식: {kind}")
        res["ok"] = True
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"[:200]
    res["posts"].sort(key=lambda p: p["at"], reverse=True)
    return res


def sample_result(ch, now):
    """화면 점검용 예시 데이터."""
    if ch.get("check", {}).get("type") == "manual":
        return {"ok": True, "manual": True, "error": "", "posts": []}
    rnd = random.Random(ch["id"])
    posts = []
    for i in range(PAST_DAYS):
        day = now - dt.timedelta(days=i)
        if i == 0 and ch["id"] == "blogger":
            continue  # 오늘 누락 예시
        if i > 0 and rnd.random() < 0.15:
            continue  # 과거 누락 예시
        at = day.replace(hour=rnd.choice([6, 7, 8]), minute=rnd.randint(0, 59))
        if at <= now:
            posts.append({"title": f"(예시) {ch['name']} {at:%m/%d} 글", "url": ch.get("url", ""), "at": at})
    return {"ok": True, "manual": False, "error": "", "posts": posts}


# ---------- 판정 ----------

def expected_on(ch, day):
    cyc = ch.get("cycle", "none")
    if cyc == "daily":
        return True
    if isinstance(cyc, list):  # 요일 목록, 월=0 … 일=6
        return day.weekday() in cyc
    return False


def day_status(ch, res, day, now):
    if res["manual"]:
        return "manual"
    if not res["ok"]:
        return "error"
    if any(p["at"].date() == day for p in res["posts"]):
        return "done"
    if day > now.date():
        return "plan" if expected_on(ch, day) else "off"
    if not expected_on(ch, day):
        return "off"
    if day == now.date():
        h, m = map(int, ch.get("due", "10:00").split(":"))
        due = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return "wait" if now < due else "miss"
    if res["posts"] and day < res["posts"][-1]["at"].date():
        return "unknown"  # 피드에 남아 있는 기간보다 이전
    return "miss"


# ---------- 화면 ----------

def e(s):
    return html.escape(str(s), quote=True)


def safe_url(u):
    return u if isinstance(u, str) and u.startswith(("https://", "http://")) else ""


def fmt_dt(d, date_only=False):
    return f"{d:%m/%d} ({WEEK[d.weekday()]})" + ("" if date_only else f" {d:%H:%M}")


def badge(st):
    label, icon = STATUS[st]
    return f'<span class="b b-{st}"><span aria-hidden="true">{icon}</span> {label}</span>'


def render(channels, results, now):
    today = now.date()
    days = [today + dt.timedelta(days=i) for i in range(-(PAST_DAYS - 1), FUTURE_DAYS + 1)]
    auto = [c for c in channels if not results[c["id"]]["manual"]]

    today_st = {c["id"]: day_status(c, results[c["id"]], today, now) for c in channels}
    due_today = [c for c in auto if expected_on(c, today)]
    done_today = [c for c in due_today if today_st[c["id"]] == "done"]
    week = [today - dt.timedelta(days=i) for i in range(7)]
    misses7 = sum(1 for c in auto for d in week if day_status(c, results[c["id"]], d, now) == "miss")
    errors = [c for c in auto if not results[c["id"]]["ok"]]
    posts7 = sum(1 for c in auto for p in results[c["id"]]["posts"] if p["at"].date() >= week[-1])

    # 한 줄 요약
    problems = [c["name"] for c in due_today if today_st[c["id"]] in ("miss", "error")]
    waiting = [c["name"] for c in due_today if today_st[c["id"]] == "wait"]
    if problems:
        lede = f"오늘 {len(due_today)}개 채널 중 {len(done_today)}개 발행 완료. 확인 필요: {', '.join(problems)}."
    elif waiting:
        lede = f"오늘 {len(due_today)}개 채널 중 {len(done_today)}개 발행 완료, {len(waiting)}개는 마감 시각 전입니다."
    elif due_today:
        lede = f"오늘 예정된 {len(due_today)}개 채널이 모두 발행됐습니다."
    else:
        lede = "오늘 예정된 자동 발행이 없습니다."
    lede_cls = "bad" if problems else ("warn" if waiting else "ok")

    # KPI
    kpis = [
        ("오늘 발행", f"{len(done_today)}<small>/{len(due_today)}</small>", "예정 채널 중 완료"),
        ("최근 7일 누락", str(misses7), "예정일에 글이 없던 횟수"),
        ("최근 7일 발행", str(posts7), "자동 확인 채널 합계"),
        ("확인 실패", str(len(errors)), "피드를 읽지 못한 채널"),
    ]
    kpi_html = "".join(
        f'<div class="card kpi{" alert" if (i in (1, 3) and v != "0") else ""}">'
        f'<div class="k-label">{e(l)}</div><div class="k-val">{v}</div><div class="k-sub">{e(s)}</div></div>'
        for i, (l, v, s) in enumerate(kpis)
    )

    # 채널 카드
    cards = []
    for c in channels:
        r = results[c["id"]]
        st = today_st[c["id"]]
        url = safe_url(c.get("url", ""))
        name = f'<a href="{e(url)}" target="_blank" rel="noopener">{e(c["name"])}</a>' if url else e(c["name"])
        lines = []
        if r["manual"]:
            lines.append(f'<div class="row"><span>상태</span><b>{e(c.get("note", "수동 관리"))}</b></div>')
        else:
            last = r["posts"][0] if r["posts"] else None
            if last:
                lu = safe_url(last["url"])
                t = e(last["title"])
                t = f'<a href="{e(lu)}" target="_blank" rel="noopener">{t}</a>' if lu else t
                lines.append(f'<div class="row"><span>최근</span><b>{fmt_dt(last["at"], last.get("date_only"))}</b></div>')
                lines.append(f'<div class="last">{t}</div>')
            else:
                lines.append('<div class="row"><span>최근</span><b>기록 없음</b></div>')
            if r["error"]:
                lines.append(f'<div class="err">피드 오류: {e(r["error"])}</div>')
            if expected_on(c, today):
                lines.append(f'<div class="row"><span>마감</span><b>{e(c.get("due", "10:00"))}</b></div>')
        cards.append(
            f'<article class="card ch st-{st}">'
            f'<header><div><div class="ch-name">{name}</div>'
            f'<div class="ch-meta">{e(c.get("platform", ""))} · {e(c.get("cycle_label", ""))}</div></div>'
            f'{badge(st)}</header>{"".join(lines)}</article>'
        )

    # 날짜별 그리드
    head = "".join(
        f'<th class="{"today" if d == today else ""}{" wkend" if d.weekday() >= 5 else ""}">'
        f'{d.day}<br><span>{WEEK[d.weekday()]}</span></th>'
        for d in days
    )
    body = []
    for c in channels:
        r = results[c["id"]]
        cells = []
        for d in days:
            st = day_status(c, r, d, now)
            label, icon = STATUS[st]
            n = sum(1 for p in r["posts"] if p["at"].date() == d)
            txt = icon if not (st == "done" and n > 1) else str(n)
            cells.append(f'<td class="g g-{st}{" today" if d == today else ""}" '
                         f'aria-label="{d:%m월 %d일} {label}{f" {n}건" if n else ""}">{txt}</td>')
        body.append(f'<tr><th scope="row">{e(c["name"])}</th>{"".join(cells)}</tr>')
    legend = "".join(f'<span class="lg g-{k}">{v[1]}</span> {v[0]}' for k, v in STATUS.items()
                     if k not in ("manual",))

    # 최근 발행 목록
    recent = []
    for c in auto:
        for p in results[c["id"]]["posts"]:
            if p["at"].date() >= days[0]:
                recent.append((p["at"], c, p))
    recent.sort(key=lambda x: x[0], reverse=True)
    rows = []
    for at, c, p in recent[:20]:
        lu = safe_url(p["url"])
        t = e(p["title"])
        t = f'<a href="{e(lu)}" target="_blank" rel="noopener">{t}</a>' if lu else t
        rows.append(f'<tr><td class="nowrap">{fmt_dt(at, p.get("date_only"))}</td><td class="nowrap">{e(c["name"])}</td><td>{t}</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="3" class="empty">표시할 발행 기록이 없습니다.</td></tr>')

    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    return (tpl
            .replace("{{UPDATED}}", f"{now:%Y-%m-%d %H:%M} KST")
            .replace("{{LEDE}}", e(lede))
            .replace("{{LEDE_CLS}}", lede_cls)
            .replace("{{KPIS}}", kpi_html)
            .replace("{{CARDS}}", "".join(cards))
            .replace("{{GRID_HEAD}}", head)
            .replace("{{GRID_BODY}}", "".join(body))
            .replace("{{LEGEND}}", legend)
            .replace("{{RECENT}}", "".join(rows)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build")
    ap.add_argument("--sample", action="store_true", help="피드 대신 예시 데이터 사용")
    args = ap.parse_args()

    now = dt.datetime.now(KST)
    channels = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
    results = {}
    for ch in channels:
        results[ch["id"]] = sample_result(ch, now) if args.sample else check_channel(ch)
        r = results[ch["id"]]
        print(f"[{ch['id']}] ok={r['ok']} posts={len(r['posts'])} {r['error']}")

    today_posts = sorted(
        ((p["at"], ch["name"], p["title"], p["url"], p.get("date_only")) for ch in channels
         for p in results[ch["id"]]["posts"] if p["at"].date() == now.date()),
        key=lambda x: x[0])
    print(f"오늘 발행 {len(today_posts)}건")
    for at, name, title, url, date_only in today_posts:
        print(f"TODAY|{'시각 미상' if date_only else f'{at:%H:%M}'}|{name}|{title}|{url}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(channels, results, now), encoding="utf-8")
    print(f"완료: {out / 'index.html'}")


if __name__ == "__main__":
    main()
