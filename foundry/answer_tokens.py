"""Shared tokenization + stopwords (imported by retrieve and answer)."""
import re

STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being
below between both but by can cannot could did do does doing don down during each few for
from further had has have having he her here hers herself him himself his how i if in into
is it its itself just like me more most my myself no nor not now of off on once only or
other ought our ours ourselves out over own same she should so some such than that the
their theirs them themselves then there these they this those through to too under until
up very was we were what when where which while who whom why with would you your yours
yourself yourselves also may often within without one two first new many much every per
shall will us we ll don doesn isn aren wasn weren hasn haven didn couldn shouldn won would
""".split())

TOKEN_RE = re.compile(r"[a-z0-9']+")


def tokenize(s):
    return TOKEN_RE.findall(s.lower())


# --- Compact Porter stemmer (public domain algorithm by Martin Porter) ---
# Used so the extractive scorer matches FTS5's porter tokenization
# (e.g. "flaw" matches "flaws", "breathing" matches "breathe").

_VOWELS = "aeiou"


def _is_consonant(word, i):
    c = word[i]
    if c in _VOWELS:
        return False
    if c == "y":
        return i == 0 or not _is_consonant(word, i - 1)
    return True


def _measure(word):
    n, i = 0, 0
    while i < len(word):
        while i < len(word) and _is_consonant(word, i):
            i += 1
        while i < len(word) and not _is_consonant(word, i):
            i += 1
        if i < len(word):
            n += 1
    return n


def _has_vowel(word):
    return any(not _is_consonant(word, i) for i in range(len(word)))


def _ends_double_consonant(word):
    return (len(word) >= 2 and word[-1] == word[-2]
            and _is_consonant(word, len(word) - 1))


def _cvc(word):
    if len(word) < 3:
        return False
    c = word[-3:]
    return (_is_consonant(word, len(word) - 3)
            and not _is_consonant(word, len(word) - 2)
            and _is_consonant(word, len(word) - 1)
            and word[-1] not in "wxy")


def _step1a(word):
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies"):
        return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _step1b(word):
    if word.endswith("eed"):
        return word[:-1] if _measure(word[:-3]) > 0 else word
    for suffix in ("ed", "ing"):
        if word.endswith(suffix) and _has_vowel(word[:-len(suffix)]):
            stem = word[:-len(suffix)]
            if stem.endswith(("at", "bl", "iz")):
                return stem + "e"
            if _ends_double_consonant(stem):
                return stem[:-1]
            if _measure(stem) == 1 and _cvc(stem):
                return stem + "e"
            return stem
    return word


def _step1c(word):
    if word.endswith("y") and _has_vowel(word[:-1]):
        return word[:-1] + "i"
    return word


_STEP2 = {
    "ational": "ate", "tional": "tion", "enci": "ence", "anci": "ance",
    "izer": "ize", "bli": "ble", "alli": "al", "entli": "ent", "eli": "e",
    "ousli": "ous", "ization": "ize", "ation": "ate", "ator": "ate",
    "alism": "al", "iveness": "ive", "fulness": "ful", "ousness": "ous",
    "aliti": "al", "iviti": "ive", "biliti": "ble", "logi": "log",
}


def _step2(word):
    for suffix, rep in _STEP2.items():
        if word.endswith(suffix) and _measure(word[:-len(suffix)]) > 0:
            return word[:-len(suffix)] + rep
    return word


_STEP3 = {
    "icate": "ic", "ative": "", "alize": "al", "iciti": "ic",
    "ical": "ic", "ful": "", "ness": "",
}


def _step3(word):
    for suffix, rep in _STEP3.items():
        if word.endswith(suffix) and _measure(word[:-len(suffix)]) > 0:
            return word[:-len(suffix)] + rep
    return word


def _step4(word):
    for suffix in ("al", "ance", "ence", "er", "ic", "able", "ible", "ant",
                   "ement", "ment", "ent", "ou", "ism", "ate", "iti",
                   "ous", "ive", "ize"):
        if word.endswith(suffix) and _measure(word[:-len(suffix)]) > 1:
            return word[:-len(suffix)]
    if word.endswith("ion"):
        stem = word[:-3]
        if _measure(stem) > 1 and stem[-1] in "st":
            return stem
    return word


def _step5(word):
    if word.endswith("e"):
        stem = word[:-1]
        if _measure(stem) > 1 or (_measure(stem) == 1 and not _cvc(stem)):
            return stem
    if word.endswith("ll") and _measure(word) > 1:
        return word[:-1]
    return word


def stem(word):
    if len(word) <= 2 or not word[0].isalpha():
        return word
    w = _step1a(word)
    w = _step1b(w)
    w = _step1c(w)
    w = _step2(w)
    w = _step3(w)
    w = _step4(w)
    w = _step5(w)
    return w


def stem_tokens(tokens):
    return [stem(t) for t in tokens]
