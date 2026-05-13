import re
from urllib.parse import quote, unquote

import requests
from ddgs import DDGS
from django.conf import settings
from openai import OpenAI
from orders.models import Order


IFIXIT_BASE_URL = getattr(settings, "IFIXIT_BASE_URL", "https://www.ifixit.com/api/2.0")
IFIXIT_TIMEOUT = getattr(settings, "IFIXIT_TIMEOUT", 8)


def safe_text(value):
    return value.strip() if isinstance(value, str) else ""


def is_repair_related_message(message: str) -> bool:
    message = safe_text(message).lower()
    if not message:
        return False

    repair_keywords = [
        # general repair/action keywords
        "repair", "fix", "replace", "replacement", "remove", "install", "reinstall",
        "broken", "not working", "issue", "problem", "help", "diagnose", "troubleshoot",

        # battery / charging / power
        "battery", "battery swelling", "charging", "charge", "won't charge", "won't turn on",
        "not turning on", "power", "power supply", "charger", "adapter", "charging port",
        "power button", "won't boot", "bootloop", "dead", "bricked",

        # display / screen / input
        "screen", "lcd", "led", "oled", "backlight", "dead pixel", "cracked screen",
        "touchscreen", "digitizer", "display", "black screen", "no display", "flicker",
        "hinge", "hinges", "bezel",

        # motherboard / core components
        "motherboard", "cpu", "processor", "gpu", "graphics", "ram", "memory",
        "ssd", "hdd", "hard drive", "nvme", "storage", "bios", "firmware",

        # ports / connectivity
        "port", "usb", "usb-c", "thunderbolt", "hdmi", "vga", "ethernet",
        "wifi", "wireless", "bluetooth", "pairing", "network",

        # audio / camera / peripherals
        "speaker", "microphone", "mic", "audio", "headphone", "headphones", "webcam", "camera",
        "headphone jack",

        # thermal / mechanical
        "fan", "fan noise", "overheating", "thermal", "heatsink", "cooling",
        "smoke", "burned", "short", "capacitor",

        # storage / data
        "data recovery", "corrupted", "filesystem", "format", "partition", "cloning",

        # software / OS / drivers
        "driver", "drivers", "update", "windows", "macos", "mac", "ios", "android", "linux",
        "bootloader", "kernel", "blue screen", "bsod", "virus", "malware", "ransomware",

        # common faults / phrases
        "stuck", "crash", "crashing", "freezing", "slow", "lag", "won't charge", "charging issue",
        "water damage", "liquid damage", "shorted", "stuck keys", "keyboard not working", "trackpad", "touchpad",

        # cards / accessories
        "sd card", "micro sd", "sim", "sim card", "microsd", "card reader",

        # repair actions / tools
        "solder", "reflow", "desolder", "glue", "adhesive", "pry", "spudger", "screw", "screws",

        # generic troubleshooting prompts
        "troubleshoot", "diagnose", "how do i", "how to", "steps", "guide", "tutorial", "fix my",
    ]
    return any(keyword in message for keyword in repair_keywords)


def get_order_device_context(user, current_order_id=None) -> dict:
    if not current_order_id:
        return {}

    try:
        order = Order.objects.get(id=current_order_id, user=user)
        return {
            "device_type": safe_text(order.device_type),
            "issue_description": safe_text(order.issue_description),
            "order_id": order.id,
        }
    except Order.DoesNotExist:
        return {}


STOPWORDS = {
    "hi", "hello", "hey", "so", "my", "i", "im", "i'm", "me", "a", "an",
    "the", "is", "it", "its", "it's", "isn't", "isnt", "like", "can", "you",
    "do", "does", "have", "has", "any", "some", "please", "thanks", "thank",
    "would", "could", "should", "with", "for", "and", "but", "or", "that",
    "this", "just", "really", "very", "having", "been", "be", "am", "are",
    "was", "were", "of", "to", "in", "at", "about", "what", "how",
    "suggestions", "suggestion", "advice", "thoughts", "ideas", "know",
    "need", "want", "get", "got", "going", "thing", "things", "think",
    "help", "working", "work", "doesn't", "doesnt", "didn't", "didnt",
    "don't", "dont", "also", "still", "maybe", "try", "trying",
}


def _fallback_clean(message: str, order_context: dict) -> str:
    """Strip stopwords and punctuation as a simple fallback query."""
    order_device = safe_text(order_context.get("device_type"))
    words = safe_text(message).split()
    cleaned = []
    for w in words:
        stripped = re.sub(r"[.,!?;:'\"()\[\]]", "", w)
        if stripped and stripped.lower() not in STOPWORDS and len(stripped) > 1:
            cleaned.append(stripped)
    query = " ".join(cleaned)[:80]
    if order_device and order_device.lower() not in query.lower():
        query = f"{order_device} {query}"
    return query.strip()[:100]


def extract_search_query(message: str, order_context: dict) -> str:
    """
    Use a quick LLM call to extract a clean iFixit search query
    from the user's message. Falls back to stopword removal on failure.
    """
    raw_message = safe_text(message)
    if not raw_message:
        return ""

    print(f"[iFixit] Raw user message: \"{raw_message}\"", flush=True)

    order_device = safe_text(order_context.get("device_type"))
    order_hint = (
        f"\nThe user's current repair order is for a: {order_device}"
        if order_device else ""
    )

    system_prompt = (
        "You extract search queries from user messages for the iFixit repair database.\n"
        "Given a user message about a device problem, return ONLY a short search query "
        "(3-6 words) containing the specific device model and core problem.\n"
        "Do NOT add extra words like 'troubleshooting', 'repair guide', or 'how to'.\n"
        "Do NOT explain your reasoning. Output ONLY the search query.\n"
        "If the message has no repair-related content, return exactly: NONE\n"
        "Examples:\n"
        "  'my xbox one isn't turning on' -> Xbox One not turning on\n"
        "  'MacBook Pro 2022 screen is cracked' -> MacBook Pro 2022 cracked screen\n"
        "  'thanks for the help!' -> NONE\n"
        f"{order_hint}"
    )

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_message},
            ],
            max_tokens=30,
            temperature=0,
        )

        raw_content = response.choices[0].message.content
        if raw_content is None:
            print("[iFixit] AI returned empty response, using fallback", flush=True)
            fallback = _fallback_clean(raw_message, order_context)
            print(f"[iFixit] Fallback query: \"{fallback}\"", flush=True)
            return fallback

        query = safe_text(raw_content).strip("\"'")

        if query.upper() == "NONE":
            print("[iFixit] AI found no repair content in message", flush=True)
            return ""

        if not query or len(query) > 60:
            print(f"[iFixit] AI response too long, using fallback: \"{query[:80]}...\"", flush=True)
            fallback = _fallback_clean(raw_message, order_context)
            print(f"[iFixit] Fallback query: \"{fallback}\"", flush=True)
            return fallback

        print(f"[iFixit] AI extracted query: \"{query}\"", flush=True)
        return query[:100]

    except Exception as exc:
        print(f"[iFixit] AI extraction failed, using fallback: {exc}", flush=True)
        fallback = _fallback_clean(raw_message, order_context)
        print(f"[iFixit] Fallback query: \"{fallback}\"", flush=True)
        return fallback


def search_ifixit(query: str) -> dict:
    if not query:
        return {"results": [], "error": None}

    encoded_query = quote(query)
    url = f"{IFIXIT_BASE_URL}/search/{encoded_query}"

    print(f"[iFixit] Search query: {query}", flush=True)
    print(f"[iFixit] URL: {url}", flush=True)

    try:
        response = requests.get(
            url,
            timeout=IFIXIT_TIMEOUT,
            headers={"Accept": "application/json"}
        )

        print(f"[iFixit] Status code: {response.status_code}", flush=True)
        print(f"[iFixit] Raw response preview: {response.text[:500]}", flush=True)

        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            if "results" not in data:
                data["results"] = []
            data["error"] = None
            return data

        if isinstance(data, list):
            return {"results": data, "error": None}

        return {"results": [], "error": "Unexpected iFixit response format"}

    except requests.RequestException as exc:
        return {"results": [], "error": f"iFixit request failed: {str(exc)}"}
    except ValueError as exc:
        return {"results": [], "error": f"iFixit invalid JSON: {str(exc)}"}


def _clean_wiki_markup(raw: str) -> str:
    """Strip iFixit wiki markup to plain readable text."""
    cleaned = re.sub(r"\[comment\].*?\[/comment\]", "", raw)
    cleaned = re.sub(r"\[link\|[^]]*\]([^[]*)\[/link\]", r"\1", cleaned)
    # [guide|ID|text|extra], [product|ID|text|extra], [post|ID]
    cleaned = re.sub(r"\[(guide|product)\|[^|]*\|([^|\]]*)[^\]]*\]", r"\2", cleaned)
    cleaned = re.sub(r"\[post\|\d+\]", "", cleaned)
    # [[wiki_key#Section|display text]] and [[wiki_key]]
    cleaned = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", cleaned)
    cleaned = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cleaned)
    # === heading ===, == heading ==, = heading =
    cleaned = re.sub(r"={1,3}\s*(.+?)\s*={1,3}", r"\n\1", cleaned)
    # ''italic'' markup
    cleaned = re.sub(r"''(.+?)''", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def fetch_wiki_content(wikiid: int) -> str:
    """Fetch the full guide/troubleshooting content for a wiki by ID."""
    url = f"{IFIXIT_BASE_URL}/wikis/{wikiid}"
    print(f"[iFixit] Fetching wiki by ID: {url}", flush=True)

    try:
        response = requests.get(
            url, timeout=IFIXIT_TIMEOUT, headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        raw = safe_text(response.json().get("contents_raw", ""))
        if raw:
            cleaned = _clean_wiki_markup(raw)
            print(f"[iFixit] Wiki content fetched: {len(cleaned)} chars", flush=True)
            return cleaned
    except Exception as exc:
        print(f"[iFixit] Wiki fetch failed: {exc}", flush=True)
    return ""


def fetch_wiki_by_title(wiki_title: str) -> str:
    """Fetch the full wiki content by namespace/title (e.g. WIKI/Xbox_One_Won't_Turn_On)."""
    encoded = quote(wiki_title.replace(" ", "_"))
    url = f"{IFIXIT_BASE_URL}/wikis/WIKI/{encoded}"
    print(f"[iFixit] Fetching wiki by title: {url}", flush=True)

    try:
        response = requests.get(
            url, timeout=IFIXIT_TIMEOUT, headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        data = response.json()
        raw = safe_text(data.get("contents_raw", ""))
        wiki_url = safe_text(data.get("url", ""))
        if raw:
            cleaned = _clean_wiki_markup(raw)
            print(f"[iFixit] Wiki content fetched: {len(cleaned)} chars", flush=True)
            return cleaned, wiki_url
    except Exception as exc:
        print(f"[iFixit] Wiki title fetch failed: {exc}", flush=True)
    return "", ""


def _parse_ifixit_url(url: str) -> dict:
    """Extract wiki/guide identifiers from an iFixit URL.

    Returns a dict with 'type' (wiki_id, wiki_title, guide_id) and
    the corresponding 'value', or empty dict if unparsable.
    """
    url = unquote(url)

    # /Troubleshooting/.../ID  or  /Wiki/.../ID
    m = re.search(r"ifixit\.com/(?:Troubleshooting|Wiki)/[^?#]+?/(\d+)$", url)
    if m:
        return {"type": "wiki_id", "value": int(m.group(1))}

    # /Wiki/Title (no trailing numeric ID)
    m = re.search(r"ifixit\.com/Wiki/([^?#/]+)$", url)
    if m:
        return {"type": "wiki_title", "value": m.group(1).replace("+", " ").replace("_", " ")}

    # /Guide/Title/ID
    m = re.search(r"ifixit\.com/Guide/[^/]+/(\d+)", url)
    if m:
        return {"type": "guide_id", "value": int(m.group(1))}

    return {}


def search_ifixit_via_web(query: str) -> dict:
    """Search DuckDuckGo for 'site:ifixit.com {query}', pick the top
    troubleshooting/wiki/guide result, and fetch its content via the API.

    Returns a dict with 'title', 'content', 'url' on success, or empty dict.
    """
    search_query = f"site:ifixit.com {query}"
    print(f"[iFixit] Web search: \"{search_query}\"", flush=True)

    try:
        ddgs = DDGS()
        results = ddgs.text(search_query, max_results=5)
    except Exception as exc:
        print(f"[iFixit] Web search failed: {exc}", flush=True)
        return {}

    if not results:
        print("[iFixit] Web search returned no results", flush=True)
        return {}

    # Prioritise troubleshooting/wiki pages over Q&A answer pages
    preferred = []
    fallback = []
    for r in results:
        href = r.get("href", "")
        if "/Answers/" in href:
            fallback.append(r)
        elif "ifixit.com" in href:
            preferred.append(r)

    ranked = preferred + fallback
    for r in ranked:
        href = r.get("href", "")
        title = r.get("title", "")
        print(f"[iFixit] Web result: {title}  ->  {href}", flush=True)

        parsed = _parse_ifixit_url(href)
        if not parsed:
            continue

        content = ""
        wiki_url = href
        if parsed["type"] == "wiki_id":
            content = fetch_wiki_content(parsed["value"])
        elif parsed["type"] == "wiki_title":
            content, api_url = fetch_wiki_by_title(parsed["value"])
            wiki_url = api_url or href
        elif parsed["type"] == "guide_id":
            content = _fetch_guide_content(parsed["value"])

        if content:
            print(f"[iFixit] Web search matched: \"{title}\" ({len(content)} chars)", flush=True)
            return {"title": title, "content": content, "url": wiki_url}

    print("[iFixit] Web search found no usable content", flush=True)
    return {}


def _fetch_guide_content(guide_id: int) -> str:
    """Fetch a step-by-step guide by ID and return a readable summary."""
    url = f"{IFIXIT_BASE_URL}/guides/{guide_id}"
    print(f"[iFixit] Fetching guide by ID: {url}", flush=True)

    try:
        resp = requests.get(url, timeout=IFIXIT_TIMEOUT, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()

        parts = []
        intro = safe_text(data.get("introduction_rendered", ""))
        if intro:
            intro_clean = re.sub(r"<[^>]+>", "", intro)
            parts.append(intro_clean.strip())

        for step in data.get("steps", []):
            lines = step.get("lines", [])
            text_parts = [safe_text(ln.get("text_rendered", "")) for ln in lines]
            combined = " ".join(re.sub(r"<[^>]+>", "", t) for t in text_parts if t)
            if combined.strip():
                parts.append(f"- {combined.strip()}")

        content = "\n".join(parts)
        print(f"[iFixit] Guide content fetched: {len(content)} chars", flush=True)
        return content
    except Exception as exc:
        print(f"[iFixit] Guide fetch failed: {exc}", flush=True)
        return ""


def find_device_category(query: str) -> dict:
    """Use /suggest/ to resolve a device name to its iFixit category.

    Picks the category whose title is the shortest superset of the
    query words, so "Xbox One" matches "Xbox One" over
    "Xbox One Wireless Controller Model 1708".
    """
    words = safe_text(query).split()
    if not words:
        return {}

    candidates = []
    if len(words) >= 3:
        candidates.append(" ".join(words[:3]))
    if len(words) >= 2:
        candidates.append(" ".join(words[:2]))
    candidates.append(query)

    seen = set()
    unique = [c for c in candidates if not (c in seen or seen.add(c))]

    for candidate in unique:
        encoded = quote(candidate)
        url = f"{IFIXIT_BASE_URL}/suggest/{encoded}?doctypes=category"
        print(f"[iFixit] Suggest lookup: \"{candidate}\"", flush=True)

        try:
            resp = requests.get(
                url, timeout=IFIXIT_TIMEOUT, headers={"Accept": "application/json"}
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            wiki_results = [
                r for r in results if r.get("dataType") == "wiki"
            ]
            if not wiki_results:
                continue

            candidate_lower = candidate.lower()
            best = None
            best_len = float("inf")
            for r in wiki_results:
                title = safe_text(r.get("title", ""))
                title_lower = title.lower()
                if candidate_lower in title_lower and len(title) < best_len:
                    best = title
                    best_len = len(title)

            if not best:
                best = safe_text(wiki_results[0].get("title", ""))

            print(f"[iFixit] Found device category: \"{best}\"", flush=True)
            return {"title": best}
        except Exception as exc:
            print(f"[iFixit] Suggest failed: {exc}", flush=True)
            continue

    print("[iFixit] No device category found via suggest", flush=True)
    return {}


def find_troubleshooting_wikis(category_title: str) -> list:
    """Fetch a device's category page and parse its troubleshooting wiki links."""
    encoded = quote(category_title.replace(" ", "_"))
    url = f"{IFIXIT_BASE_URL}/wikis/CATEGORY/{encoded}"
    print(f"[iFixit] Fetching category page: {url}", flush=True)

    try:
        resp = requests.get(
            url, timeout=IFIXIT_TIMEOUT, headers={"Accept": "application/json"}
        )
        resp.raise_for_status()
        raw = safe_text(resp.json().get("contents_raw", ""))

        wiki_links = re.findall(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]", raw)
        wikis = []
        for wiki_key, display in wiki_links:
            name = safe_text(display or wiki_key)
            key = safe_text(wiki_key)
            if name:
                wikis.append({"title": name, "wiki_key": key})

        print(f"[iFixit] Found {len(wikis)} wiki links in category page", flush=True)
        for w in wikis:
            print(f"[iFixit]   - {w['title']}", flush=True)
        return wikis

    except Exception as exc:
        print(f"[iFixit] Category page fetch failed: {exc}", flush=True)
        return []


def match_troubleshooting_wiki(wikis: list, problem: str) -> dict:
    """Use the LLM to pick the best matching troubleshooting wiki."""
    if not wikis:
        return {}

    titles = [w["title"] for w in wikis]
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))

    print(f"[iFixit] Asking AI to match problem to wiki titles...", flush=True)

    system_prompt = (
        "You match a user's device problem to the most relevant troubleshooting wiki page.\n"
        "You will be given a numbered list of wiki page titles and a problem description.\n"
        "Return ONLY the number of the best matching title.\n"
        "If none are relevant, return 0.\n"
        "Do NOT explain your reasoning. Output ONLY the number."
    )
    user_prompt = f"Wiki pages:\n{numbered}\n\nProblem: {problem}"

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=5,
            temperature=0,
        )

        raw = response.choices[0].message.content
        if raw is None:
            print("[iFixit] AI match returned empty, using fallback", flush=True)
            return _fallback_match_wiki(wikis, problem)

        choice = safe_text(raw).strip(".")
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(wikis):
                print(f"[iFixit] AI matched wiki: \"{wikis[idx]['title']}\"", flush=True)
                return wikis[idx]

        if choice == "0":
            print("[iFixit] AI found no matching wiki", flush=True)
            return {}

        print(f"[iFixit] AI returned unexpected: \"{choice}\", using fallback", flush=True)
        return _fallback_match_wiki(wikis, problem)

    except Exception as exc:
        print(f"[iFixit] AI match failed, using fallback: {exc}", flush=True)
        return _fallback_match_wiki(wikis, problem)


def _fallback_match_wiki(wikis: list, problem: str) -> dict:
    """Simple word-overlap fallback when the LLM match fails."""
    problem_words = set(problem.lower().split())
    best = None
    best_score = 0

    for wiki in wikis:
        title_lower = wiki["title"].lower()
        title_words = set(title_lower.split())
        score = len(problem_words & title_words) * 2

        if "general" in title_lower or title_lower.endswith("troubleshooting"):
            score -= 3

        if score > best_score:
            best_score = score
            best = wiki

    if best and best_score > 0:
        print(f"[iFixit] Fallback matched wiki: \"{best['title']}\" (score: {best_score})", flush=True)
        return best

    print("[iFixit] Fallback found no matching wiki", flush=True)
    return {}


def normalize_ifixit_results(raw_data: dict, query: str) -> list:
    raw_results = raw_data.get("results", [])
    normalized = []

    query_lower = safe_text(query).lower()

    for item in raw_results:
        if not isinstance(item, dict):
            continue

        title = safe_text(item.get("title"))
        summary = safe_text(item.get("summary")) or safe_text(item.get("text"))
        url = safe_text(item.get("url"))
        result_type = safe_text(item.get("dataType")).lower() or "unknown"

        combined = f"{title} {summary}".lower()
        score = 0
        if result_type == "wiki":
            score += 10
        elif result_type == "guide":
            score += 10
        elif result_type == "device":
            score -= 2

        if query_lower in combined:
            score += 8

        query_words = query_lower.split()
        for word in query_words:
            if word in combined:
                score += 1

        variant_keywords = ["pro", "max", "mini", "plus", "ultra"]
        for variant in variant_keywords:
            if variant in combined and variant not in query_lower:
                score -= 2

        if "replacement" in combined:
            score += 2
        if "repair" in combined:
            score += 1
        if result_type:
            score += 1

        normalized.append({
            "title": title or "Untitled",
            "summary": summary,
            "url": url,
            "type": result_type,
            "score": score,
            "wikiid": item.get("wikiid"),
            "wiki_content": "",
        })

    normalized.sort(key=lambda x: x["score"], reverse=True)
    top_results = normalized[:3]

    for result in top_results:
        wikiid = result.get("wikiid")
        if result["type"] in ("wiki", "guide") and wikiid:
            result["wiki_content"] = fetch_wiki_content(wikiid)

    return top_results


def format_ifixit_context(results: list, query: str, error: str = None) -> str:
    if error:
        return f"iFixit Repair Knowledge:\nLookup failed: {error}\n\n"

    if not results:
        return (
            "iFixit Repair Knowledge:\n"
            f"Search Query Used: {query}\n"
            "No device-specific iFixit results were found.\n\n"
        )

    context = "iFixit Repair Knowledge:\n"
    context += f"Search Query Used: {query}\n"
    context += "Relevant iFixit Results:\n"

    for idx, result in enumerate(results, start=1):
        context += (
            f"{idx}. Title: {result['title']}\n"
            f"   Type: {result['type']}\n"
            f"   Summary: {result['summary']}\n"
            f"   URL: {result['url']}\n"
        )
        if result.get("wiki_content"):
            context += f"   Guide Content:\n{result['wiki_content']}\n"

    context += "\n"
    return context


def get_ifixit_context(user, message: str, current_order_id=None) -> dict:
    no_context = {
        "context": "iFixit Repair Knowledge:\nNot used for this message.\n\n",
        "source_url": "",
        "source_title": "",
    }

    order_context = get_order_device_context(user, current_order_id)
    query = extract_search_query(message, order_context)
    if not query:
        no_context["context"] = "iFixit Repair Knowledge:\nNo usable search query could be built.\n\n"
        print("[iFixit] No query built", flush=True)
        return no_context

    print(f"[iFixit] Using LLM-extracted query: \"{query}\"", flush=True)

    # --- Primary: Web search via DuckDuckGo ---
    web_result = search_ifixit_via_web(query)
    if web_result:
        context = "iFixit Repair Knowledge:\n"
        context += f"Search Query Used: {query}\n"
        context += f"Matched Guide: {web_result['title']}\n"
        context += f"Guide Content:\n{web_result['content']}\n\n"

        print("[iFixit] Final context injected into prompt:", flush=True)
        for line in context.splitlines():
             print(f"[iFixit] {line}", flush=True)
        print(context, flush=True)
        return {
            "context": context,
            "source_url": web_result.get("url", ""),
            "source_title": web_result.get("title", ""),
        }

    # --- Fallback 1: Category-based approach via /suggest/ ---
    print("[iFixit] Web search did not find a guide, trying category-based approach...", flush=True)
    category = find_device_category(query)
    if category:
        wikis = find_troubleshooting_wikis(category["title"])
        if wikis:
            matched = match_troubleshooting_wiki(wikis, query)
            if matched:
                content, wiki_url = fetch_wiki_by_title(matched["wiki_key"])
                if content:
                    context = "iFixit Repair Knowledge:\n"
                    context += f"Search Query Used: {query}\n"
                    context += f"Device: {category['title']}\n"
                    context += f"Matched Guide: {matched['title']}\n"
                    context += f"Guide Content:\n{content}\n\n"

                    print("[iFixit] Final context injected into prompt:", flush=True)
                    print(context, flush=True)
                    return {
                        "context": context,
                        "source_url": wiki_url or "",
                        "source_title": matched["title"],
                    }

    # --- Fallback 2: Search-based approach via /search/ ---
    print("[iFixit] Category approach also failed, falling back to /search/", flush=True)
    raw_data = search_ifixit(query)
    error = raw_data.get("error")
    results = normalize_ifixit_results(raw_data, query)
    context = format_ifixit_context(results, query, error)

    print("[iFixit] Final context injected into prompt:", flush=True)
    print(context, flush=True)

    return {
        "context": context,
        "source_url": results[0].get("url", "") if results else "",
        "source_title": results[0].get("title", "") if results else "",
    }
