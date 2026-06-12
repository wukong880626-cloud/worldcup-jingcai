#!/usr/bin/env python3
"""每日自动更新 2026 世界杯赛果 → data.js
数据源：ESPN 公开比分接口（site.api.espn.com，无需 key）
- 小组赛(id 1-72)：按队伍对匹配，回填 result/score
- 淘汰赛(id 73-104)：对阵公布后回填对阵/北京时间/球场，完赛后回填结果
- result 取 90 分钟+补时常规结果（加时/点球场次按 90' 比分判 H/D/A，比分加注）
"""
import json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
DATA = ROOT + "/data.js"
API = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={}"

BJ = timezone(timedelta(hours=8))
ET = timezone(timedelta(hours=-4))  # 6-7月为美东夏令时

NAME2CODE = {
    "Mexico":"MEX","South Africa":"RSA","South Korea":"KOR","Korea Republic":"KOR","Czechia":"CZE","Czech Republic":"CZE",
    "Canada":"CAN","Bosnia and Herzegovina":"BIH","Qatar":"QAT","Switzerland":"SUI",
    "Brazil":"BRA","Morocco":"MAR","Haiti":"HAI","Scotland":"SCO",
    "United States":"USA","USA":"USA","Paraguay":"PAR","Australia":"AUS","Turkiye":"TUR","Türkiye":"TUR","Turkey":"TUR",
    "Germany":"GER","Curacao":"CUW","Curaçao":"CUW","Ivory Coast":"CIV","Côte d'Ivoire":"CIV","Ecuador":"ECU",
    "Netherlands":"NED","Japan":"JPN","Sweden":"SWE","Tunisia":"TUN",
    "Belgium":"BEL","Egypt":"EGY","Iran":"IRN","New Zealand":"NZL",
    "Spain":"ESP","Cape Verde":"CPV","Cabo Verde":"CPV","Saudi Arabia":"KSA","Uruguay":"URU",
    "France":"FRA","Senegal":"SEN","Iraq":"IRQ","Norway":"NOR",
    "Argentina":"ARG","Algeria":"ALG","Austria":"AUT","Jordan":"JOR",
    "Portugal":"POR","DR Congo":"COD","Congo DR":"COD","Democratic Republic of the Congo":"COD",
    "Uzbekistan":"UZB","Colombia":"COL",
    "England":"ENG","Croatia":"CRO","Ghana":"GHA","Panama":"PAN",
}
CITY_CN = {
    "Mexico City":"墨西哥城","Zapopan":"瓜达拉哈拉","Guadalajara":"瓜达拉哈拉",
    "Toronto":"多伦多","Vancouver":"温哥华",
    "Los Angeles":"洛杉矶","Inglewood":"洛杉矶","Pasadena":"洛杉矶",
    "San Francisco":"旧金山","Santa Clara":"旧金山",
    "East Rutherford":"纽约/新泽西","New York":"纽约/新泽西","New Jersey":"纽约/新泽西",
    "Boston":"波士顿","Foxborough":"波士顿",
    "Houston":"休斯敦","Dallas":"达拉斯","Arlington":"达拉斯",
    "Philadelphia":"费城","Guadalupe":"蒙特雷","Monterrey":"蒙特雷",
    "Atlanta":"亚特兰大","Miami":"迈阿密","Miami Gardens":"迈阿密",
    "Kansas City":"堪萨斯城","Seattle":"西雅图",
}

def stage_of(et_date):
    d = et_date.strftime("%m%d")
    if d <= "0627": return "group"
    if d <= "0703": return "r32"
    if d <= "0708": return "r16"
    if d <= "0712": return "qf"
    if d <= "0716": return "sf"
    if d <= "0718": return "third"
    return "final"

def fetch(date_str):
    try:
        with urllib.request.urlopen(API.format(date_str), timeout=30) as r:
            return json.load(r).get("events", [])
    except Exception as e:
        print(f"  ! fetch {date_str} failed: {e}", file=sys.stderr)
        return []

def team_code(comp):
    name = comp["team"].get("displayName", "")
    if name.upper() in ("TBD", "TBA") or comp["team"].get("shortDisplayName","").upper() in ("TBD","TBA"):
        return None
    return NAME2CODE.get(name)

def reg_goals(comp):
    """90分钟常规进球数：linescores 前两节之和；取不到返回 None"""
    ls = comp.get("linescores") or []
    if len(ls) >= 2:
        try: return int(ls[0]["value"]) + int(ls[1]["value"])
        except Exception: return None
    return None

def main():
    src = open(DATA, encoding="utf-8").read()
    payload = json.loads(re.sub(r"^window\.WC_DATA\s*=\s*|;\s*$", "", src.strip()))
    matches = payload["matches"]
    by_pair = {frozenset((m["home"], m["away"])): m for m in matches if m["stage"] == "group"}
    kos = [m for m in matches if m["stage"] != "group"]
    by_espn = {m["espnId"]: m for m in kos if m.get("espnId")}

    now_et = datetime.now(ET)
    start = datetime(2026, 6, 11, tzinfo=ET)
    end = min(now_et, datetime(2026, 7, 19, 23, 59, tzinfo=ET))
    changed, day = [], start
    while day <= end:
        for ev in fetch(day.strftime("%Y%m%d")):
            c = ev["competitions"][0]
            comps = {x["homeAway"]: x for x in c["competitors"]}
            h, a = comps.get("home"), comps.get("away")
            if not h or not a: continue
            hc, ac = team_code(h), team_code(a)
            ko_utc = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            et_date = ko_utc.astimezone(ET)
            done = ev["status"]["type"].get("completed", False)

            if stage_of(et_date) == "group":
                if not (hc and ac): continue
                m = by_pair.get(frozenset((hc, ac)))
                if not m or not done or m.get("result"): continue
                hg, ag = int(h.get("score", 0)), int(a.get("score", 0))
                if m["home"] != hc: hg, ag = ag, hg          # 比分对齐到我方主队
                m["result"] = "H" if hg > ag else ("A" if hg < ag else "D")
                m["score"] = f"{hg}-{ag}"
                changed.append(f'{m["home"]} {m["score"]} {m["away"]}')
            else:
                eid = ev.get("id")
                m = by_espn.get(eid)
                if not m:  # 占该阶段第一个空位
                    st = stage_of(et_date)
                    free = [x for x in kos if x["stage"] == st and not x.get("espnId")]
                    if not free: continue
                    m = free[0]; m["espnId"] = eid; by_espn[eid] = m
                bj = ko_utc.astimezone(BJ)
                m["date"], m["t"] = bj.strftime("%Y-%m-%d"), bj.strftime("%H:%M")
                m["home"], m["away"] = hc, ac
                city = (c.get("venue", {}).get("address", {}) or {}).get("city", "")
                m["venue"] = CITY_CN.get(city, m.get("venue") or "待定")
                if done and hc and ac and not m.get("result"):
                    hg, ag = int(h.get("score", 0)), int(a.get("score", 0))
                    rh, ra = reg_goals(h), reg_goals(a)
                    so_h, so_a = h.get("shootoutScore"), a.get("shootoutScore")
                    if so_h is not None and so_a is not None:
                        m["result"] = "D"
                        base = f"{rh}-{ra}" if rh is not None else f"{hg}-{ag}"
                        m["score"] = f"{base} (点球{so_h}-{so_a})"
                    elif rh is not None and (rh, ra) != (hg, ag):  # 加时改写了比分
                        m["result"] = "H" if rh > ra else ("A" if rh < ra else "D")
                        m["score"] = f"{hg}-{ag} (加时)"
                    else:
                        m["result"] = "H" if hg > ag else ("A" if hg < ag else "D")
                        m["score"] = f"{hg}-{ag}"
                    changed.append(f'{m["home"]} {m["score"]} {m["away"]}')
                else:
                    changed.append(f'[{m["stage"]}] {hc or "待定"} vs {ac or "待定"} @ {m["date"]} {m["t"]}')
        day += timedelta(days=1)

    payload["updated"] = datetime.now(BJ).isoformat(timespec="seconds")
    out = "window.WC_DATA = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n"
    json.loads(re.sub(r"^window\.WC_DATA\s*=\s*|;\s*$", "", out.strip()))  # 自检
    open(DATA, "w", encoding="utf-8").write(out)
    print("updated entries:" if changed else "no changes", *changed[:40], sep="\n  ")

if __name__ == "__main__":
    main()
