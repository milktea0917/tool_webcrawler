#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, time, re, json, sys, traceback
from collections import deque, defaultdict
from urllib.parse import urljoin, urlparse, urlunparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

# --- 可選：Selenium 渲染 ---
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    _SELENIUM_AVAILABLE = True
except Exception:
    _SELENIUM_AVAILABLE = False


def normalize_url(base, href):
    """把相對連結補全、去掉 fragment/query、統一為 http(s)。"""
    if not href:
        return None
    if href.startswith("mailto:") or href.startswith("javascript:") or href.startswith("tel:"):
        return None
    u = urljoin(base, href)
    parts = list(urlparse(u))
    if parts[0] not in ("http", "https"):
        return None
    # 清掉 query / fragment
    parts[4] = ""  # query
    parts[5] = ""  # fragment
    cleaned = urlunparse(parts)
    # 去除多餘的結尾斜線（但保留根）
    if cleaned.endswith("/") and cleaned.count("/") > 2:
        cleaned = cleaned[:-1]
    return cleaned


def same_domain(u1, u2):
    """是否同網域（含子網域視為不同，若要寬鬆可自行調整）。"""
    return urlparse(u1).netloc == urlparse(u2).netloc


def looks_like_binary(content_type):
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip().lower()
    # 常見非 HTML / 非純文本格式
    return any(ct.endswith(x) for x in [
        "pdf", "zip", "octet-stream", "msword",
        "vnd.openxmlformats-officedocument", "image/jpeg", "image/png",
        "image/gif", "image/webp", "audio/", "video/"
    ]) or (ct not in ("text/html", "text/plain") and "html" not in ct)


def get_title_and_text(html):
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else None)
    # 粗略擷取可讀文字（避免太大）
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return title, text[:2000]  # 截斷避免爆量


class PageFetcher:
    """抽象抓頁：requests 或 selenium（可切換）"""
    def __init__(self, render=False, headless=True, user_agent=None, timeout=15):
        self.render = render and _SELENIUM_AVAILABLE
        self.timeout = timeout
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; SimpleCrawler/1.0)"
        self.driver = None
        if render and not _SELENIUM_AVAILABLE:
            print("[Warn] Selenium 未安裝或不可用，將改用 requests。", file=sys.stderr)
        if self.render:
            opts = ChromeOptions()
            if headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--window-size=1400,1800")
            opts.add_argument(f"user-agent={self.user_agent}")
            self.driver = webdriver.Chrome(options=opts)
            self.driver.set_page_load_timeout(self.timeout)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

    def fetch(self, url):
        """
        回傳：status, content_type, html_text（若是 HTML）, raw_text
        非 HTML 內容只回傳 raw_text=None。
        """
        if self.render and self.driver:
            try:
                self.driver.get(url)
                # 簡單等待一下（可依需求調整或加入顯式等待）
                time.sleep(0.6)
                html = self.driver.page_source or ""
                status = 200  # Selenium 看不到 status code，當作 200
                ctype = "text/html"
                return status, ctype, html, None
            except Exception as e:
                return 0, None, None, None

        # requests 版本
        try:
            resp = self.session.get(url, timeout=self.timeout)
            ctype = resp.headers.get("Content-Type", "")
            if looks_like_binary(ctype):
                return resp.status_code, ctype, None, None
            return resp.status_code, ctype, resp.text, None
        except Exception:
            return 0, None, None, None


def build_robot_parser(start_url, ua):
    """讀取 robots.txt，無法讀取時採『允許』策略（常見做法之一）"""
    p = robotparser.RobotFileParser()
    base = urlparse(start_url)
    robots_url = f"{base.scheme}://{base.netloc}/robots.txt"
    try:
        p.set_url(robots_url)
        p.read()
    except Exception:
        pass
    # 若 robots 無法讀，RobotFileParser 會 is_allowed 回傳 True
    return p


def crawl(start_url, max_pages, max_depth, delay, include_re, exclude_re,
          same_domain_only, user_agent, output, render, headless, timeout):
    start_url = normalize_url(start_url, "") or start_url
    if not start_url:
        print("[Error] 起始網址無效。", file=sys.stderr)
        sys.exit(2)

    rp = build_robot_parser(start_url, user_agent)
    fetcher = PageFetcher(render=render, headless=headless, user_agent=user_agent, timeout=timeout)

    seen = set()
    results = []
    q = deque()
    q.append((start_url, 0))

    # 每網域的上次請求時間（簡單同域節流）
    last_fetch_time = defaultdict(lambda: 0.0)

    try:
        while q and len(results) < max_pages:
            url, depth = q.popleft()
            if url in seen:
                continue
            seen.add(url)

            if same_domain_only and not same_domain(start_url, url):
                continue

            if not rp.can_fetch(user_agent, url):
                # 被 robots 禁爬
                continue

            # 節流（同網域）
            host = urlparse(url).netloc
            now = time.time()
            delta = now - last_fetch_time[host]
            if delta < delay:
                time.sleep(delay - delta)

            status, ctype, html, _ = fetcher.fetch(url)
            last_fetch_time[host] = time.time()

            page_info = {
                "url": url,
                "status": status,
                "content_type": ctype,
                "title": None,
                "text_snippet": None,
                "outlinks": []
            }

            if status == 0:
                results.append(page_info)
                continue

            if html:
                title, text = get_title_and_text(html)
                page_info["title"] = title
                page_info["text_snippet"] = text[:500] if text else None

                # 解析出鏈
                soup = BeautifulSoup(html, "html.parser")
                hrefs = []
                for a in soup.find_all("a", href=True):
                    nu = normalize_url(url, a.get("href"))
                    if not nu:
                        continue
                    # include / exclude 過濾
                    if include_re and not re.search(include_re, nu):
                        continue
                    if exclude_re and re.search(exclude_re, nu):
                        continue
                    hrefs.append(nu)

                # 去重
                hrefs = list(dict.fromkeys(hrefs))
                page_info["outlinks"] = hrefs[:200]  # 避免過大

                # enqueue
                if depth < max_depth:
                    for nxt in hrefs:
                        if nxt not in seen:
                            q.append((nxt, depth + 1))

            results.append(page_info)

        # 輸出
        with open(output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"✅ Done. Crawled {len(results)} pages. Saved to {output}")
        return 0

    except KeyboardInterrupt:
        print("\n[Info] 使用者中斷，寫出已抓到的結果…", file=sys.stderr)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return 130
    except Exception as e:
        print("[Error] 未預期錯誤：", e, file=sys.stderr)
        traceback.print_exc()
        # 仍盡量輸出目前為止的結果
        with open(output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return 1
    finally:
        fetcher.close()


def main():
    parser = argparse.ArgumentParser(
        description="A configurable BFS web crawler with optional JS rendering."
    )
    parser.add_argument("--web", required=True, help="起始網址（e.g. https://example.com）")
    parser.add_argument("--max-pages", type=int, default=100, help="最大頁數（預設 100）")
    parser.add_argument("--max-depth", type=int, default=3, help="最大深度（預設 3）")
    parser.add_argument("--delay", type=float, default=0.8, help="同網域請求間隔秒數（預設 0.8s）")
    parser.add_argument("--include", default=None, help="只抓符合此 regex 的連結（選填）")
    parser.add_argument("--exclude", default=None, help="排除符合此 regex 的連結（選填）")
    parser.add_argument("--all-domains", action="store_true", help="允許跨網域（預設關閉）")
    parser.add_argument("--user-agent", default="Mozilla/5.0 (compatible; SimpleCrawler/1.0)",
                        help="自訂 User-Agent")
    parser.add_argument("--output", default="crawl_result.json", help="輸出 JSON 檔名")
    parser.add_argument("--render", action="store_true",
                        help="啟用 Selenium 解析（需安裝 Chrome/driver）")
    parser.add_argument("--headless", action="store_true", help="Selenium headless 模式")
    parser.add_argument("--timeout", type=int, default=15, help="逾時秒數（預設 15）")

    args = parser.parse_args()

    return crawl(
        start_url=args.web,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        delay=args.delay,
        include_re=args.include,
        exclude_re=args.exclude,
        same_domain_only=(not args.all_domains),
        user_agent=args.user_agent,
        output=args.output,
        render=args.render,
        headless=args.headless,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
