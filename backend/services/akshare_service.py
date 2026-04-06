"""
股票数据服务 - 使用腾讯财经 API 直接获取数据
"""
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
import pandas as pd
import json
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

# ─── requests 全局超时补丁 ─────────────────────────────────────────────────
# akshare / requests 内部不带 timeout，Windows 代理环境下 SSL 会永远挂住。
# 这里在 akshare_service 导入时立即 patch requests.HTTPAdapter.send，
# 所有后续 requests 调用均自动走禁用代理+默认超时。
try:
    import requests
    _orig_send = requests.adapters.HTTPAdapter.send
    _NO_PROXY = {"http": None, "https": None}
    _EM_HOSTS = ("eastmoney", "qt.gtimg", "sinajs", "ifzq", "10jqka")

    def _patched_send(adapter, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        url = getattr(request, 'url', '') or ''
        if timeout is None and url:
            timeout = 12.0
        if proxies is None and url and any(h in url for h in _EM_HOSTS):
            proxies = _NO_PROXY
            verify = False
        return _orig_send(adapter, request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies)

    requests.adapters.HTTPAdapter.send = _patched_send
    print("[补丁] requests.HTTPAdapter.send: timeout=12s + 禁用代理 for eastmoney")
except Exception as e:
    print(f"[补丁] 注入失败: {e}")

# 创建 HTTP 客户端
_http_client: httpx.AsyncClient | httpx.Client | None = None


def _get_client() -> httpx.Client:
    """获取或创建 HTTP 客户端（禁用代理，直连）"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            trust_env=False,  # 禁用代理，避免代理导致 SSL 超时
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://finance.qq.com/',
                'Accept': '*/*',
            }
        )
    return _http_client


def get_stock_news(limit: int = 10) -> list:
    """
    获取财经新闻列表，按优先级尝试：东方财富快讯 → 同花顺 → 东方财富资讯。
    返回 [{ title, time, url, source, digest }]。
    """
    cache_key = f"stock_news:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # ① 东方财富实时快讯（最及时）
    news = _fetch_em_breaking_news(limit)
    if news:
        _cache_set(cache_key, news, ttl=300)
        print(f"[新闻] 东方财富快讯获取成功，共 {len(news)} 条")
        return news

    # ② 同花顺行业/市场新闻
    news = _fetch_ths_news(limit)
    if news:
        _cache_set(cache_key, news, ttl=300)
        print(f"[新闻] 同花顺获取成功，共 {len(news)} 条")
        return news

    # ③ 东方财富资讯列表兜底
    news = _fetch_em_article_news(limit)
    if news:
        _cache_set(cache_key, news, ttl=300)
        print(f"[新闻] 东方财富资讯获取成功，共 {len(news)} 条")
        return news

    print("[新闻] 所有来源均获取失败")
    return []


def _fetch_em_breaking_news(limit: int) -> list:
    """东方财富实时快讯 API"""
    try:
        client = _get_client()
        url = (
            "https://np-anotice-stock.eastmoney.com/api/security/ann"
            f"?sr=-1&page_size={limit}&page_index=1"
            "&ann_type=A&client_source=web"
            "&fields=title,notice_date,art_code,source"
        )
        resp = client.get(url, timeout=10, headers={"Referer": "https://data.eastmoney.com/"})
        js = resp.json()
        items = (js.get("data") or {}).get("list") or []
        news = []
        for item in items:
            title = str(item.get("title", "") or "").strip()
            if not title:
                continue
            news.append({
                "title": title,
                "time": str(item.get("notice_date", "") or "")[:16],
                "source": "东方财富",
                "url": f"https://data.eastmoney.com/notices/{item.get('art_code', '')}.html",
                "digest": "",
            })
        return news
    except Exception as e:
        print(f"[新闻] 东方财富快讯失败: {e}")
        return []


def _fetch_ths_news(limit: int) -> list:
    """同花顺财经快讯"""
    try:
        client = _get_client()
        url = (
            "https://news.10jqka.com.cn/tapp/news/push/stock/"
            f"?page=1&tag=&track=website&pagesize={limit}"
        )
        resp = client.get(url, timeout=10, headers={"Referer": "https://www.10jqka.com.cn/"})
        js = resp.json()
        items = (js.get("data") or {}).get("list") or []
        news = []
        for item in items:
            title = str(item.get("title", "") or "").strip()
            if not title:
                continue
            news.append({
                "title": title,
                "time": str(item.get("time", "") or "")[:16],
                "source": str(item.get("from", "") or "同花顺").strip() or "同花顺",
                "url": str(item.get("url", "") or ""),
                "digest": str(item.get("summary", "") or "").strip()[:120],
            })
        return news
    except Exception as e:
        print(f"[新闻] 同花顺失败: {e}")
        return []


def _fetch_em_article_news(limit: int) -> list:
    """东方财富资讯列表（兜底）"""
    try:
        client = _get_client()
        url = (
            "https://np-listapi.eastmoney.com/comm/web/getNormalListByConditions"
            "?client=web&biz=web_home_article"
            "&category=gc-推-7"
            f"&page=1&pageSize={limit}"
            "&order=0&orderBy=1"
            "&fields=Title,ShowTime,DocAbstract,Url,Source"
            "&debutType=1"
        )
        resp = client.get(url, timeout=15, headers={"Referer": "https://www.eastmoney.com/"})
        js = resp.json()
        items = (js.get("data") or {}).get("list") or []
        news = []
        for item in items:
            title = str(item.get("Title", "") or "").strip()
            if not title:
                continue
            news.append({
                "title": title,
                "time": str(item.get("ShowTime", "") or ""),
                "source": str(item.get("Source", "") or "").strip() or "东方财富",
                "url": str(item.get("Url", "") or ""),
                "digest": str(item.get("DocAbstract", "") or "").strip()[:120],
            })
        return news
    except Exception as e:
        print(f"[新闻] 东方财富资讯兜底失败: {e}")
        return []


# 简单的内存缓存
_cache: dict = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry is None:
        return None
    data, timestamp, ttl = entry
    if datetime.now().timestamp() - timestamp < ttl:
        return data
    if key in _cache:
        del _cache[key]
    return None


def _cache_set(key: str, data, ttl: int = 60):
    _cache[key] = (data, datetime.now().timestamp(), ttl)


def normalize_stock_code(code: str) -> tuple[str, str]:
    """规范化股票代码，返回 (market_code, exchange)
       sz=深圳, sh=上海
    """
    code = code.strip().zfill(6)
    if code.startswith(('00', '30', '002', '003')):
        return code, "sz"
    elif code.startswith(('60', '68', '500', '501')):
        return code, "sh"
    elif code.startswith('8') or code.startswith('4'):
        return code, "bj"
    return code, "sz"


def _get_qq_market_code(code: str) -> str:
    """获取腾讯API的市场前缀"""
    code = code.strip().zfill(6)
    if code.startswith(('00', '30', '002', '003')):
        return "sz"  # 深圳
    elif code.startswith(('60', '68', '500', '501')):
        return "sh"  # 上海
    elif code.startswith('8') or code.startswith('4'):
        return "bj"  # 北交所
    return "sz"


def get_realtime_quote(codes: list[str]) -> pd.DataFrame:
    """获取实时行情，分批并发拉取（腾讯 API 单 URL 约 150 只为上限）。"""
    if not codes:
        return pd.DataFrame()

    cache_key = f"realtime:{','.join(sorted(codes))}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # 腾讯 API 单次请求上限约 150 只，分批并发
    BATCH = 150

    def _fetch_batch(batch: list[str]) -> list[dict]:
        qq_codes = []
        for code in batch:
            sym, _ = normalize_stock_code(code)
            mkt = _get_qq_market_code(code)
            qq_codes.append(f"{mkt}{sym}")
        url = f"https://qt.gtimg.cn/q={','.join(qq_codes)}"
        try:
            client = _get_client()
            resp = client.get(url, timeout=10)
            records = []
            lines = resp.text.strip().split('\n')
            for i, line in enumerate(lines):
                if not line or '=' not in line:
                    continue
                match = re.search(r'v_\w+="(.+)"', line)
                if not match:
                    continue
                data = match.group(1).split('~')
                if len(data) < 38:
                    continue
                try:
                    stock_code = batch[i] if i < len(batch) else data[2]
                    records.append({
                        "代码": data[2] if len(data) > 2 else stock_code,
                        "名称": data[1] if len(data) > 1 else "",
                        "最新价": float(data[3]) if data[3] else 0,
                        "涨跌幅": float(data[32]) if len(data) > 32 and data[32] else 0,
                        "成交量": float(data[6]) if data[6] else 0,
                        "成交额": float(data[37]) if len(data) > 37 and data[37] else 0,
                        "今开": float(data[4]) if data[4] else 0,
                        "最高": float(data[33]) if len(data) > 33 and data[33] else 0,
                        "最低": float(data[34]) if len(data) > 34 and data[34] else 0,
                        "昨收": float(data[5]) if data[5] else 0,
                    })
                except (ValueError, IndexError):
                    continue
            return records
        except Exception as e:
            print(f"[行情] 批次拉取失败: {e}")
            return []

    # 并发分批
    batches = [codes[i:i + BATCH] for i in range(0, len(codes), BATCH)]
    workers = min(len(batches), 10)
    all_records: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for records in pool.map(_fetch_batch, batches):
            all_records.extend(records)

    df = pd.DataFrame(all_records)
    if not df.empty:
        _cache_set(cache_key, df, ttl=60)
    return df


def get_kline_hist(
    code: str,
    period: str = "daily",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "qfq"
) -> pd.DataFrame:
    """
    获取历史K线数据
    period: daily/weekly/monthly/5/15/30/60 分钟
    adjust: qfq=前复权 hfq=后复权 None=不复权
    """
    cache_key = f"kline:{code}:{period}:{start_date}:{end_date}:{adjust}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sym, _ = normalize_stock_code(code)
    mkt = _get_qq_market_code(code)

    # 分钟数据使用新浪API
    minute_periods = ["5", "15", "30", "60"]
    if period in minute_periods:
        df = _get_minute_data_sina(sym, mkt, period, adjust)
        if not df.empty:
            _cache_set(cache_key, df, ttl=60)  # 分钟数据缓存60秒
        return df

    # 日/周/月数据使用腾讯API
    period_map = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
    }
    period_qq = period_map.get(period, "day")

    # 复权处理
    if adjust == "qfq":
        adjust_suffix = "qfq"
    elif adjust == "hfq":
        adjust_suffix = "hfq"
    else:
        adjust_suffix = ""

    # 默认获取500条数据
    limit = 500

    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_{period_qq}{adjust_suffix}&param={mkt}{sym},{period_qq},,,{limit},{adjust_suffix}"
        client = _get_client()
        resp = client.get(url)
        text = resp.text

        # 解析返回数据: kline_dayqfq={...}
        json_match = re.search(r'=({.+})', text)
        if not json_match:
            return pd.DataFrame()

        data = json.loads(json_match.group(1))
        key = f"{mkt}{sym}"

        if key not in data.get("data", {}):
            return pd.DataFrame()

        # 获取数据 - 注意腾讯API返回的key格式可能是 "qfqweek" 而不是 "weekqfq"
        data_key = f"{period_qq}{adjust_suffix}" if adjust_suffix else period_qq
        klines = data["data"][key].get(data_key, [])

        if not klines:
            # 尝试其他可能的key格式
            for k in [f"qfq{period_qq}", f"{period_qq}qfq", period_qq, "day", "qfqday", "hfqday", "dayhfq"]:
                if k in data["data"][key]:
                    klines = data["data"][key][k]
                    break

        if not klines:
            return pd.DataFrame()

        records = []
        for kl in klines:
            if len(kl) >= 6:
                try:
                    records.append({
                        "date": kl[0],
                        "open": float(kl[1]),
                        "close": float(kl[2]),
                        "high": float(kl[3]),
                        "low": float(kl[4]),
                        "volume": float(kl[5]),
                    })
                except (ValueError, IndexError):
                    continue

        df = pd.DataFrame(records)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            _cache_set(cache_key, df, ttl=300 if period == "daily" else 3600)
        return df
    except Exception as e:
        print(f"K线获取失败 {code} {period}: {e}")
        return pd.DataFrame()


def get_index_quote(index_code: str = "000001") -> dict:
    """获取指数实时行情"""
    cache_key = f"index:{index_code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        index_map = {
            "000001": "sh000001",
            "399001": "sz399001",
            "399006": "sz399006",
            "000688": "sh000688",
            "399300": "sz399300",  # 沪深300
            "000016": "sh000016",   # 上证50
            "000905": "sh000905",   # 中证500
            "000852": "sh000852",   # 中证1000
            "399303": "sz399303",   # 国证2000（部分行情源）
        }
        qq_code = index_map.get(index_code, f"sh{index_code}" if index_code.startswith("0") else f"sz{index_code}")

        url = f"https://qt.gtimg.cn/q={qq_code}"
        client = _get_client()
        resp = client.get(url)
        text = resp.text

        match = re.search(r'v_\w+="(.+)"', text)
        if match:
            data = match.group(1).split('~')
            if len(data) > 30:
                result = {
                    "代码": data[2] if len(data) > 2 else index_code,
                    "名称": data[1] if len(data) > 1 else "",
                    "最新价": float(data[3]) if data[3] else 0,
                    "涨跌幅": float(data[32]) if data[32] else 0,
                }
                _cache_set(cache_key, result, ttl=15)
                return result
        return {}
    except Exception as e:
        print(f"指数行情获取失败: {e}")
        return {}


def _normalize_index_row(index_code: str, display_name: str) -> dict:
    """将 get_index_quote 结果转为前端统一字段"""
    q = get_index_quote(index_code)
    if not q:
        return {
            "code": index_code,
            "name": display_name,
            "price": 0.0,
            "change_pct": 0.0,
        }
    return {
        "code": str(q.get("代码", index_code)),
        "name": str(q.get("名称") or display_name),
        "price": float(q.get("最新价", 0) or 0),
        "change_pct": float(q.get("涨跌幅", 0) or 0),
    }


def get_a_share_market_breadth() -> dict:
    """
    A 股涨跌家数：
      ① 东方财富 clist 分页统计（与涨幅榜同源，稳定）
      ② 兜底：新浪 Market_Center 分页
    """
    cache_key = "market_breadth:hs_a:v2"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result = _fetch_em_breadth_via_clist()
    if result and (result["advancers"] + result["decliners"] + result["unchanged"]) >= 500:
        _cache_set(cache_key, result, ttl=60)
        return result

    result = _fetch_sina_breadth_paginated()
    if result and (result["advancers"] + result["decliners"] + result["unchanged"]) > 0:
        _cache_set(cache_key, result, ttl=60)
        return result

    print("[涨跌家数] 所有来源均失败")
    return {"advancers": 0, "decliners": 0, "unchanged": 0}


# 与热门股涨幅榜一致的 A 股范围（沪主板/科创 + 深主板/创业板）
_EM_A_SHARE_FS = "m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23"

# 东方财富多个 push 入口：82 节点在部分网络下比主域名更稳定（避免 SSL 握手超时）
_EM_PUSH_BASES = (
    "https://push2delay.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://push2.eastmoney.com",
)


def _em_clist_request(params: dict, *, timeout: float = 25.0) -> dict | None:
    """依次尝试各 push 域名请求 api/qt/clist/get，成功返回 JSON dict。
    用 requests 直接调用（可被 run_server.py 的补丁拦截，禁用代理+verify=False）。"""
    import requests as _req
    _no_proxy = {"http": None, "https": None}
    for base in _EM_PUSH_BASES:
        try:
            resp = _req.get(
                f"{base}/api/qt/clist/get",
                params=params,
                timeout=timeout,
                verify=False,
                proxies=_no_proxy,
                headers={"Referer": "https://quote.eastmoney.com/"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[EM clist] {base} 失败: {e}")
    return None


def _fetch_em_breadth_via_clist() -> dict | None:
    """东方财富 clist 分页拉全 A，按 f3 涨跌幅统计涨跌平家数。"""
    try:
        adv, dec, flat = 0, 0, 0
        page = 1
        page_size = 500
        total_expected = None

        while page <= 30:
            js = _em_clist_request(
                {
                    "pn": page,
                    "pz": page_size,
                    "po": 1,
                    "np": 1,
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    "fs": _EM_A_SHARE_FS,
                    "fields": "f3",
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                },
                timeout=22.0,
            )
            if not js:
                break
            data = js.get("data") or {}
            if total_expected is None:
                try:
                    total_expected = int(data.get("total", 0) or 0)
                except (TypeError, ValueError):
                    total_expected = 0
            diff = data.get("diff") or []
            if not diff:
                break
            for row in diff:
                try:
                    chg = float(row.get("f3", 0) or 0)
                except (TypeError, ValueError):
                    chg = 0.0
                if chg > 0.001:
                    adv += 1
                elif chg < -0.001:
                    dec += 1
                else:
                    flat += 1
            if len(diff) < page_size:
                break
            page += 1

        total = adv + dec + flat
        print(f"[涨跌家数] EM clist: 涨 {adv} 跌 {dec} 平 {flat} 合计 {total} (预期约 {total_expected})")
        if total <= 0:
            return None
        return {"advancers": adv, "decliners": dec, "unchanged": flat}
    except Exception as e:
        print(f"[涨跌家数] EM clist 失败: {e}")
        return None


def _fetch_sina_breadth_paginated() -> dict | None:
    """新浪 A 股列表分页统计涨跌家数（兜底）。"""
    adv, dec, flat = 0, 0, 0
    page = 1
    page_size = 800
    try:
        client = _get_client()
        while page <= 25:
            url = (
                "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
                "/Market_Center.getHQNodeDataSimple"
                f"?node=hs_a&num={page_size}&sort=symbol&asc=1&page={page}"
            )
            resp = client.get(url, timeout=15)
            text = resp.content.decode("gbk", errors="replace")
            data = json.loads(text)
            if not isinstance(data, list) or len(data) == 0:
                break
            for item in data:
                try:
                    chg = float(item.get("changepercent", 0) or 0)
                except (TypeError, ValueError):
                    chg = 0.0
                if chg > 0.0001:
                    adv += 1
                elif chg < -0.0001:
                    dec += 1
                else:
                    flat += 1
            if len(data) < page_size:
                break
            page += 1
        total = adv + dec + flat
        print(f"[涨跌家数] 新浪分页: 涨 {adv} 跌 {dec} 平 {flat} 合计 {total}")
        if total <= 0:
            return None
        return {"advancers": adv, "decliners": dec, "unchanged": flat}
    except Exception as e:
        print(f"[涨跌家数] 新浪分页失败: {e}")
        return None


def get_all_industry_boards() -> list[dict]:
    """
    全部行业板块：① 东方财富行业板块（m:90+t:2）
                  ② 兜底：东方财富概念板块（m:90+t:3）
    返回 { name, change_pct } 列表，按涨跌幅降序排列。
    """
    cache_key = "industry_boards:all:v2"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # ① 行业板块
    boards = _fetch_em_industry_boards()
    if boards:
        _cache_set(cache_key, boards, ttl=120)
        print(f"[行业板块] 东方财富获取成功，共 {len(boards)} 个")
        return boards

    # ② 概念板块兜底
    boards = _fetch_em_concept_boards()
    if boards:
        _cache_set(cache_key, boards, ttl=120)
        print(f"[行业板块] 概念板块兜底成功，共 {len(boards)} 个")
        return boards

    print("[行业板块] 所有来源均失败")
    return []


def _fetch_em_industry_boards() -> list[dict]:
    """东方财富行业板块（m:90+t:2）"""
    try:
        js = _em_clist_request(
            {
                "pn": 1,
                "pz": 200,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:90+t:2",
                "fields": "f14,f3",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            },
            timeout=20.0,
        )
        if not js:
            return []
        diff = (js.get("data") or {}).get("diff") or []
        rows: list[tuple[str, float]] = []
        for row in diff:
            name = str(row.get("f14", "") or "").strip()
            if not name:
                continue
            try:
                pct = float(row.get("f3", 0) or 0)
            except (TypeError, ValueError):
                pct = 0.0
            rows.append((name, pct))
        if not rows:
            return []
        rows.sort(key=lambda x: x[1], reverse=True)
        return [{"name": n, "change_pct": round(p, 2)} for n, p in rows]
    except Exception as e:
        print(f"[行业板块] 东方财富行业失败: {e}")
        return []


def _fetch_em_concept_boards() -> list[dict]:
    """东方财富概念板块（m:90+t:3）兜底"""
    try:
        js = _em_clist_request(
            {
                "pn": 1,
                "pz": 200,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:90+t:3",
                "fields": "f14,f3",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            },
            timeout=20.0,
        )
        if not js:
            return []
        diff = (js.get("data") or {}).get("diff") or []
        rows: list[tuple[str, float]] = []
        for row in diff:
            name = str(row.get("f14", "") or "").strip()
            if not name:
                continue
            try:
                pct = float(row.get("f3", 0) or 0)
            except (TypeError, ValueError):
                pct = 0.0
            rows.append((name, pct))
        if not rows:
            return []
        rows.sort(key=lambda x: x[1], reverse=True)
        return [{"name": n, "change_pct": round(p, 2)} for n, p in rows]
    except Exception as e:
        print(f"[行业板块] 概念板块兜底失败: {e}")
        return []


def get_industry_board_movers(limit_each: int = 5) -> dict:
    """
    行业板块涨跌幅（兼容旧接口）：东方财富 push2 接口。
    返回 top（涨幅前 N）与 bottom（跌幅前 N）。
    """
    all_boards = get_all_industry_boards()
    if not all_boards:
        return {"top": [], "bottom": []}

    top = all_boards[:limit_each]
    bottom = list(reversed(all_boards[-limit_each:]))
    return {"top": top, "bottom": bottom}


def get_market_overview_bundle() -> dict:
    """聚合：主要指数 + 涨跌家数 + 全部行业板块（供 /api/market/overview）"""
    indices = {
        "sh": _normalize_index_row("000001", "上证指数"),
        "sz": _normalize_index_row("399001", "深证成指"),
        "cyb": _normalize_index_row("399006", "创业板指"),
        "kc50": _normalize_index_row("000688", "科创50"),
        "hs300": _normalize_index_row("399300", "沪深300"),
        "zz500": _normalize_index_row("000905", "中证500"),
    }
    breadth = get_a_share_market_breadth()
    all_boards = get_all_industry_boards()
    top5 = all_boards[:5]
    bottom5 = list(reversed(all_boards[-5:]))
    return {
        "indices": indices,
        "market_breadth": breadth,
        "sectors": all_boards,
        "sectors_top": top5,
        "sectors_bottom": bottom5,
    }


def _parse_sina_suggest(text: str) -> list[dict]:
    """
    解析新浪搜索响应
    两种格式：
      名称搜索: "徐工机械,11,000425,sz000425,徐工机械,..."
      代码搜索: "sz000425,11,000425,sz000425,徐工机械,..."
    """
    if not text.startswith('var suggestvalue='):
        return []
    content = text[len('var suggestvalue='):].strip().strip('"').rstrip(';')
    if not content or content == 'N':
        return []

    records = []
    for entry in content.split(';'):
        items = entry.split(',')
        if len(items) < 5:
            continue

        first_field = items[0]
        # 判断格式：市场代码搜索（以sz/sh开头）还是名称搜索
        if first_field.startswith(('sz', 'sh')):
            # 代码搜索格式: 市场代码,类型,代码,市场代码,名称,...
            market_code = items[0]
            code = items[2]
            name = items[4]
        else:
            # 名称搜索格式: 名称,类型,代码,市场代码,名称,...
            name = items[0]
            code = items[2]
            market_code = items[3]

        # 只保留A股
        if (market_code.startswith('sh') or market_code.startswith('sz')) and not name.isdigit():
            records.append({"code": code, "name": name})

    return records


def search_stocks(keyword: str) -> pd.DataFrame:
    """搜索股票 - 使用新浪搜索API"""
    cache_key = f"search:{keyword}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        # 始终使用 UTF-8 URL encode（两种搜索都有效）
        keyword_encoded = urllib.parse.quote(keyword)
        url = f"https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={keyword_encoded}"
        client = _get_client()
        resp = client.get(url)
        text = resp.content.decode('gbk', errors='replace').strip()

        records = _parse_sina_suggest(text)

        # 去重并限制数量
        seen: set[str] = set()
        unique = []
        for r in records:
            if r['code'] not in seen:
                seen.add(r['code'])
                unique.append(r)

        df = pd.DataFrame(unique[:20])
        _cache_set(cache_key, df, ttl=3600)
        return df
    except Exception as e:
        print(f"股票搜索失败: {e}")
        return pd.DataFrame()


def get_daily_hot_stocks(limit: int = 20) -> list:
    """当日个股人气榜（东方财富），返回含代码、名称、排名等；缓存为空时直接获取实时数据。"""
    limit = max(1, int(limit))
    cache_key = f"hot:daily:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    return _fetch_and_cache_hot(limit)


def _fetch_and_cache_hot(limit: int = 20) -> list:
    """按优先级尝试多个来源获取热门股票：东方财富涨幅榜 → 同花顺 → 新浪人气榜。"""
    limit = max(1, int(limit))
    cache_key = f"hot:daily:{limit}"

    # ① 东方财富涨幅榜（按涨跌幅）
    stocks = _fetch_em_hot_stocks(limit)
    if stocks:
        _cache_set(cache_key, stocks, ttl=120)
        print(f"[热门] 东方财富涨幅榜获取成功，共 {len(stocks)} 条")
        return stocks

    # ② 同花顺热门
    stocks = _fetch_ths_hot_stocks(limit)
    if stocks:
        _cache_set(cache_key, stocks, ttl=120)
        print(f"[热门] 同花顺热门获取成功，共 {len(stocks)} 条")
        return stocks

    # ③ 新浪人气榜兜底
    stocks = _fetch_sina_hot_stocks(limit)
    _cache_set(cache_key, stocks, ttl=60)
    if stocks:
        print(f"[热门] 新浪人气榜获取成功，共 {len(stocks)} 条")
    else:
        print("[热门] 所有来源均获取失败")
    return stocks


def _fetch_em_hot_stocks(limit: int) -> list:
    """东方财富涨幅榜（今日涨跌幅从高到低），并发分页，最多支持 1000 条。"""
    PAGE_SIZE = 100
    total_pages = (limit + PAGE_SIZE - 1) // PAGE_SIZE

    def fetch_page(pn: int) -> list[dict]:
        try:
            js = _em_clist_request(
                {
                    "pn": pn,
                    "pz": PAGE_SIZE,
                    "po": 1,
                    "np": 1,
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    "fs": "m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23",
                    "fields": "f2,f3,f4,f12,f14",
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                },
                timeout=20.0,
            )
            if not js:
                return []
            diff = (js.get("data") or {}).get("diff") or []
            stocks = []
            for row in diff:
                try:
                    price = float(row.get("f2", 0) or 0)
                    chg = float(row.get("f3", 0) or 0)
                except (TypeError, ValueError):
                    price, chg = 0.0, 0.0
                code = str(row.get("f12", "") or "").strip()
                name = str(row.get("f14", "") or "").strip()
                if not code:
                    continue
                stocks.append({
                    "code": code.zfill(6),
                    "name": name,
                    "change_pct": round(chg, 2),
                    "price": round(price, 2),
                    "volume": 0,
                })
            return stocks
        except Exception as e:
            print(f"[热门-分页] 第 {pn} 页失败: {e}")
            return []

    all_stocks: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(total_pages, 10)) as pool:
        futures = {pool.submit(fetch_page, pn): pn for pn in range(1, total_pages + 1)}
        for future in as_completed(futures):
            try:
                page_stocks = future.result(timeout=25.0)
                all_stocks.extend(page_stocks)
            except Exception as e:
                pn = futures[future]
                print(f"[热门-分页] 第 {pn} 页超时/异常: {e}")

    # 按涨幅降序重新编号
    all_stocks.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    for idx, s in enumerate(all_stocks, start=1):
        s["rank"] = idx

    return all_stocks[:limit]


def _fetch_ths_hot_stocks(limit: int) -> list:
    """同花顺热门股票"""
    try:
        client = _get_client()
        url = (
            "https://d.10jqka.com.cn/v6/line/hs_a/01/order=desc/page=1/ajax=1/fund=2"
        )
        resp = client.get(url, timeout=10, headers={"Referer": "https://www.10jqka.com.cn/"})
        text = resp.text
        data = json.loads(text)
        items = data.get("data", []) if isinstance(data, dict) else []
        stocks = []
        for idx, item in enumerate(items[:limit], start=1):
            try:
                chg = float(item.get("zxdf", 0))
            except (TypeError, ValueError):
                chg = 0.0
            code = str(item.get("code", "") or "").strip()
            name = str(item.get("name", "") or "").strip()
            if not code:
                continue
            stocks.append({
                "rank": idx,
                "code": code.zfill(6),
                "name": name,
                "change_pct": round(chg, 2),
                "volume": 0,
            })
        return stocks
    except Exception as e:
        print(f"[热门] 同花顺热门失败: {e}")
        return []


def _fetch_sina_hot_stocks(limit: int) -> list:
    """新浪人气榜（兜底）"""
    try:
        client = _get_client()
        url = (
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
            "/Market_Center.getHQNodeDataSimple"
            f"?node=hs_a&num={limit}&sort=focus&asc=0&page=1"
        )
        resp = client.get(url, timeout=15)
        text = resp.content.decode("gbk", errors="replace")
        data = json.loads(text)
        if not isinstance(data, list):
            print(f"[热门] 新浪人气榜返回格式异常: {text[:200]}")
            return []

        stocks = []
        for idx, item in enumerate(data, start=1):
            symbol = str(item.get("symbol", "")).strip()
            for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
                if symbol.startswith(p):
                    code = symbol[len(p):].zfill(6)
                    break
            else:
                code = symbol.zfill(6) if symbol.isdigit() else symbol

            try:
                chg = float(item.get("changepercent", 0))
            except (TypeError, ValueError):
                chg = 0.0
            try:
                vol = int(float(item.get("volume", 0) or 0))
            except (TypeError, ValueError):
                vol = 0

            stocks.append({
                "rank": idx,
                "code": code,
                "name": str(item.get("name", "") or "").strip(),
                "change_pct": round(chg, 2),
                "volume": vol,
            })
        return stocks
    except Exception as e:
        print(f"[热门] 新浪人气榜失败: {e}")
        return []


def warm_hot_cache():
    """后台线程预热热门股票缓存（5 分钟刷新一次）。"""
    import threading, time
    def _loop():
        while True:
            _fetch_and_cache_hot(20)
            time.sleep(300)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print("热门股票后台预热线程已启动")


def get_stock_info(code: str) -> dict:
    """获取股票基本信息"""
    cache_key = f"info:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sym, _ = normalize_stock_code(code)
    mkt = _get_qq_market_code(code)

    try:
        url = f"https://qt.gtimg.cn/q={mkt}{sym}"
        client = _get_client()
        resp = client.get(url)
        text = resp.text

        match = re.search(r'v_\w+="(.+)"', text)
        if match:
            data = match.group(1).split('~')
            # 与 get_realtime_quote 一致：≥38 即可解析核心字段；勿用 >45 过严导致部分行情返回被丢弃
            if len(data) >= 38:
                info = {
                    "代码": data[2] if len(data) > 2 else sym,
                    "名称": data[1] if len(data) > 1 else "",
                    "现价": float(data[3]) if data[3] else 0,
                    "涨跌幅": float(data[32]) if len(data) > 32 and data[32] else 0,
                    "涨跌额": float(data[31]) if len(data) > 31 and data[31] else 0,
                    "成交量": float(data[6]) if data[6] else 0,
                    "成交额": float(data[37]) if len(data) > 37 and data[37] else 0,
                    "振幅": float(data[43]) if len(data) > 43 and data[43] else 0,
                    "最高": float(data[33]) if len(data) > 33 and data[33] else 0,
                    "最低": float(data[34]) if len(data) > 34 and data[34] else 0,
                    "今开": float(data[4]) if data[4] else 0,
                    "昨收": float(data[5]) if data[5] else 0,
                    "市净率": float(data[46]) if len(data) > 46 and data[46] else 0,
                    "市盈率": float(data[39]) if len(data) > 39 and data[39] else 0,
                }
                _cache_set(cache_key, info, ttl=300)
                return info
        return {}
    except Exception as e:
        print(f"股票信息获取失败: {e}")
        return {}


def get_stock_depth_em(code: str) -> dict:
    """
    东方财富五档盘口（买卖各五档）。
    返回 {"asks": [{"price": float, "volume": int}, ...], "bids": [...]}，
    asks 顺序为卖五→卖一（由上到下）。
    """
    cache_key = f"depth_em:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sym, _ = normalize_stock_code(code)
    secid = f"1.{sym}" if sym.startswith("6") else f"0.{sym}"
    params = {
        "fltt": "2",
        "invt": "2",
        "secid": secid,
        "fields": "f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f41,f42,f19,f20,f21,f22,f23,f24",
    }

    # 多域名兜底，顺序尝试
    hosts = [
        "https://push2.eastmoney.com/api/qt/stock/get",
        "https://push2delay.eastmoney.com/api/qt/stock/get",
        "https://push2his.eastmoney.com/api/qt/stock/get",
    ]

    d = None
    for host in hosts:
        try:
            client = _get_client()
            resp = client.get(host, params=params, timeout=8)
            js = resp.json()
            d = js.get("data")
            if d:
                break
        except Exception as e:
            print(f"[盘口] {host} 失败: {e}")
            continue

    if not d:
        out = {"asks": [], "bids": []}
        _cache_set(cache_key, out, ttl=30)
        return out

    # 直接解析字段，不依赖 pandas
    asks: list[dict] = []
    for i in range(5, 0, -1):
        pair = {5: (31, 32), 4: (33, 34), 3: (35, 36), 2: (37, 38), 1: (39, 40)}[i]
        p_idx, v_idx = pair
        price = d.get(f"f{p_idx}")
        vol = d.get(f"f{v_idx}")
        asks.append({
            "price": round(float(price), 3) if price else 0.0,
            "volume": int(float(vol or 0) * 100),
        })

    bids: list[dict] = []
    for i in range(1, 6):
        pair = {1: (19, 20), 2: (21, 22), 3: (23, 24), 4: (25, 26), 5: (27, 28)}[i]
        p_idx, v_idx = pair
        price = d.get(f"f{p_idx}")
        vol = d.get(f"f{v_idx}")
        bids.append({
            "price": round(float(price), 3) if price else 0.0,
            "volume": int(float(vol or 0) * 100),
        })

    out = {"asks": asks, "bids": bids}
    _cache_set(cache_key, out, ttl=15)
    return out


def get_stock_boards_em(code: str) -> dict:
    """
    个股资料中的行业等信息，直接请求东方财富接口（替代 akshare）。
    """
    cache_key = f"boards_em:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sym, _ = normalize_stock_code(code)
    secid = f"1.{sym}" if sym.startswith("6") else f"0.{sym}"
    params = {
        "fltt": "2",
        "invt": "2",
        "secid": secid,
        "fields": "f127,f84,f85,f116,f117,f189,f43",
    }

    hosts = [
        "https://push2.eastmoney.com/api/qt/stock/get",
        "https://push2delay.eastmoney.com/api/qt/stock/get",
        "https://push2his.eastmoney.com/api/qt/stock/get",
    ]

    d = None
    for host in hosts:
        try:
            client = _get_client()
            resp = client.get(host, params=params, timeout=8)
            js = resp.json()
            d = js.get("data")
            if d:
                break
        except Exception as e:
            print(f"[板块] {host} 失败: {e}")
            continue

    if d is None:
        out = {"industry": "", "highlights": []}
        _cache_set(cache_key, out, ttl=60)
        return out

    industry = str(d.get("f127") or "").strip()
    highlights: list[dict] = []
    interest = ("行业", "总市值", "流通市值", "总股本", "流通股", "上市时间")
    seen: set[str] = set()

    def _add(label: str, val):
        if val is None:
            return
        val_s = str(val).strip()
        if not val_s:
            return
        if label in interest or any(x in label for x in interest):
            if label not in seen:
                seen.add(label)
                highlights.append({"label": label, "value": val_s})

    _add("行业", d.get("f127"))
    _add("总市值", d.get("f116"))
    _add("流通市值", d.get("f117"))
    _add("总股本", d.get("f84"))
    _add("流通股", d.get("f85"))

    # 上市时间处理
    listed_date = d.get("f189")
    if listed_date:
        try:
            listed_str = str(int(float(listed_date)))
            if len(listed_str) == 8:
                formatted = f"{listed_str[:4]}-{listed_str[4:6]}-{listed_str[6:]}"
                _add("上市时间", formatted)
        except (ValueError, TypeError):
            pass

    highlights.sort(key=lambda x: (0 if "行业" in x["label"] else 1, x["label"]))
    out = {"industry": industry, "highlights": highlights[:8]}
    _cache_set(cache_key, out, ttl=600)
    return out


def get_stock_symbol_news_em(code: str, limit: int = 8) -> list:
    """东方财富个股相关新闻。"""
    limit = max(1, min(20, int(limit)))
    cache_key = f"sym_news_em:{code}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sym, _ = normalize_stock_code(code)
    try:
        import akshare as ak

        df = ak.stock_news_em(symbol=sym)
        if df is None or df.empty:
            _cache_set(cache_key, [], ttl=300)
            return []

        ncols = len(df.columns)
        title_i = 1 if ncols > 1 else 0
        time_i = 3 if ncols > 3 else min(2, ncols - 1)
        src_i = 4 if ncols > 4 else min(3, ncols - 1)
        url_i = 5 if ncols > 5 else ncols - 1

        items = []
        for _, row in df.head(limit).iterrows():
            try:
                title = str(row.iloc[title_i]).strip()
                url = str(row.iloc[url_i]).strip()
                if not title:
                    continue
                items.append({
                    "title": title[:300],
                    "time": str(row.iloc[time_i]).strip()[:32] if ncols > time_i else "",
                    "source": str(row.iloc[src_i]).strip()[:48] if ncols > src_i else "",
                    "url": url if url.startswith("http") else "",
                })
            except (IndexError, TypeError, ValueError):
                continue

        _cache_set(cache_key, items, ttl=300)
        return items
    except Exception as e:
        print(f"[个股新闻] 失败 {code}: {e}")
        return []


# ─── 分时数据 ────────────────────────────────────────────────────────────────
def get_minute_data(code: str, period: str = "5") -> pd.DataFrame:
    """获取分钟K线数据"""
    cache_key = f"minute:{code}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # 分钟数据使用日K接口的分钟数据
    return get_kline_hist(code, period=period, adjust="qfq")


# ─── 新浪分钟数据 ─────────────────────────────────────────────────────────────
def _get_minute_data_sina(code: str, market: str, period: str, adjust: str = "qfq") -> pd.DataFrame:
    """
    使用新浪API获取分钟K线数据
    period: 5, 15, 30, 60 (分钟)
    """
    # 新浪代码格式: sz000001, sh600000
    sina_code = f"{market}{code}"

    # 新浪API参数
    scale_map = {"5": 5, "15": 15, "30": 30, "60": 60}
    scale = scale_map.get(period, 30)

    # 新浪API URL
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_code}&scale={scale}&ma=no&datalen=500"

    try:
        client = _get_client()
        resp = client.get(url)
        data = resp.json()

        if not data or not isinstance(data, list):
            return pd.DataFrame()

        records = []
        for kl in data:
            try:
                records.append({
                    "date": pd.to_datetime(kl.get("day", "")),
                    "open": float(kl.get("open", 0)),
                    "close": float(kl.get("close", 0)),
                    "high": float(kl.get("high", 0)),
                    "low": float(kl.get("low", 0)),
                    "volume": float(kl.get("volume", 0)),
                })
            except (ValueError, TypeError):
                continue

        df = pd.DataFrame(records)
        return df
    except Exception as e:
        print(f"新浪分钟数据获取失败 {code} {period}: {e}")
        return pd.DataFrame()
