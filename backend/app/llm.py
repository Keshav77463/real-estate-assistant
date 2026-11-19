import os, re, requests
from .vocab import ALIASES, canon_key

SYSTEM = ("You are a professional real estate assistant for DarGlobal and Wasalt. "
          "Answer using ONLY the provided context. Each property entry starts with a metadata line "
          "(Title, Location, Type, Bedrooms, Area, Price, Status, Amenities) followed by page text; use those "
          "values and never invent amenities, brands, prices or dates that are not stated there. "
          "When Bedrooms lists multiple options, report every listed option; do not reduce it to one number. "
          "Present EVERY property in exactly this consistent format, one field per line:\n\n"
          "## <Property name>\n"
          "- **Location:** city, country\n"
          "- **Type:** property type\n"
          "- **Developer:** developer or brand when stated\n"
          "- **Bedrooms:** bedrooms\n"
          "- **Area:** size when stated\n"
          "- **Price:** amount with currency exactly as stated, or 'Not stated'\n"
          "- **Status:** development or sale status\n"
          "- **Amenities:** comma-separated amenities from the metadata and page text\n"
          "- **Source:** the exact URL given in the context entry's parentheses\n\n"
          "This property format is mandatory for every answer that has matching property context. "
          "Never stop after the introductory sentence; always include the property section(s). "
          "If a field is not present in the context, write 'Not stated' for that field. "
          "If the question asks something specific (amenities, price, status, comparison), begin with one "
          "short sentence answering it, then give the property sections. Order multiple properties by "
          "relevance to the request. If the user names a specific property, present only that property. "
          "Use plain ASCII: no tables, no emoji, no en/em dashes. "
          "If no property satisfies the requested criteria (location, currency, budget, bedrooms), say so "
          "clearly and name the criterion that failed instead of listing mismatched properties.")

RETRYABLE = {429, 500, 502, 503, 504}

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = [os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b",
               "qwen/qwen3.8-27b",
               "openai/gpt-oss-20b"]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [os.getenv("OPENROUTER_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b:free",
                     "nvidia/nemotron-3.5-lightning:free",
                     "inclusionai/ling-3.2-flash:free"]


def _post_groq(model, messages, strict_json=True):
    payload = {"model": model, "messages": messages, "max_tokens": 1200, "temperature": 0.2}
    if strict_json and "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
    elif strict_json and "qwen" in model:
        payload["reasoning_effort"] = "none"
    return requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json=payload,
        timeout=(10, 90))


def _post_openrouter(model, messages, strict_json=True):
    payload = {"model": model, "messages": messages}
    if strict_json:
        payload["reasoning"] = {"enabled": False}
        payload["max_tokens"] = 1200
    return requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json=payload,
        timeout=(10, 90))


def _providers():
    providers = []
    if os.getenv("GROQ_API_KEY"):
        providers += [("groq", m) for m in dict.fromkeys(GROQ_MODELS)]
    if os.getenv("OPENROUTER_API_KEY"):
        providers += [("openrouter", m) for m in dict.fromkeys(OPENROUTER_MODELS)]
    return providers


def _ensure_specific_property_section(answer, question, context):
    if re.search(r"^##\s+", answer, re.M) or not context:
        return answer

    def tokens(text):
        return {word.rstrip("s") for word in re.findall(r"[a-z0-9]+", text.lower())
                if len(word) > 2}

    question_tokens = tokens(question)
    ranked = [(len(question_tokens & tokens(title)), item)
              for item in context for title in [item[1]]]
    score, (content, title, url, _) = max(ranked, key=lambda match: match[0])
    if score == 0:
        return answer

    lines = (content or "").split("\n\n", 1)[0].splitlines()
    header = lines[0] if lines else ""
    fields = {}
    for part in header.split(" | "):
        if ": " in part:
            key, value = part.split(": ", 1)
            fields[key.strip().lower()] = value.strip()

    def value(*keys):
        return next((fields[key] for key in keys if fields.get(key)), "Not stated")

    area_value = value("area")
    if area_value == "Not stated":
        area = re.search(
            r"\b(?:built[- ]?up area|area|spanning)\s*(?:of|:)?\s*"
            r"([\d,.]+)\s*(sqm|sq\.?\s*m|m²|sqft|sq\.?\s*ft)\b",
            content or "", re.I,
        )
        area_value = f"{area.group(1)} {area.group(2).upper()}" if area else "Not stated"
    section = (
        f"## {title}\n"
        f"- **Location:** {value('location')}\n"
        f"- **Type:** {value('type')}\n"
        f"- **Developer:** {value('developer', 'brand')}\n"
        f"- **Bedrooms:** {value('bedrooms')}\n"
        f"- **Area:** {area_value}\n"
        f"- **Price:** {value('price')}\n"
        f"- **Status:** {value('status')}\n"
        f"- **Amenities:** {value('amenities')}\n"
        f"- **Source:** {url}"
    )
    return f"{answer.rstrip()}\n\n{section}"


def _deduplicate_property_sections(answer):
    preamble, sections, current = [], [], None
    for line in answer.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append(current)
            current = [line]
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    if current is not None:
        sections.append(current)

    seen_sources, unique_sections = set(), []
    for section in sections:
        match = re.search(r"^\s*[-*]\s*\*\*Source:\*\*\s*(\S+)", "\n".join(section), re.I | re.M)
        key = canon_key(match.group(1)) if match else None
        if key and key in seen_sources:
            continue
        if key:
            seen_sources.add(key)
        unique_sections.append("\n".join(section))

    parts = ["\n".join(preamble).rstrip()] if any(line.strip() for line in preamble) else []
    parts.extend(unique_sections)
    return "\n\n".join(parts)


def _prior_user_messages(question, history):
    is_follow_up = (
        re.search(r"\b(it|its|they|them|those|these|that|there|same)\b", question, re.I)
        or re.match(r"\s*(?:what|how)\s+about\b", question, re.I)
    )
    if not is_follow_up:
        return []
    return [message for message in history if message.get("role") == "user"][-3:]


def ask(question, context, history):
    ctx = "\n\n".join(f"[{i+1}] {t} ({u})\n{c}" for i, (c, t, u, _) in enumerate(context))
    messages = [{"role": "system", "content": SYSTEM}, *_prior_user_messages(question, history),
                {"role": "user", "content": (
                    "Current-turn property context is authoritative. Previous user questions may help "
                    "resolve references, but never use them to add or change property facts for this answer.\n"
                    f"Context:\n{ctx}\n\nQuestion: {question}"
                )}]
    last_error = None
    for provider, model in _providers():
        post = _post_groq if provider == "groq" else _post_openrouter
        try:
            r = post(model, messages)
            if r.status_code == 400:
                r = post(model, messages, strict_json=False)
        except requests.RequestException:
            continue
        if r.status_code in RETRYABLE:
            last_error = r
            continue
        r.raise_for_status()
        content = (r.json()["choices"][0]["message"].get("content") or "").strip()
        if content:
            for old, new in ALIASES.items():
                content = content.replace(old, new)
            content = _deduplicate_property_sections(content)
            return _ensure_specific_property_section(content, question, context)
    if last_error is not None:
        last_error.raise_for_status()
    raise RuntimeError("All configured LLM models returned empty responses")
