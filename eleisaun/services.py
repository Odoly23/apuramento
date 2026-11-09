"""Lójika konsolidasaun rezultadu no analitika.

Regra konsolidasaun ba kada sentru (rezultadu ofisiál la'ós fiskál ida deit):
  1. Relatóriu VERIFIKADU hosi admin -> prevalese ("verified").
  2. Se la iha, relatóriu rua ka liu ho númeru hanesan 100% -> "consensus".
  3. Relatóriu úniku -> "provisional".
  4. Relatóriu oioin la hanesan, la iha verifikasaun -> "conflict" (la konta, hein admin).
"""
from collections import defaultdict

from django.core.cache import cache

from .models import Centre, Contestant, Election, Report

SNAPSHOT_TTL = 5  # segundu


def invalidate(election_id):
    cache.delete(f"snap:{election_id}")


def compute_flags(report, centre, contestants_count=None):
    flags = []
    reg = centre.registered_voters or 0
    if reg and report.voted / reg > 0.95:
        flags.append("high_turnout")
    if report.voted and (report.blank + report.invalid) / report.voted > 0.10:
        flags.append("high_invalid")
    valid = report.voted - report.blank - report.invalid
    lines = list(report.lines.all())
    if valid >= 100 and lines and max(l.votes for l in lines) / valid > 0.95:
        flags.append("extreme_share")
    return flags


class Node:
    """Agregasaun ba rejiaun (nasionál, munisípiu, postu, suku)."""

    __slots__ = ("id", "name", "parent", "centres_total", "centres_reporting", "registered",
                 "registered_reporting", "voted", "blank", "invalid", "votes", "conflicts", "hckey")

    def __init__(self, id, name, parent=None, hckey=None):
        self.id, self.name, self.parent, self.hckey = id, name, parent, hckey
        self.centres_total = self.centres_reporting = 0
        self.registered = self.registered_reporting = 0
        self.voted = self.blank = self.invalid = 0
        self.votes = defaultdict(int)
        self.conflicts = 0

    def add_centre(self, centre):
        self.centres_total += 1
        self.registered += centre.registered_voters

    def add_result(self, centre, c):
        self.centres_reporting += 1
        self.registered_reporting += centre.registered_voters
        self.voted += c["voted"]
        self.blank += c["blank"]
        self.invalid += c["invalid"]
        for cid, v in c["votes"].items():
            self.votes[cid] += v

    @property
    def valid(self):
        return sum(self.votes.values())

    def as_dict(self):
        valid = self.valid
        ranked = sorted(self.votes.items(), key=lambda kv: -kv[1])
        leader = ranked[0][0] if ranked and ranked[0][1] > 0 else None
        margin = (ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else (ranked[0][1] if ranked else 0)
        return {
            "id": self.id, "name": self.name, "parent": self.parent, "hckey": self.hckey,
            "centres_total": self.centres_total, "centres_reporting": self.centres_reporting,
            "progress": round(100 * self.centres_reporting / self.centres_total, 1) if self.centres_total else 0,
            "registered": self.registered, "voted": self.voted, "blank": self.blank, "invalid": self.invalid,
            "valid": valid,
            "turnout": round(100 * self.voted / self.registered_reporting, 2) if self.registered_reporting else 0,
            "votes": {str(k): v for k, v in self.votes.items()},
            "shares": {str(k): round(100 * v / valid, 2) if valid else 0 for k, v in self.votes.items()},
            "leader": leader, "margin": margin, "conflicts": self.conflicts,
        }


def resolve_centre(rs):
    """Dadu lista relatóriu (la inklui rejeitadu) ba sentru ida -> (relatóriu hili, estadu)."""
    verified = [r for r in rs if r.status == Report.VERIFIED]
    if verified:
        return verified[0], "verified"
    groups = defaultdict(list)
    for r in rs:
        groups[r.signature()].append(r)
    if len(groups) == 1:
        group = next(iter(groups.values()))
        return group[0], ("consensus" if len(group) > 1 else "provisional")
    best = sorted(groups.values(), key=len, reverse=True)
    if len(best[0]) > 1 and len(best[0]) > len(best[1]):
        return best[0][0], "consensus"
    return None, "conflict"


def consolidate(election):
    """Return dict centre_id -> {state, report, voted, blank, invalid, votes{cid: n}, n_reports}."""
    reports = (Report.objects.filter(election=election).exclude(status=Report.REJECTED)
               .select_related("submitted_by").prefetch_related("lines"))
    by_centre = defaultdict(list)
    for r in reports:
        by_centre[r.centre_id].append(r)

    out = {}
    for centre_id, rs in by_centre.items():
        chosen, state = resolve_centre(rs)
        entry = {"state": state, "n_reports": len(rs), "report": chosen}
        if chosen is not None:
            entry.update(
                voted=chosen.voted, blank=chosen.blank, invalid=chosen.invalid,
                votes={l.contestant_id: l.votes for l in chosen.lines.all()},
            )
        out[centre_id] = entry
    return out


def build_snapshot(election, use_cache=True):
    key = f"snap:{election.id}"
    if use_cache:
        snap = cache.get(key)
        if snap is not None:
            return snap

    contestants = list(Contestant.objects.filter(election=election).select_related("party"))
    centres = Centre.objects.select_related("village__administrativepost__municipality", "nasaun")
    cons = consolidate(election)

    national = Node("all", "Timor-Leste")
    diaspora = Node("dia", "Diáspora")
    munis, postus, sukus, nasauns = {}, {}, {}, {}
    states = defaultdict(int)
    for ce in centres:
        if ce.is_diaspora:
            nodes = (national, diaspora, nasauns.setdefault(ce.nasaun_id, Node(ce.nasaun_id, ce.nasaun.name)))
        else:
            vi, po = ce.village, ce.village.administrativepost
            mu = po.municipality
            m = munis.setdefault(mu.id, Node(mu.id, mu.name, hckey=mu.hckey))
            p = postus.setdefault(po.id, Node(po.id, po.name, parent=mu.id))
            s = sukus.setdefault(vi.id, Node(vi.id, vi.name, parent=po.id))
            nodes = (national, m, p, s)
        for n in nodes:
            n.add_centre(ce)
        c = cons.get(ce.id)
        if not c:
            states["missing"] += 1
            continue
        states[c["state"]] += 1
        if c["state"] == "conflict":
            for n in nodes:
                n.conflicts += 1
            continue
        for n in nodes:
            n.add_result(ce, c)

    recent = (Report.objects.filter(election=election).select_related("centre__village__administrativepost__municipality", "centre__nasaun", "submitted_by")
              .order_by("-updated_at")[:12])
    snap = {
        "election": {"id": election.id, "name": election.name, "kind": election.kind, "date": str(election.date)},
        "contestants": [{"id": c.id, "name": c.name, "short": c.short, "number": c.ballot_number,
                         "color": c.color, "party_id": c.party_id} for c in contestants],
        "national": national.as_dict(),
        "municipalities": sorted((n.as_dict() for n in munis.values()), key=lambda d: d["name"]),
        "nasauns": sorted((n.as_dict() for n in nasauns.values()), key=lambda d: d["name"]),
        "diaspora": diaspora.as_dict(),
        "postus": [n.as_dict() for n in postus.values()],
        "sukus": [n.as_dict() for n in sukus.values()],
        "states": dict(states),
        "recent": [{
            "id": r.id, "centre": r.centre.name, "code": r.centre.code, "muni": r.centre.municipality.name if r.centre.municipality else f"Diáspora · {r.centre.nasaun}",
            "by": r.submitted_by.get_username(), "status": r.status, "at": r.updated_at.isoformat(),
        } for r in recent],
    }
    cache.set(key, snap, SNAPSHOT_TTL)
    return snap


def pick_election(request_value=None):
    qs = Election.objects.all()
    if request_value:
        e = qs.filter(pk=request_value).first() if str(request_value).isdigit() else None
        if e:
            return e
    return qs.filter(is_active=True).first() or qs.first()
