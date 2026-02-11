"""
analyzer.py — Content intelligence: sentiment analysis,
emotion detection, topic extraction, and audio matching.
No heavy ML — uses VADER + keyword heuristics.
"""

import json
import re
from pathlib import Path
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from config import AUDIO_LIBRARY_PATH

_vader = SentimentIntensityAnalyzer()


# ══════════════════════════════════════════════════════════════
#  SENTIMENT ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_sentiment(text: str) -> dict:
    """Return compound score + label."""
    scores = _vader.polarity_scores(text)
    compound = scores["compound"]

    if compound >= 0.5:
        label = "very_positive"
    elif compound >= 0.1:
        label = "positive"
    elif compound <= -0.5:
        label = "very_negative"
    elif compound <= -0.1:
        label = "negative"
    else:
        label = "neutral"

    return {
        "compound": round(compound, 3),
        "positive": round(scores["pos"], 3),
        "negative": round(scores["neg"], 3),
        "neutral": round(scores["neu"], 3),
        "label": label,
    }


# ══════════════════════════════════════════════════════════════
#  EMOTION DETECTION  (keyword-based, fast)
# ══════════════════════════════════════════════════════════════

_EMOTION_WORDS = {
    "happy": [
        "happy", "joy", "excited", "celebrate", "amazing", "wonderful",
        "great", "love", "fantastic", "brilliant", "thrilled", "delighted",
        "breakthrough", "success", "win", "congratulations", "proud",
    ],
    "sad": [
        "sad", "loss", "mourning", "passed away", "tragic", "unfortunately",
        "grief", "sorrow", "miss", "death", "memorial", "remembering",
        "heartbreaking", "devastating", "farewell",
    ],
    "angry": [
        "angry", "outrage", "furious", "unacceptable", "disgusting",
        "terrible", "worst", "scandal", "corrupt", "shameful", "infuriating",
    ],
    "fear": [
        "fear", "danger", "warning", "urgent", "emergency", "threat",
        "risk", "safety", "recall", "crisis", "alarming", "breaking",
    ],
    "surprise": [
        "surprise", "unexpected", "shocking", "breaking", "unbelievable",
        "suddenly", "revealed", "unprecedented", "stunning", "wow",
    ],
}


def detect_emotions(text: str) -> dict:
    """Score each emotion 0-1 based on keyword density."""
    text_lower = text.lower()
    words = re.findall(r"\w+", text_lower)
    word_count = max(len(words), 1)

    scores = {}
    for emotion, keywords in _EMOTION_WORDS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        scores[emotion] = round(min(hits / 5, 1.0), 2)  # cap at 1.0

    # pick primary and secondary
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = ranked[0][0] if ranked[0][1] > 0 else "neutral"
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 0 else "neutral"

    return {
        "scores": scores,
        "primary": primary,
        "secondary": secondary,
    }


# ══════════════════════════════════════════════════════════════
#  TOPIC / KEYWORD EXTRACTION  (regex-based, no spaCy)
# ══════════════════════════════════════════════════════════════

_TOPIC_KEYWORDS = {
    "technology": ["ai", "tech", "software", "digital", "computer", "data", "app", "algorithm", "robot", "machine learning"],
    "science": ["research", "study", "scientist", "discovery", "experiment", "lab", "theory"],
    "business": ["company", "market", "stock", "revenue", "startup", "ceo", "investor", "profit"],
    "health": ["health", "medical", "doctor", "hospital", "vaccine", "disease", "wellness"],
    "entertainment": ["movie", "music", "film", "celebrity", "concert", "show", "streaming"],
    "sports": ["game", "team", "player", "championship", "league", "score", "coach"],
    "politics": ["government", "election", "president", "policy", "vote", "congress", "law"],
    "lifestyle": ["travel", "food", "fashion", "fitness", "recipe", "adventure", "home"],
    "environment": ["climate", "environment", "green", "sustainability", "carbon", "ocean"],
    "safety": ["recall", "warning", "danger", "safety", "emergency", "urgent", "alert"],
}


def extract_topics(text: str) -> list[str]:
    """Return list of matched topic categories."""
    text_lower = text.lower()
    matched = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(topic)
    return matched if matched else ["general"]


def extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """Pull out significant words (length > 5, not stop-words)."""
    stop = {
        "about", "after", "again", "their", "there", "these", "those",
        "which", "would", "could", "should", "being", "other", "where",
        "under", "between", "through", "before", "during", "without",
    }
    words = re.findall(r"[a-zA-Z]{5,}", text.lower())
    filtered = [w for w in words if w not in stop]
    # rank by frequency
    freq = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in ranked[:top_n]]


# ══════════════════════════════════════════════════════════════
#  FULL CONTENT ANALYSIS  (single entry-point)
# ══════════════════════════════════════════════════════════════

def analyze_content(text: str) -> dict:
    """Run all analyses and return a combined result dict."""
    sentiment = analyze_sentiment(text)
    emotions = detect_emotions(text)
    topics = extract_topics(text)
    keywords = extract_keywords(text)

    return {
        "sentiment": sentiment,
        "emotions": emotions,
        "topics": topics,
        "keywords": keywords,
    }


# ══════════════════════════════════════════════════════════════
#  AUDIO MATCHING
# ══════════════════════════════════════════════════════════════

# Maps sentiment labels → desired audio moods
_MOOD_MAP = {
    "very_positive": {"want": ["happy", "energetic", "inspirational", "upbeat"], "avoid": ["sad", "dark"]},
    "positive":      {"want": ["happy", "upbeat", "inspirational", "calm"],     "avoid": ["sad", "dark", "dramatic"]},
    "neutral":       {"want": ["calm", "ambient", "inspirational"],             "avoid": ["dramatic", "dark"]},
    "negative":      {"want": ["sad", "calm", "reflective", "emotional"],       "avoid": ["happy", "energetic", "upbeat"]},
    "very_negative": {"want": ["sad", "dramatic", "emotional", "reflective"],   "avoid": ["happy", "energetic", "upbeat", "party"]},
}

# Emotion overrides (take priority when emotion is strong)
_EMOTION_MOOD_OVERRIDE = {
    "angry":    {"want": ["dramatic", "energetic", "intense"], "genres": ["rock", "hip-hop", "electronic"]},
    "fear":     {"want": ["dramatic", "tense", "serious"],     "genres": ["cinematic", "electronic"]},
    "surprise": {"want": ["energetic", "upbeat", "dramatic"],  "genres": ["electronic", "pop"]},
}


def _load_audio_library() -> list[dict]:
    if not AUDIO_LIBRARY_PATH.exists():
        return []
    with open(AUDIO_LIBRARY_PATH) as f:
        return json.load(f)


def match_audio(
    sentiment: dict,
    emotions: dict,
    topics: list[str],
    target_platform: str = "any",
) -> list[dict]:
    """
    Return top 3 audio suggestions sorted by match score.
    Each result includes the track metadata + match_score + rationale.
    """
    library = _load_audio_library()
    if not library:
        return []

    label = sentiment.get("label", "neutral")
    mood_prefs = _MOOD_MAP.get(label, _MOOD_MAP["neutral"])
    want_moods = set(mood_prefs["want"])
    avoid_moods = set(mood_prefs["avoid"])

    # emotion override
    primary_emotion = emotions.get("primary", "neutral")
    genre_boost = set()
    if primary_emotion in _EMOTION_MOOD_OVERRIDE:
        override = _EMOTION_MOOD_OVERRIDE[primary_emotion]
        want_moods.update(override["want"])
        genre_boost.update(override.get("genres", []))

    scored = []
    for track in library:
        track_moods = set(track.get("moods", []))
        track_genres = set(track.get("genres", []))

        # skip if platform mismatch
        tp = track.get("platform", "any")
        if target_platform != "any" and tp != "any" and tp != target_platform:
            continue

        # skip if has any avoid mood
        if track_moods & avoid_moods:
            continue

        # ── Score ─────────────────────────────────────
        # mood overlap (0-1) — weight 0.70
        overlap = len(track_moods & want_moods) / max(len(want_moods), 1)
        mood_score = overlap * 0.70

        # trending (0-1) — weight 0.20
        trending = track.get("trending_score", 50) / 100
        trend_score = trending * 0.20

        # genre bonus — weight 0.10
        genre_overlap = len(track_genres & genre_boost) / max(len(genre_boost), 1) if genre_boost else 0.5
        genre_score = genre_overlap * 0.10

        total = round(mood_score + trend_score + genre_score, 3)

        scored.append({
            **track,
            "match_score": total,
            "rationale": {
                "wanted_moods": list(want_moods),
                "matched_moods": list(track_moods & want_moods),
                "trending_score": track.get("trending_score", 0),
            },
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:3]


def suggest_audio_for_content(text: str, platform: str = "any") -> list[dict]:
    """One-call convenience: analyse text → match audio."""
    analysis = analyze_content(text)
    return match_audio(
        sentiment=analysis["sentiment"],
        emotions=analysis["emotions"],
        topics=analysis["topics"],
        target_platform=platform,
    )
