"""Turn scores into what people see next to a source: short, checkable, context-aware."""
import threading

from . import explain, scoring, store

_lock = threading.Lock()
_cache = {"key": None}


def snapshot(db, path):
    """Scores are recomputed only when the data changed (revision counter)."""
    key = (str(path), store.get_meta(db, "generation"), store.get_meta(db, "revision", "0"),
           store.get_meta(db, "today"))
    with _lock:
        if _cache["key"] != key:
            as_of = scoring.today(db)
            _cache.update(key=key, scores=scoring.compute(db, as_of), gaps=scoring.gaps(db, as_of), causes={})
        return _cache


def cause_for(cache, source_id):
    causes = cache["causes"]
    if source_id not in causes:
        versions = cache["scores"]["versions"]
        causes[source_id] = explain.root_cause(versions[source_id], list(versions.values()))
    return causes[source_id]


def phrase(segment):
    return scoring._segment_phrase(segment)


def trust_label(cache, source_id, context=None):
    """The track record of one source, for the reader's context when we know it.

    context: {"statute", "pc", "country", "size"}; unknown values are None.
    """
    version = cache["scores"]["versions"].get(source_id)
    if version is None:
        return None
    context = context or {}
    quadrant = version["quadrant"]
    label = {"quadrant": quadrant, "quadrant_label": version["quadrant_label"], "warning": None,
             "context_note": None, "tip": None}
    if quadrant == "insufficient":
        label["headline"] = "Nog geen trackrecord"
        label["detail"] = (f"{version['uses']} gebruik(en) met gekende uitkomst. We oordelen pas vanaf "
                           f"{scoring.MIN_USES} gebruiken door {scoring.MIN_USERS} collega's.")
    else:
        label["headline"] = f"{version['uses'] - version['fails']} van {version['uses']} keer zonder correctie"
        label["detail"] = f"{version['users']} collega's gebruikten deze bron voor een ticket"

    segment = version["segment"]
    cause = cause_for(cache, source_id) if quadrant in ("dangerous", "broken") else None
    because = (f" Oorzaak volgens de tickets: {', '.join(t['word'] for t in cause['terms'][:3])}."
               if cause and cause["terms"] else "")
    if segment and segment["high"]:
        dimension = segment["dimension"]
        wanted = "recent" if dimension == "period" else context.get(dimension)
        own = next((row for row in version["segments"].get(dimension, []) if row["value"] == wanted), None)
        if own:   # the numbers for the reader's own context, not the global average
            own_phrase = phrase({**segment, "value": own["value"]})
            prefix = f"{own_phrase[0].upper()}{own_phrase[1:]}" if dimension == "period" else f"Bij {own_phrase}"
            label["headline"] = f"{prefix}: {own['uses'] - own['fails']} van {own['uses']} keer zonder correctie"
        text = (f"{'In' if dimension == 'period' else 'Bij'} {phrase(segment)} liep "
                f"{segment['fails']} van de {segment['uses']} gebruiken mis.")
        if dimension == "period" or wanted == segment["value"]:
            label["warning"] = text + because
        elif wanted is None:
            label["warning"] = text + because + f" Geef {segment['dimension_label'].lower()} op om te zien of dit voor jou geldt."
        else:
            label["context_note"] = text + " Jouw situatie valt daar niet onder; daar zien we geen afwijking."
    elif quadrant in ("dangerous", "broken"):
        label["warning"] = f"{version['fails']} van de {version['uses']} gebruiken liepen mis.{because}"
    if quadrant in ("unclear", "broken") and version["follow_ups"]:
        label["tip"] = f"Na het lezen vroegen collega's vaak: “{version['follow_ups'][0]['text']}”"
    return label


def public(version, fields=("id", "document_id", "title", "topic", "country", "statute", "owner", "version",
                             "published_at", "is_current", "quadrant", "quadrant_label", "uses", "fails", "users",
                             "fail_rate", "doubt_rate", "reads", "doubts", "reason", "segment", "kind",
                             "approved")):
    return {field: version[field] for field in fields}
