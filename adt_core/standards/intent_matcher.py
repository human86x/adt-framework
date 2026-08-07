import json
import os
import re
from typing import List, Dict, Any, Tuple

ENGINE_VERSION = "keyword_matcher_v2"

def load_intent_index() -> Dict[str, Any]:
    index_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'intent_index.json')
    if not os.path.exists(index_path):
        return {}
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _tokenize(text: str) -> List[str]:
    """Lowercased word tokens plus lowercased whole text for phrase-substring matching."""
    return re.findall(r'\b[\w-]+\b', text.lower())


def _score_domain(tokens: List[str], text_lower: str, keywords: List[str]) -> Tuple[int, float]:
    """Return (match_count, confidence_score) for a domain.

    Match rules:
      - Single-word keyword: hits if it appears in the token list (whole-word match).
      - Multi-word keyword: hits if the phrase appears as a substring in text_lower.
      - Confidence = matched_kw / total_kw (capped at 1.0). Ranges 0..1.
    """
    if not keywords:
        return 0, 0.0
    match_count = 0
    for kw in keywords:
        kw_norm = kw.lower().strip()
        if not kw_norm:
            continue
        if ' ' in kw_norm or '-' in kw_norm and '_' not in kw_norm:
            # Phrase or hyphenated compound: substring match
            if kw_norm in text_lower:
                match_count += 1
        else:
            # Whole-word match against tokens
            if kw_norm in tokens:
                match_count += 1
    confidence = min(1.0, match_count / max(1, len(keywords)))
    return match_count, round(confidence, 3)


def match_intent_domain(intent_text: str) -> Tuple[List[str], List[str]]:
    """Legacy interface — returns matching domain keys and suggested baseline_rr_ids.

    Broad-match: returns every domain whose confidence >= threshold
    (env ADT_INTENT_MATCH_THRESHOLD, default 0.15). Empty matches are valid.
    """
    result = match_intent_domain_detailed(intent_text)
    return result["matched_domains"], result["suggested_rr_ids"]


def match_intent_domain_detailed(intent_text: str) -> Dict[str, Any]:
    """Detailed interface used by MRR event logging.

    Returns:
      {
        matched_domains: [domain_key, ...]  -- sorted by confidence desc
        baseline_rr_ids: [rr_id, ...]       -- deduplicated union
        suggested_rr_ids: [rr_id, ...]      -- alias of baseline (for demo clarity)
        match_confidence_per_domain: {domain_key: 0.0..1.0}
        engine_version: str
      }
    """
    index = load_intent_index()
    empty = {
        "matched_domains": [],
        "baseline_rr_ids": [],
        "suggested_rr_ids": [],
        "match_confidence_per_domain": {},
        "engine_version": ENGINE_VERSION,
    }
    if not index or 'domains' not in index:
        return empty

    try:
        threshold = float(os.environ.get("ADT_INTENT_MATCH_THRESHOLD", "0.15"))
    except (TypeError, ValueError):
        threshold = 0.15

    text_lower = intent_text.lower() if intent_text else ""
    tokens = _tokenize(text_lower)

    scored: List[Tuple[str, int, float, List[str]]] = []
    for domain_key, domain_data in index['domains'].items():
        keywords = domain_data.get('keywords', []) or []
        count, confidence = _score_domain(tokens, text_lower, keywords)
        if count > 0 and confidence >= threshold:
            scored.append((domain_key, count, confidence, domain_data.get('baseline_rr_ids', []) or []))

    # Sort by confidence descending then match count
    scored.sort(key=lambda x: (x[2], x[1]), reverse=True)

    matched_domains: List[str] = []
    baseline_rr_ids: List[str] = []
    confidence_map: Dict[str, float] = {}
    for domain_key, _count, confidence, rr_ids in scored:
        matched_domains.append(domain_key)
        confidence_map[domain_key] = confidence
        for rr in rr_ids:
            if rr not in baseline_rr_ids:
                baseline_rr_ids.append(rr)

    return {
        "matched_domains": matched_domains,
        "baseline_rr_ids": baseline_rr_ids,
        "suggested_rr_ids": list(baseline_rr_ids),
        "match_confidence_per_domain": confidence_map,
        "engine_version": ENGINE_VERSION,
    }
