"""Optimized Policy: every rule shares one matching index built at init.

Semantics are identical to reference.py (see CONTRACT.md). A pattern is a
sequence of literal byte strings joined by '*' wildcards that absorb any
run of bytes (zero length included); only a trailing '$' anchors the end
of the path, the first literal must start at offset 0, and a rule matches
when its literals appear in order. The hit with the highest score (total
literal bytes) decides; ties go to allow, and no hit means allow.

Index built once per instance (never cached across instances):
  * one Aho-Corasick automaton over every distinct non-empty literal of
    every rule, so a single left-to-right scan of the canonical path
    reports every occurrence of every literal, overlaps included;
  * one rule trie whose root-to-node paths are the rules' literal
    sequences, so prefixes shared between rules are stored and advanced
    once; each node keeps the (score, allow) terminal of the rules ending
    exactly there, separately for anchored and unanchored rules;
  * per node an earliest-end slot stamped with the current query
    generation, so a query only visits nodes reached by real occurrences
    and never scans the rules one by one.
"""
from collections import deque

from normalization import rule_parts, url_path


class Policy:
    def __init__(self, rules):
        if not isinstance(rules, (list, tuple)):
            raise ValueError("rules must be a list or tuple")
        part_ids = {}
        parts = []
        edges = []
        always = None
        children = [{}]
        nscore = [0]
        term_free = [None]
        term_anchor = [None]
        for item in rules:
            parsed = rule_parts(item)
            if parsed is None:
                continue
            allow, pieces, anchored, score = parsed
            if anchored and not pieces[-1]:
                # The pattern ends with '*': the trailing '.*' already
                # reaches the end of any path, so the anchor is moot.
                anchored = False
            seq = []
            for piece in pieces:
                if not piece:
                    # An empty literal between wildcards is a no-op.
                    continue
                pid = part_ids.get(piece)
                if pid is None:
                    pid = len(parts)
                    part_ids[piece] = pid
                    parts.append(piece)
                    edges.append([])
                seq.append(pid)
            if not seq:
                # Only wildcards: matches every path with score 0.
                always = allow if always is None else (always or allow)
                continue
            node = 0
            for pid in seq:
                nxt = children[node].get(pid)
                if nxt is None:
                    nxt = len(children)
                    children[node][pid] = nxt
                    children.append({})
                    nscore.append(nscore[node] + len(parts[pid]))
                    term_free.append(None)
                    term_anchor.append(None)
                    edges[pid].append((node, nxt))
                node = nxt
            # Rules sharing one literal sequence share its score, so only
            # the allow flag needs merging; a tie is won by allow.
            if anchored:
                prev = term_anchor[node]
                term_anchor[node] = allow if prev is None else (prev or allow)
            else:
                prev = term_free[node]
                term_free[node] = allow if prev is None else (prev or allow)

        # Aho-Corasick automaton over the distinct literals.
        trans = [{}]
        own = [()]
        for pid, piece in enumerate(parts):
            node = 0
            for byte in piece:
                nxt = trans[node].get(byte)
                if nxt is None:
                    nxt = len(trans)
                    trans[node][byte] = nxt
                    trans.append({})
                    own.append(())
                node = nxt
            own[node] = (pid,)
        fail = [0] * len(trans)
        out = list(own)
        queue = deque(trans[0].values())
        while queue:
            node = queue.popleft()
            for byte, nxt in trans[node].items():
                queue.append(nxt)
                back = fail[node]
                while back and byte not in trans[back]:
                    back = fail[back]
                fail[nxt] = trans[back].get(byte, 0)
                if out[fail[nxt]]:
                    out[nxt] = out[nxt] + out[fail[nxt]]

        self._always = always
        self._trans = trans
        self._fail = fail
        self._out = out
        self._plen = [len(piece) for piece in parts]
        self._edges = edges
        self._nscore = nscore
        self._term_free = term_free
        self._term_anchor = term_anchor
        self._gen = [0] * len(children)
        self._val = [0] * len(children)
        self._cur = 0

    def allowed(self, url):
        path = url_path(url)
        best_score = -1
        best_allow = True
        always = self._always
        if always is not None:
            best_score = 0
            best_allow = always
        cur = self._cur + 1
        self._cur = cur
        gen = self._gen
        val = self._val
        trans = self._trans
        fail = self._fail
        out = self._out
        plen = self._plen
        edges = self._edges
        nscore = self._nscore
        term_free = self._term_free
        term_anchor = self._term_anchor
        n = len(path)
        node = 0
        pos = 0
        for byte in path:
            pos += 1
            while node and byte not in trans[node]:
                node = fail[node]
            node = trans[node].get(byte, 0)
            for pid in out[node]:
                start = pos - plen[pid]
                for prev, nxt in edges[pid]:
                    if prev:
                        if gen[prev] != cur or val[prev] > start:
                            continue
                    elif start:
                        # The first literal must begin at offset 0.
                        continue
                    if gen[nxt] != cur:
                        # Occurrences arrive in growing end order, so the
                        # first reach is the earliest possible end.
                        gen[nxt] = cur
                        val[nxt] = pos
                        allow = term_free[nxt]
                        if allow is not None:
                            score = nscore[nxt]
                            if score > best_score or (score == best_score and allow):
                                best_score = score
                                best_allow = allow
                    if pos == n:
                        # Anchored rules need their last literal to end
                        # exactly at the path end; check every occurrence.
                        allow = term_anchor[nxt]
                        if allow is not None:
                            score = nscore[nxt]
                            if score > best_score or (score == best_score and allow):
                                best_score = score
                                best_allow = allow
        return best_allow
