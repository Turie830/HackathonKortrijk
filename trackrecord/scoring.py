"""The rules that turn usage signals into a track record for every PARALLAX source.

Every judgement here is deterministic and explainable. No model decides.

Find it       -> doubt before a usable source is found   (see gaps())
Understand it -> doubt after reading a source            (doubt rate)
Trust it      -> what happened after the source was used (failure rate)

Rates are recency-weighted, smoothed towards the typical source and only judged
with enough evidence. A source or context segment is never shown with fewer
than MIN_USERS distinct people behind it.
"""
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import knowledge

HALF_LIFE_DAYS = 90        # a use from 90 days ago counts half
RECENT_DAYS = 90           # "recently worse" (e.g. after a rule change) is its own segment
PRIOR_STRENGTH = 10        # smoothing: behave as if we saw 10 average uses
MIN_USES = 5               # below this: "nog geen trackrecord"
MIN_USERS = 5              # privacy: never show numbers backed by fewer people
HIGH_FACTOR = 1.5          # "high" means above 1.5x the organisation average
CONFIDENCE = 0.90          # required probability that a rate is really high
SEGMENT_MIN_DIFF = 0.15    # a context segment must differ by at least 15 points
SEGMENT_CONFIDENCE = 0.95
DOUBT_WINDOW = timedelta(minutes=15)
MIN_DWELL_SECONDS = 10     # shorter than this is a bounce (findability), not a read
PERSON_MONTHLY_CAP = 10    # one person counts at most 10 uses and 10 reads per version per month
GAP_WINDOW_DAYS = 90
GAP_MIN_SESSIONS = 8
GAP_MIN_TEAMS_SHARE = 0.4

SEGMENT_DIMENSIONS = [("statute", "Statuut"), ("pc", "Paritair comité"), ("country", "Land"),
                      ("size", "Klantgrootte"), ("period", "Periode")]
PERIOD_LABELS = {"recent": f"laatste {RECENT_DAYS} dagen", "eerder": "daarvoor"}
QUADRANTS = {
    "dangerous": "Gevaarlijk",
    "broken": "Kapot",
    "unclear": "Onduidelijk",
    "reliable": "Betrouwbaar",
    "insufficient": "Nog geen trackrecord",
}
PRIORITY = {"dangerous": 4, "broken": 3, "unclear": 2, "reliable": 0, "insufficient": 0}


# --- statistics ---------------------------------------------------------------------------

def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Numerical Recipes)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for numerator in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                          -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            delta = d * c
            h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def beta_cdf(x, a, b):
    """P(X <= x) for X ~ Beta(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_front = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(log_front) * _betacf(a, b, x) / a
    return 1.0 - math.exp(log_front) * _betacf(b, a, 1.0 - x) / b


class Rate:
    """Recency-weighted successes/failures of one document or segment."""

    def __init__(self):
        self.hits = 0.0      # weighted failures (or doubts)
        self.total = 0.0     # weighted uses (or reads)
        self.n = 0           # raw count
        self.raw_hits = 0
        self.users = set()

    def add(self, weight, hit, user):
        self.hits += weight * hit
        self.total += weight
        self.n += 1
        self.raw_hits += int(hit)
        self.users.add(user)

    def posterior(self, prior, smooth=True):
        strength = PRIOR_STRENGTH if smooth else 1.0
        return self.hits + strength * prior, (self.total - self.hits) + strength * (1 - prior)

    def rate(self, prior, smooth=True):
        if not smooth:
            return self.hits / self.total if self.total else 0.0
        a, b = self.posterior(prior)
        return a / (a + b)

    def prob_above(self, threshold, prior, smooth=True):
        a, b = self.posterior(prior, smooth)
        return 1.0 - beta_cdf(min(threshold, 0.999), a, b)

    def enough(self):
        return self.n >= MIN_USES and len(self.users) >= MIN_USERS


def prob_greater(first, second, prior):
    """P(rate of first > rate of second), normal approximation of two Beta posteriors."""
    (a1, b1), (a2, b2) = first.posterior(prior), second.posterior(prior)
    m1, m2 = a1 / (a1 + b1), a2 / (a2 + b2)
    v1 = a1 * b1 / ((a1 + b1) ** 2 * (a1 + b1 + 1))
    v2 = a2 * b2 / ((a2 + b2) ** 2 * (a2 + b2 + 1))
    return 0.5 * (1 + math.erf((m1 - m2) / math.sqrt(2 * (v1 + v2))))


# --- loading ------------------------------------------------------------------------------

def _parse(text):
    return datetime.fromisoformat(text)


def _weight(moment, as_of, recency):
    if not recency:
        return 1.0
    age = max(0, (as_of - moment.date()).days)
    return 0.5 ** (age / HALF_LIFE_DAYS)


def load_sources(db, as_of):
    """PARALLAX sources as track-record units. A new version (supersedes) starts a new track record."""
    sources = {source["id"]: source for source in
               (json.loads(row["payload"]) for row in db.execute("SELECT payload FROM sources"))}
    successors = defaultdict(list)
    for source in sources.values():
        for old in source.get("supersedes", []):
            successors[old].append(source)
    info = {}
    for source_id, source in sources.items():
        root, version, seen = source_id, 1, set()
        while sources[root].get("supersedes") and sources[root]["supersedes"][0] in sources and root not in seen:
            seen.add(root)
            root, version = sources[root]["supersedes"][0], version + 1
        replaced = any(other["approved"] and date.fromisoformat(other["valid_from"]) <= as_of
                       for other in successors[source_id])
        info[source_id] = {
            "id": source_id, "document_id": root, "version": version,
            "is_current": knowledge.valid_at(source, as_of) and not replaced,
            "published_at": source["valid_from"], "title": source["title"], "topic": source.get("topic"),
            "country": source["country"], "client_id": source["client_id"], "statute": source.get("statute", "ALL"),
            "owner": source["owner"] or "Geen bronhouder", "owner_team": source["owner"],
            "approved": source["approved"], "kind": source["kind"],
            "successors": [other["id"] for other in successors[source_id]],
        }
    return info


def _load_events(db, cutoff):
    return db.execute("""
        SELECT e.session_id, s.ticket_id, e.pseudo_user, e.at, e.type, e.source_id, e.text, e.dwell_seconds,
               t.statute, t.topic, c.country, c.pc, c.size, o.result, o.comment, o.at AS outcome_at
        FROM events e
        JOIN work_sessions s ON s.id = e.session_id
        LEFT JOIN tickets t ON t.id = s.ticket_id
        LEFT JOIN clients c ON c.id = t.client_id
        LEFT JOIN outcomes o ON o.ticket_id = t.id
        WHERE e.at <= ? ORDER BY e.session_id, e.at, e.id""", (cutoff,)).fetchall()


# --- the track record -------------------------------------------------------------------

def compute(db, as_of, recency=True, smooth=True, min_evidence=True):
    """Score every source as of a date. Flags exist only for the evaluation's ablations."""
    cutoff = f"{as_of.isoformat()}T23:59:59"
    versions = load_sources(db, as_of)
    stats = {vid: {"fail": Rate(), "doubt": Rate(), "bounces": 0, "pending": 0, "segments": defaultdict(Rate),
                   "failures": [], "follow_ups": [], "months": defaultdict(lambda: [0, 0, 0, 0])}
             for vid in versions}

    sessions = defaultdict(list)
    for row in _load_events(db, cutoff):
        sessions[row["session_id"]].append(row)
    # Integrity: one ticket outcome counts once per document, and nobody can steer a score alone.
    seen_tickets = set()
    per_person = Counter()

    def over_cap(kind, vid, event):
        key = (kind, vid, event["pseudo_user"], event["at"][:7])
        per_person[key] += 1
        return per_person[key] > PERSON_MONTHLY_CAP

    for events in sessions.values():
        for index, event in enumerate(events):
            vid = event["source_id"]
            if vid not in stats:
                continue
            s = stats[vid]
            moment = _parse(event["at"])
            weight = _weight(moment, as_of, recency)
            if event["type"] == "cite":
                if event["ticket_id"] is None or (vid, event["ticket_id"]) in seen_tickets or over_cap("use", vid, event):
                    continue
                seen_tickets.add((vid, event["ticket_id"]))
                known = event["result"] is not None and event["outcome_at"] <= cutoff
                if not known:
                    s["pending"] += 1
                    continue
                failed = event["result"] != "ok"
                s["fail"].add(weight, failed, event["pseudo_user"])
                context = {dimension: event[dimension] for dimension, _ in SEGMENT_DIMENSIONS if dimension != "period"}
                if recency:
                    context["period"] = "recent" if (as_of - moment.date()).days < RECENT_DAYS else "eerder"
                for dimension, value in context.items():
                    s["segments"][(dimension, value)].add(weight, failed, event["pseudo_user"])
                month = s["months"][event["at"][:7]]
                month[0] += 1
                month[1] += int(failed)
                if failed:
                    s["failures"].append({"result": event["result"], "comment": event["comment"] or "",
                                          "segment": context})
            elif event["type"] == "open":
                if (event["dwell_seconds"] or 0) < MIN_DWELL_SECONDS:
                    s["bounces"] += 1
                    continue
                if over_cap("read", vid, event):
                    continue
                window_end = moment + timedelta(seconds=event["dwell_seconds"]) + DOUBT_WINDOW
                doubt_events = [later for later in events[index + 1:]
                                if _parse(later["at"]) <= window_end and (
                                    later["type"] in ("search", "teams_question", "review_request")
                                    or (later["type"] == "open" and later["source_id"] != vid)
                                    or (later["type"] == "not_helpful" and later["source_id"] == vid))]
                s["doubt"].add(weight, bool(doubt_events), event["pseudo_user"])
                month = s["months"][event["at"][:7]]
                month[2] += 1
                month[3] += int(bool(doubt_events))
                s["follow_ups"] += [later["text"] for later in doubt_events
                                    if later["type"] in ("teams_question", "review_request") and later["text"]]

    # "Normal" is the typical document (median), so a few bad documents cannot raise the bar.
    fail_prior = _typical_rate([s["fail"] for s in stats.values()])
    doubt_prior = _typical_rate([s["doubt"] for s in stats.values()])
    raw_fail_prior = fail_prior
    fail_threshold = HIGH_FACTOR * fail_prior
    doubt_threshold = HIGH_FACTOR * doubt_prior

    results = {}
    for vid, s in stats.items():
        info = versions[vid]
        fail, doubt = s["fail"], s["doubt"]
        enough_fail = fail.enough() if min_evidence else fail.n > 0
        enough_doubt = doubt.enough() if min_evidence else doubt.n > 0
        if smooth and min_evidence:
            fail_high = enough_fail and fail.prob_above(fail_threshold, fail_prior) >= CONFIDENCE
            doubt_high = enough_doubt and doubt.prob_above(doubt_threshold, doubt_prior) >= CONFIDENCE
        else:  # ablation: judge the raw rate, no smoothing, no evidence requirement
            fail_high = enough_fail and fail.rate(fail_prior, False) > fail_threshold
            doubt_high = enough_doubt and doubt.rate(doubt_prior, False) > doubt_threshold

        segment = _worst_segment(s["segments"], fail, fail_prior, fail_threshold) if enough_fail else None
        failing = fail_high or bool(segment and segment["high"])
        if failing and doubt_high:
            quadrant = "broken"
        elif failing:
            quadrant = "dangerous"
        elif doubt_high:
            quadrant = "unclear"
        elif enough_fail:
            quadrant = "reliable"
        else:
            quadrant = "insufficient"

        excess = max(0.0, fail.raw_hits - raw_fail_prior * fail.n)
        results[vid] = {
            **info,
            "quadrant": quadrant,
            "quadrant_label": QUADRANTS[quadrant],
            "uses": fail.n, "fails": fail.raw_hits, "pending": s["pending"], "users": len(fail.users),
            "fail_rate": round(fail.rate(fail_prior, smooth), 4),
            "fail_evidence": round(fail.prob_above(fail_threshold, fail_prior), 3) if fail.n else 0.0,
            "reads": doubt.n, "doubts": doubt.raw_hits,
            "doubt_rate": round(doubt.rate(doubt_prior, smooth), 4),
            "doubt_evidence": round(doubt.prob_above(doubt_threshold, doubt_prior), 3) if doubt.n else 0.0,
            "bounces": s["bounces"],
            "enough_fail": enough_fail, "enough_doubt": enough_doubt,
            "segment": segment,
            "segments": _segment_table(s["segments"], fail_prior),
            "excess_failures": round(excess, 1),
            "priority": PRIORITY[quadrant] * 1000 + excess,
            "failures": s["failures"],
            "follow_ups": _top_texts(s["follow_ups"]),
            "months": {month: dict(zip(("uses", "fails", "reads", "doubts"), values))
                       for month, values in sorted(s["months"].items())},
        }
        results[vid]["reason"] = _reason(results[vid], fail_prior, doubt_prior)

    return {
        "as_of": as_of.isoformat(),
        "versions": results,
        "org": {"fail_rate": round(fail_prior, 4), "doubt_rate": round(doubt_prior, 4),
                "fail_threshold": round(fail_threshold, 4), "doubt_threshold": round(doubt_threshold, 4)},
        "rules": {"half_life_days": HALF_LIFE_DAYS if recency else None, "prior_strength": PRIOR_STRENGTH,
                  "min_uses": MIN_USES, "min_users": MIN_USERS, "high_factor": HIGH_FACTOR,
                  "confidence": CONFIDENCE, "doubt_window_minutes": DOUBT_WINDOW.seconds // 60,
                  "person_monthly_cap": PERSON_MONTHLY_CAP,
                  "min_dwell_seconds": MIN_DWELL_SECONDS},
    }


def _typical_rate(rates):
    """Median weighted rate over documents with enough evidence (pooled rate as fallback)."""
    values = sorted(rate.hits / rate.total for rate in rates if rate.enough() and rate.total)
    if values:
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    hits, total = sum(rate.hits for rate in rates), sum(rate.total for rate in rates)
    return hits / total if total else 0.0


def _worst_segment(segments, overall, prior, threshold):
    """The context in which this document fails clearly more often than elsewhere."""
    best = None
    for (dimension, value), segment in segments.items():
        if not segment.enough():
            continue
        rest = Rate()
        rest.hits, rest.total = overall.hits - segment.hits, overall.total - segment.total
        rest.n, rest.raw_hits = overall.n - segment.n, overall.raw_hits - segment.raw_hits
        if rest.n < MIN_USES:
            continue
        difference = segment.rate(prior) - rest.rate(prior)
        if difference < SEGMENT_MIN_DIFF or prob_greater(segment, rest, prior) < SEGMENT_CONFIDENCE:
            continue
        if best is None or difference > best["difference"]:
            label = dict(SEGMENT_DIMENSIONS)[dimension]
            best = {"dimension": dimension, "dimension_label": label, "value": value,
                    "uses": segment.n, "fails": segment.raw_hits, "users": len(segment.users),
                    "rate": round(segment.rate(prior), 4), "rest_rate": round(rest.rate(prior), 4),
                    "raw": round(segment.raw_hits / segment.n, 4),
                    "rest_raw": round(rest.raw_hits / rest.n, 4),
                    "difference": round(difference, 4),
                    "high": segment.prob_above(threshold, prior) >= CONFIDENCE}
    return best


def _segment_table(segments, prior):
    """All context segments that may be shown (privacy threshold applied)."""
    table = defaultdict(list)
    for (dimension, value), segment in segments.items():
        if segment.enough():
            table[dimension].append({"value": value, "uses": segment.n, "fails": segment.raw_hits,
                                     "rate": round(segment.rate(prior), 4)})
    return {dimension: sorted(rows, key=lambda row: -row["uses"]) for dimension, rows in table.items()}


def _top_texts(texts, limit=4):
    counts = Counter(" ".join(text.split()) for text in texts if text)
    return [{"text": text, "count": count} for text, count in counts.most_common(limit)]


def _segment_phrase(segment):
    if segment["dimension"] == "period":
        return f"de {PERIOD_LABELS['recent']}" if segment["value"] == "recent" else "de periode daarvoor"
    if segment["dimension"] == "statute":
        return {"arbeider": "arbeiders", "bediende": "bedienden",
                "alle": "werknemers zonder statuut"}.get(segment["value"], segment["value"])
    return f'{segment["dimension_label"].lower()} {segment["value"]}'


def _reason(result, fail_prior, doubt_prior):
    quadrant = result["quadrant"]
    if quadrant == "insufficient":
        return (f"Pas vanaf {MIN_USES} gebruiken door minstens {MIN_USERS} collega's tonen we een oordeel. "
                "Tot dan telt de eigenaar en de publicatiedatum.")
    parts = []
    if result["segment"] and result["segment"]["high"]:
        segment = result["segment"]
        elsewhere = "daarvoor" if segment["dimension"] == "period" else "elders"
        parts.append(f'{"In" if segment["dimension"] == "period" else "Bij"} {_segment_phrase(segment)} liep '
                     f'{segment["fails"]} van de {segment["uses"]} gebruiken mis '
                     f'({segment["raw"]:.0%} tegenover {segment["rest_raw"]:.0%} {elsewhere}).')
    if quadrant in ("dangerous", "broken") and not (result["segment"] and result["segment"]["high"]):
        parts.append(f'{result["fails"]} van de {result["uses"]} gebruiken liepen mis '
                     f'({result["fails"] / result["uses"]:.0%}; bij een typisch document {fail_prior:.0%}).')
    if quadrant in ("unclear", "broken"):
        parts.append(f'Na {result["doubts"]} van de {result["reads"]} keer lezen bleef de twijfel '
                     f'({result["doubts"] / result["reads"]:.0%}; bij een typisch document {doubt_prior:.0%}).')
    if quadrant == "dangerous":
        parts.append("Wie het leest, twijfelt niet: de fout blijft onzichtbaar zonder uitkomsten.")
    if quadrant == "reliable":
        parts.append(f'{result["uses"] - result["fails"]} van de {result["uses"]} gebruiken zonder correctie, '
                     f'en lezers twijfelen niet meer dan normaal.')
    return " ".join(parts)


# --- Find it: knowledge that people search for but cannot find --------------------------------

_STOP = {"de", "het", "een", "en", "van", "voor", "in", "op", "bij", "is", "hoe", "wat", "welke", "wie",
         "met", "per", "na", "te", "je", "ik", "er", "nu", "ook", "dit", "die", "dat", "om", "aan"}


def _stems(text):
    words = re.findall(r"[a-zà-ÿ0-9]+", text.lower())
    return {word[:5] for word in words if word not in _STOP and len(word) > 2}


def gaps(db, as_of, window_days=GAP_WINDOW_DAYS):
    """Cluster sessions that searched but never cited a document."""
    start = (as_of - timedelta(days=window_days)).isoformat()
    cutoff = f"{as_of.isoformat()}T23:59:59"
    sessions = defaultdict(lambda: {"queries": [], "questions": [], "cited": False, "bounces": 0, "users": set()})
    for row in db.execute("""SELECT session_id, pseudo_user, type, text, dwell_seconds FROM events
                             WHERE at >= ? AND at <= ? ORDER BY session_id, at""", (start, cutoff)):
        session = sessions[row["session_id"]]
        session["users"].add(row["pseudo_user"])
        if row["type"] == "search":
            session["queries"].append(row["text"])
        elif row["type"] in ("teams_question", "review_request") and row["text"]:
            session["questions"].append(row["text"])
        elif row["type"] == "cite":
            session["cited"] = True
        elif row["type"] == "open" and (row["dwell_seconds"] or 0) < MIN_DWELL_SECONDS:
            session["bounces"] += 1

    failed = [session for session in sessions.values() if not session["cited"] and session["queries"]]
    # Words that keep coming back in failed searches are the theme; rare words weigh less.
    weight = Counter(stem for session in failed for stem in _stems(" ".join(session["queries"])))
    clusters = []
    for session in failed:
        stems = _stems(" ".join(session["queries"]))
        best, best_score = None, 0.0
        for cluster in clusters:
            core = {stem for stem, count in cluster["stems"].items() if count >= 0.5 * cluster["sessions"]}
            union = sum(weight[stem] for stem in stems | core)
            score = sum(weight[stem] for stem in stems & core) / union if union else 0
            if score > best_score:
                best, best_score = cluster, score
        if best is None or best_score < 0.2:
            best = {"stems": Counter(), "sessions": 0, "with_teams": 0, "bounces": 0,
                    "queries": Counter(), "questions": Counter(), "users": set()}
            clusters.append(best)
        best["stems"].update(stems)
        best["sessions"] += 1
        best["with_teams"] += int(bool(session["questions"]))
        best["bounces"] += session["bounces"]
        best["queries"].update(session["queries"])
        best["questions"].update(session["questions"])
        best["users"] |= session["users"]

    output = []
    for cluster in clusters:
        if len(cluster["users"]) < MIN_USERS:
            continue
        share = cluster["with_teams"] / cluster["sessions"]
        output.append({
            "label": cluster["queries"].most_common(1)[0][0],
            "sessions": cluster["sessions"], "teams_share": round(share, 2), "bounces": cluster["bounces"],
            "queries": [q for q, _ in cluster["queries"].most_common(4)],
            "questions": [{"text": q, "count": c} for q, c in cluster["questions"].most_common(3)],
            "is_gap": cluster["sessions"] >= GAP_MIN_SESSIONS and share >= GAP_MIN_TEAMS_SHARE,
            "stems": sorted(stem for stem, count in cluster["stems"].items() if count >= 0.5 * cluster["sessions"]),
        })
    return sorted(output, key=lambda gap: (-gap["is_gap"], -gap["sessions"]))


def today(db):
    from .store import get_meta
    return date.fromisoformat(get_meta(db, "today"))
