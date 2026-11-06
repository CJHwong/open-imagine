#!/usr/bin/env python3
"""Build the review board, import feedback, preview dependency impact, and gate storyboard readiness and video submission."""

import argparse
import copy
import datetime
import hashlib
import json
import pathlib
import sys
import tempfile

PROFILES = {
    "drama": {},
    "short": {"aspect_ratio": "9:16", "max_seconds": 60, "promise_by_seconds": 3},
}
BEAT_ROLES = ("promise", "setup", "payoff", "re_engage", "turn", "reveal", "other")


def profile(p):
    """A project without a profile is a drama, as every project was before profiles existed."""
    return p.get("settings", {}).get("profile", "drama")


def profile_settings(p):
    """The profile's defaults under the project's own settings; an explicit setting wins."""
    return {**PROFILES[profile(p)], **p["settings"]}


def generated_shots(p):
    """Shots the pipeline renders; real footage skips the storyboard gates."""
    return [s for s in p["shots"] if s.get("source", "generated") == "generated"]


def selected(node):
    return next(v for v in node["versions"] if v["id"] == node["selected"])


def input_id(dependency):
    if not isinstance(dependency, dict):
        raise ValueError(f"An input must be an object with asset_id or shot_id, not {dependency!r}")
    keys = [k for k in ("asset_id", "shot_id") if dependency.get(k)]
    if len(keys) != 1:
        raise ValueError("A dependency needs exactly one asset_id or shot_id")
    return dependency[keys[0]]


def validate(p):
    if p.get("schema_version") != 1:
        raise ValueError("Unsupported schema_version")
    ids = [x["id"] for x in p["assets"] + p["shots"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Asset and shot IDs must be unique")
    nodes = {n["id"]: n for n in p["assets"] + p["shots"]}
    for n in p["assets"] + p["shots"]:
        vs = [v["id"] for v in n["versions"]]
        if len(vs) != len(set(vs)) or n["selected"] not in vs:
            raise ValueError(f"Invalid versions/selection: {n['id']}")
        for v in n["versions"]:
            for i in v.get("inputs", []):
                target = nodes.get(input_id(i))
                expected = p["assets"] if i.get("asset_id") else p["shots"]
                if (
                    target is None
                    or target not in expected
                    or i["version"] not in [x["id"] for x in target["versions"]]
                ):
                    raise ValueError(f"Unknown input: {i}")
    visiting, done = set(), set()

    def walk(aid):
        if aid in visiting:
            raise ValueError("Cyclic asset dependencies")
        if aid in done:
            return
        visiting.add(aid)
        for i in selected(nodes[aid]).get("inputs", []):
            walk(input_id(i))
        visiting.remove(aid)
        done.add(aid)

    for aid in nodes:
        walk(aid)
    if profile(p) not in PROFILES:
        raise ValueError(f"settings.profile must be one of {sorted(PROFILES)}, not {profile(p)!r}")
    for s in p["shots"]:
        if s.get("source", "generated") not in ("generated", "footage"):
            raise ValueError(f"{s['id']}: source must be generated or footage")
    shots = sorted(p["shots"], key=lambda s: s["start"])
    end = 0
    generated = {s["id"] for s in generated_shots(p)}
    for s in shots:
        ceiling = p["settings"]["max_shot_seconds"] if s["id"] in generated else float("inf")
        if s["duration"] <= 0 or s["duration"] > ceiling:
            raise ValueError(f"Shot duration violates project setting: {s['id']}")
        if abs(s["start"] - end) > 0.01:
            raise ValueError(f"Timeline gap/overlap before {s['id']}")
        end = s["start"] + s["duration"]
    if abs(end - p["settings"]["target_seconds"]) > 0.05:
        raise ValueError("Timeline does not match target duration")


def stale_nodes(p):
    nodes = {n["id"]: n for n in p["assets"] + p["shots"]}
    stale = set()
    while True:
        before = set(stale)
        for n in p["assets"] + p["shots"]:
            if any(
                i["version"] != nodes[input_id(i)]["selected"] or input_id(i) in stale
                for i in selected(n).get("inputs", [])
            ):
                stale.add(n["id"])
        if stale == before:
            return sorted(stale)


def plan(p, changed):
    assets = {a["id"]: a for a in p["assets"]}
    nodes = {n["id"]: n for n in p["assets"] + p["shots"]}
    unknown = set(changed) - nodes.keys()
    if unknown:
        raise ValueError(f"Unknown changed asset IDs: {sorted(unknown)}")
    affected = set(changed)
    while True:
        nxt = affected | {
            n["id"] for n in nodes.values() if any(input_id(i) in affected for i in selected(n).get("inputs", []))
        }
        if nxt == affected:
            break
        affected = nxt
    shots = []
    for s in p["shots"]:
        hits = [i for i in selected(s).get("inputs", []) if input_id(i) in affected]
        if not hits and s["id"] not in changed:
            continue
        actions = {"regenerate_video", "reassemble"} if s["id"] in changed else set()
        for i in hits:
            use = i.get("use")
            if use in ["image_reference", "scene"]:
                actions.update(["update_reference", "regenerate_video", "reassemble"])
            elif use in ["video_conditioning", "preceding_cut_frame", "selected_end_frame"]:
                actions.update(["regenerate_video", "reassemble"])
            elif use == "audio":
                actions.update(["update_audio", "retime_captions", "remix"])
            else:
                actions.add("review_dependency")
        shots.append({"id": s["id"], "actions": sorted(actions), "affected_inputs": [input_id(i) for i in hits]})
    return {
        "changed_assets": sorted(set(changed) & assets.keys()),
        "changed_shots": sorted(set(changed) - assets.keys()),
        "downstream_assets": sorted((affected - set(changed)) & assets.keys()),
        "shots": shots,
        "jobs_submitted": 0,
    }


def take_media(version):
    """The file a take decision judges: its clip, else its frame, else its audio."""
    return version.get("video") or storyboard_frame(version) or version.get("audio")


def pin_approval(version, root):
    """An approved take names the bytes the producer approved; any other decision drops the pin."""
    version.pop("approved_sha256", None)
    media = take_media(version)
    if version["review_status"] == "approved" and media:
        version["approved_sha256"] = file_sha256(root, media)


def void_approvals(p, path):
    """Return (node id, version id) for each approved take whose media changed after the approval."""
    root = path.resolve().parent
    return [
        (node["id"], version["id"])
        for node in p["assets"] + p["shots"]
        for version in node["versions"]
        if version.get("approved_sha256") and version["approved_sha256"] != file_sha256(root, take_media(version))
    ]


def apply_feedback(p, feedback, path):
    if feedback.get("project_id") != p["id"] or feedback.get("base_revision") != p["revision"]:
        raise ValueError("Feedback project/revision mismatch; rebuild the board or resolve against current choices")
    out = copy.deepcopy(p)
    for collection in ["shots", "assets"]:
        nodes = {n["id"]: n for n in out[collection]}
        seen = set()
        for f in feedback.get(collection, []):
            if f["id"] in seen or f["id"] not in nodes:
                raise ValueError("Duplicate/unknown node in feedback")
            seen.add(f["id"])
            node = nodes[f["id"]]
            if f.get("base_selected") != node["selected"]:
                raise ValueError(f"Selection conflict: {node['id']}")
            versions = {v["id"]: v for v in node["versions"]}
            if f.get("selected") not in versions:
                raise ValueError("Feedback selects an unknown version")
            decisions = {**f.get("takes", {}), f["selected"]: f}
            for vid, decision in decisions.items():
                if (
                    vid not in versions
                    or decision.get("review_status") not in ["unreviewed", "approved", "revise"]
                    or not isinstance(decision.get("notes", ""), str)
                ):
                    raise ValueError("Invalid per-take review decision/notes")
                versions[vid]["review_status"] = decision["review_status"]
                versions[vid]["notes"] = decision.get("notes", "")
                pin_approval(versions[vid], path.resolve().parent)
            node["selected"] = f["selected"]
    out.setdefault("history", []).append(
        {
            "at": datetime.datetime.now(datetime.UTC).isoformat(),
            "kind": "feedback_import",
            "from_revision": p["revision"],
            "previous_choices": [
                {
                    "id": n["id"],
                    "selected": n["selected"],
                    "review_status": selected(n).get("review_status", "unreviewed"),
                    "notes": selected(n).get("notes", ""),
                }
                for n in p["shots"] + p["assets"]
            ],
            "feedback": feedback,
        }
    )
    out["revision"] += 1
    return out


def now():
    return datetime.datetime.now(datetime.UTC).isoformat()


def storyboard_frame(version):
    return version.get("storyboard_image") or version.get("reference") or version.get("image")


def file_sha256(root, rel):
    return hashlib.sha256((root / rel).read_bytes()).hexdigest()


def staging_problems(p):
    """A board is checkable only when every shot cites one shared map and world time."""
    staging = p.get("staging")
    if not staging:
        return [
            "Add a staging block: one top-down map of positions, reachable props and cameras, plus a world-time timeline."
        ]
    problems = []
    if not staging.get("map"):
        problems.append("staging.map: add the top-down map image.")
    cameras = set(staging.get("cameras", []))
    times = {t.get("id") for t in staging.get("timeline", [])}
    if not cameras:
        problems.append("staging.cameras: list the camera setups drawn on the map.")
    if not times:
        problems.append("staging.timeline: list world-time states with ids.")
    for s in generated_shots(p):
        cited = s.get("staging", {})
        if cited.get("camera") not in cameras:
            problems.append(f"{s['id']}: staging.camera must cite a camera from staging.cameras.")
        if cited.get("world_time") not in times:
            problems.append(f"{s['id']}: staging.world_time must cite a staging.timeline id.")
    return problems


CARD_FIELDS = ("camera", "world_time", "mover", "camera_move", "mouth_visible", "end_state")
MOUTH_VISIBILITY = ("hidden", "small", "close")


def card_problems(p):
    """Each layout card names what the blind reviewer checks against its frame; a blank field leaves nothing to check."""
    problems = []
    for s in generated_shots(p):
        card = s.get("staging") or {}
        missing = [field for field in CARD_FIELDS if not str(card.get(field, "")).strip()]
        if missing:
            problems.append(f"{s['id']}: the layout card needs {', '.join(missing)}.")
        if card.get("mouth_visible") and card["mouth_visible"] not in MOUTH_VISIBILITY:
            problems.append(
                f"{s['id']}: staging.mouth_visible must be hidden, small or close, not {card['mouth_visible']!r}."
            )
    return problems


def shot_digests(p, path):
    """Hash what the producer sees and approves: frame pixels, timing, purpose, inputs and staging."""
    root = path.resolve().parent
    staging = copy.deepcopy(p.get("staging", {}))
    if staging.get("map"):
        staging["map_sha256"] = file_sha256(root, staging["map"])
    digests = {}
    for s in generated_shots(p):
        version = selected(s)
        frame = storyboard_frame(version)
        if not frame:
            raise ValueError(f"{s['id']} has no storyboard frame")
        record = {
            "shot": {k: s.get(k) for k in ("id", "start", "duration", "purpose", "dialogue", "selected", "staging")},
            "inputs": version.get("inputs", []),
            "frame_sha256": file_sha256(root, frame),
            "staging": staging,
        }
        digests[s["id"]] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return digests


def changed_shots(recorded, digests, shot_ids):
    return [sid for sid in shot_ids if recorded.get(sid) != digests[sid]]


SEVERITIES = ("block", "revise")


def is_revision(finding):
    return finding.get("result") == "fail" and finding.get("severity") == "revise"


def is_blocking(finding):
    """A failed finding recorded before severities existed counts as blocking."""
    return finding.get("result") == "fail" and finding.get("severity", "block") == "block"


def open_revisions(p):
    """The revise findings of the current blind review: the board may go to the producer, who sees these."""
    return [f for f in p.get("storyboard_review", {}).get("findings", []) if is_revision(f)]


def review_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def waived(p):
    """A producer can accept a failed review knowingly; the waiver covers that one review, not a later or edited one."""
    waiver = p.get("storyboard_approval", {}).get("waived_review")
    if not waiver:
        return False
    if "digest" in waiver:
        return waiver["digest"] == review_digest(p["storyboard_review"])
    return waiver["at"] == p["storyboard_review"]["at"]


def board_problems(p, path, shot_ids):
    record = p.get("storyboard_review")
    if not record:
        return ["No blind board review recorded. Run it and save the verdict with `review.py verdict`."]
    if record["verdict"] != "pass" and not waived(p):
        return ["The last blind board review failed. Repair the failed relationships and review again."]
    digests = shot_digests(p, path)
    stale = changed_shots(record["shots"], digests, shot_ids or list(digests))
    return [f"Changed since the blind review: {', '.join(stale)}. Review the board again."] if stale else []


def cast_files(p):
    """The character images a cast check compares: each selected master and its reference views."""
    files = []
    for asset in p["assets"]:
        if asset.get("kind") == "character":
            version = selected(asset)
            files += [version["image"]] if version.get("image") else []
            files += [view["image"] for view in version.get("reference_views", []) if view.get("image")]
    return files


def sound_files(p):
    """The audio a sound check hears: every dialogue take and every effect file under a shot."""
    files = []
    for shot in p["shots"]:
        files += [line["audio"] for line in shot.get("dialogue", []) if line.get("audio")]
        files += shot.get("sound_files", [])
    return files


CHECK_FILES = {"cast": cast_files, "sound": sound_files}


def unready_lines(p):
    """A sound check hears selected takes performed to a written direction; a line without either is not ready."""
    problems = []
    for shot in p["shots"]:
        for line in shot.get("dialogue", []):
            for field in ("audio", "direction"):
                if not str(line.get(field, "")).strip():
                    problems.append(f"{shot['id']}: the line {line.get('line', '')!r} needs its {field}.")
    return problems


def check_problems(p, path):
    """Return what blocks the cast and sound checks; a film without cast or sound needs no such check."""
    root = path.resolve().parent
    problems = []
    for kind, files_of in CHECK_FILES.items():
        files = files_of(p)
        if not files:
            continue
        record = p.get("checks", {}).get(kind)
        if not record:
            problems.append(f"No {kind} check recorded. Run it and save the verdict with `review.py check {kind}`.")
        elif record["verdict"] != "pass":
            problems.append(f"The {kind} check failed. Repair the failed findings and check again.")
        else:
            changed = [f for f in files if record["files"].get(f) != file_sha256(root, f)]
            if changed:
                problems.append(f"Changed since the {kind} check: {', '.join(changed)}. Run the {kind} check again.")
    return problems


def package_problems(p, beat_ids):
    """A creator video plans its title and thumbnail before production; they set what the video must deliver."""
    package = p.get("package") or {}
    problems = []
    if not str(package.get("title", "")).strip():
        problems.append("package.title: plan the video's title before production.")
    if not str((package.get("thumbnail") or {}).get("brief", "")).strip():
        problems.append("package.thumbnail: write the thumbnail brief before production.")
    for component in package.get("critical", []):
        if not component.get("beats") or set(component["beats"]) - beat_ids:
            problems.append(f"package.critical {component.get('item')!r} must name the beats that deliver it.")
    return problems


def beat_record_problems(p):
    shot_ids = {s["id"] for s in p["shots"]}
    problems = []
    for beat in p.get("beats", []):
        name = beat.get("id")
        if beat.get("role") not in BEAT_ROLES:
            problems.append(f"{name}: role {beat.get('role')!r} is not one of {', '.join(BEAT_ROLES)}.")
        if "energy" in beat and beat["energy"] not in range(1, 6):
            problems.append(f"{name}: energy must be a whole number from 1 to 5, not {beat['energy']!r}.")
        if not beat.get("shots") or set(beat["shots"]) - shot_ids:
            problems.append(f"{name}: shots must list shot IDs of this project, not {beat.get('shots')!r}.")
    return problems


def beat_spans(p):
    """{beat id: (start, end)} in seconds, from the shots each beat lists."""
    shots = {s["id"]: s for s in p["shots"]}
    return {
        b["id"]: (
            min(shots[i]["start"] for i in b["shots"]),
            max(shots[i]["start"] + shots[i]["duration"] for i in b["shots"]),
        )
        for b in p.get("beats", [])
    }


def setup_problems(beats, spans):
    """Each setup names a later payoff, and each payoff has a setup that names it."""
    payoffs = {b["id"] for b in beats if b["role"] == "payoff"}
    named = set()
    problems = []
    for beat in (b for b in beats if b["role"] == "setup"):
        targets = [t for t in beat.get("sets_up", []) if t in payoffs]
        named.update(targets)
        if not targets:
            problems.append(f"{beat['id']}: a setup needs sets_up naming its payoff beat.")
        problems += [
            f"{beat['id']}: sets up {t}, which must come later." for t in targets if spans[t][0] <= spans[beat["id"]][0]
        ]
    problems += [f"{b}: a payoff needs a setup beat that names it in sets_up." for b in sorted(payoffs - named)]
    return problems


def timing_problems(p, beats, spans):
    settings = profile_settings(p)
    problems = []
    limit = settings["promise_by_seconds"]
    promises = [b["id"] for b in beats if b["role"] == "promise"]
    if not promises:
        problems.append(
            f"Add a promise beat: what the title and thumbnail promise, delivered in the first {limit:g} s."
        )
    elif min(spans[b][1] for b in promises) > limit:
        first = min(promises, key=lambda b: spans[b][1])
        problems.append(
            f"The promise beat {first} ends at {spans[first][1]:g} s; the {profile(p)} profile needs it "
            f"within the first {limit:g} s (settings.promise_by_seconds)."
        )
    for low, high in settings.get("re_engage_windows", []):
        if not any(b["role"] == "re_engage" and low <= spans[b["id"]][0] <= high for b in beats):
            problems.append(f"Add a re_engage beat that starts between {low:g} and {high:g} s.")
    # Beats that share a span keep their listed order.
    last = max(enumerate(beats), key=lambda pair: (spans[pair[1]["id"]], pair[0]))[1]
    if last["role"] != "payoff":
        problems.append(f"The last beat, {last['id']}, is a {last['role']}; end on a payoff.")
    return problems


def length_problems(p):
    settings = profile_settings(p)
    total = max(s["start"] + s["duration"] for s in p["shots"])
    problems = []
    if total > settings.get("max_seconds", float("inf")):
        problems.append(
            f"The film runs {total:g} s; the {profile(p)} profile allows at most {settings['max_seconds']:g} s."
        )
    if total < settings.get("min_seconds", 0):
        problems.append(
            f"The film runs {total:g} s; the {profile(p)} profile needs at least {settings['min_seconds']:g} s."
        )
    return problems


def beat_problems(p):
    """What a short plan lacks: the package, the length, and beat roles that promise, set up and pay off."""
    beats = p.get("beats", [])
    problems = package_problems(p, {b.get("id") for b in beats}) + length_problems(p)
    if not beats:
        return [*problems, "Add beats: each with an id, a role, its shots and an energy from 1 to 5."]
    record = beat_record_problems(p)
    if record:
        return problems + record
    spans = beat_spans(p)
    return problems + setup_problems(beats, spans) + timing_problems(p, beats, spans)


def clock(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def beat_report(p):
    """The beat plan by minute mark, with a text energy curve; empty while a beat record is broken."""
    if beat_record_problems(p):
        return []
    spans = beat_spans(p)
    return [
        f"{clock(spans[b['id']][0])}-{clock(spans[b['id']][1])}  {b['id']:<4} {b['role']:<9} {'#' * b.get('energy', 0)}"
        for b in sorted(p.get("beats", []), key=lambda b: spans[b["id"]])
    ]


def readiness(p, path, shot_ids=None):
    """Return what blocks these shots (default all) from reaching the producer; empty means ready."""
    problems = staging_problems(p)
    if problems:
        return problems
    problems = board_problems(p, path, shot_ids) + check_problems(p, path)
    return problems + (beat_problems(p) if profile(p) != "drama" else [])


def gate(p, path, shot_ids):
    """Return what blocks video submission for these shots; empty means submission may proceed."""
    digests = shot_digests(p, path) if not staging_problems(p) else {}
    unknown = set(shot_ids or []) - {s["id"] for s in generated_shots(p)}
    if unknown:
        raise ValueError(f"Unknown shot IDs: {sorted(unknown)}")
    problems = readiness(p, path, shot_ids)
    if problems:
        return problems
    approval = p.get("storyboard_approval")
    if not approval:
        return [
            "No producer approval recorded. Present the board and record the producer's words with `review.py approve`."
        ]
    stale = changed_shots(approval["shots"], digests, shot_ids or list(digests))
    return (
        [f"Changed since producer approval: {', '.join(stale)}. Present these shots for renewed approval."]
        if stale
        else []
    )


def check_verdict(verdict, needs_tell_back=True):
    findings = verdict.get("findings")
    if verdict.get("verdict") not in ("pass", "fail") or not findings:
        raise ValueError("A verdict needs verdict pass/fail and at least one finding")
    if needs_tell_back and not str(verdict.get("tell_back", "")).strip():
        raise ValueError("A verdict needs the reviewer's tell_back from phase 1")
    for f in findings:
        if (
            f.get("result") not in ("pass", "fail", "unassessable")
            or not f.get("relationship")
            or not f.get("evidence")
        ):
            raise ValueError(f"Each finding needs relationship, result pass/fail/unassessable and evidence: {f}")
    if verdict["verdict"] == "pass" and any(is_blocking(f) for f in findings):
        raise ValueError("A passing verdict cannot contain a failed finding that blocks")


def check_board_verdict(verdict):
    """A failed board finding carries the reviewer's severity: block keeps the board back, revise goes to the producer."""
    findings = verdict.get("findings") or []
    for f in findings:
        if f.get("result") == "fail" and f.get("severity") not in SEVERITIES:
            raise ValueError(f"Each failed finding needs severity block or revise: {f}")
    if verdict.get("verdict") == "fail" and not any(is_blocking(f) for f in findings):
        raise ValueError("A failing board verdict needs at least one finding with severity block")
    check_verdict(verdict)


def record_verdict(p, path, verdict):
    check_board_verdict(verdict)
    problems = staging_problems(p)
    if problems:
        raise ValueError("Blind review needs the staging map first: " + " ".join(problems))
    problems = card_problems(p)
    if problems:
        raise ValueError("Blind review needs complete layout cards: " + " ".join(problems))
    out = copy.deepcopy(p)
    out["storyboard_review"] = {
        "at": now(),
        "verdict": verdict["verdict"],
        "tell_back": verdict["tell_back"],
        "shots": shot_digests(p, path),
        "findings": verdict["findings"],
    }
    out.setdefault("history", []).append({"at": now(), "kind": "blind_board_review", "verdict": verdict["verdict"]})
    out["revision"] += 1
    return out


def record_check(p, path, kind, verdict):
    """Record a fresh reviewer's cast or sound verdict, pinned to the files it judged."""
    if kind not in CHECK_FILES:
        raise ValueError(f"Unknown check {kind!r}; use one of {sorted(CHECK_FILES)}")
    check_verdict(verdict, needs_tell_back=False)
    if kind == "sound":
        problems = unready_lines(p)
        if problems:
            raise ValueError("The sound check needs every line's take and direction: " + " ".join(problems))
    root = path.resolve().parent
    out = copy.deepcopy(p)
    out.setdefault("checks", {})[kind] = {
        "at": now(),
        "verdict": verdict["verdict"],
        "files": {f: file_sha256(root, f) for f in CHECK_FILES[kind](p)},
        "findings": verdict["findings"],
    }
    out.setdefault("history", []).append({"at": now(), "kind": f"{kind}_check", "verdict": verdict["verdict"]})
    out["revision"] += 1
    return out


def approve(p, path, text, waive_review=False):
    if not text.strip():
        raise ValueError("Record the producer's own approval words")
    out = copy.deepcopy(p)
    out["storyboard_approval"] = {"at": now(), "user_words": text, "shots": shot_digests(p, path)}
    if open_revisions(p):
        out["storyboard_approval"]["revise"] = open_revisions(p)
    if waive_review:
        review = p.get("storyboard_review") or {}
        if review.get("verdict") != "fail":
            raise ValueError("A waiver accepts a failed blind review; the last review did not fail")
        failed = sum(f["result"] == "fail" for f in review["findings"])
        out["storyboard_approval"]["waived_review"] = {
            "at": review["at"],
            "failed": failed,
            "digest": review_digest(review),
        }
    problems = readiness(out, path)
    if problems:
        raise ValueError("The board is not ready for approval: " + " ".join(problems))
    entry = {"at": now(), "kind": "storyboard_approval", "user_words": text}
    if waive_review:
        entry["waived_review"] = out["storyboard_approval"]["waived_review"]
    out.setdefault("history", []).append(entry)
    out["revision"] += 1
    return out


def note(p, user_words, interpretation):
    out = copy.deepcopy(p)
    out.setdefault("history", []).append(
        {"at": now(), "kind": "user_feedback", "user_words": user_words, "interpretation": interpretation}
    )
    out["revision"] += 1
    return out


PAGE = (pathlib.Path(__file__).resolve().parent.parent / "assets" / "review.html").read_text()


def validate_media_paths(p, path):
    """Keep live creative dependencies and deliverables inside their project."""
    root = path.resolve().parent
    paths = []
    if p.get("storyboard"):
        paths.append(p["storyboard"])
    if p.get("staging", {}).get("map"):
        paths.append(p["staging"]["map"])
    paths.extend(x["path"] for x in p.get("exports", []) if x.get("path"))
    media_keys = (
        "image",
        "reference",
        "storyboard_image",
        "video",
        "audio",
        "reference_audio",
        "reference_card",
        "identity_comparison",
    )
    for node in p["assets"] + p["shots"]:
        for version in node["versions"]:
            paths.extend(version[k] for k in media_keys if version.get(k))
            paths.extend(guide["image"] for guide in version.get("guides", []) if guide.get("image"))
            paths.extend(view["image"] for view in version.get("reference_views", []) if view.get("image"))
            paths.extend(line["audio"] for line in version.get("lines", []) if line.get("audio"))
    paths.extend(sound_files(p))
    for value in paths:
        rel = pathlib.Path(value)
        target = (root / rel).resolve()
        if rel.is_absolute() or "://" in value or not target.is_relative_to(root):
            raise ValueError(f"Import external media into the project before use: {value}")
        if not target.is_file():
            raise ValueError(f"Registered media is missing: {value}")


def build(p, path):
    validate_media_paths(p, path)
    data = copy.deepcopy(p)
    data["_stale"] = stale_nodes(p)
    if PROFILES[profile(p)].get("aspect_ratio"):
        data["settings"].setdefault("aspect_ratio", PROFILES[profile(p)]["aspect_ratio"])
    void = set(void_approvals(p, path))
    for node in data["assets"] + data["shots"]:
        for version in node["versions"]:
            if (node["id"], version["id"]) in void:
                version.update(review_status="unreviewed", approval_void=True)
    encoded = (
        json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    out = path.parent / "review.html"
    out.write_text(PAGE.replace("__DATA__", encoded), encoding="utf-8")
    return out


def write_atomic(path, obj):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
        tmp = pathlib.Path(f.name)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in [
        "build",
        "feedback",
        "plan",
        "ready",
        "gate",
        "lint",
        "beats",
        "verdict",
        "check",
        "approve",
        "note",
    ]:
        c = sub.add_parser(command)
        c.add_argument("project", type=pathlib.Path)
        if command == "check":
            c.add_argument("kind", choices=sorted(CHECK_FILES))
            c.add_argument("verdict", type=pathlib.Path)
        if command in ("feedback", "verdict"):
            c.add_argument(command, type=pathlib.Path)
        if command == "plan":
            c.add_argument("--changed", nargs="+", required=True)
        if command == "gate":
            c.add_argument("--shots", nargs="+", help="Shots about to be submitted; default all")
        if command == "approve":
            c.add_argument("--user-words", required=True, help="The producer's approval, verbatim")
            c.add_argument(
                "--waive-review", action="store_true", help="The producer accepts the failed blind review as it stands"
            )
        if command == "note":
            c.add_argument("--user-words", required=True, help="The producer's feedback, verbatim")
            c.add_argument("--interpretation", required=True)
    args = parser.parse_args()
    path = args.project.resolve()
    p = json.loads(path.read_text())
    validate(p)
    validate_media_paths(p, path)
    if args.command in ("ready", "gate"):
        problems = readiness(p, path) if args.command == "ready" else gate(p, path, args.shots)
        report = {"ok": not problems, "problems": problems}
        if args.command == "ready" and open_revisions(p):
            report["revise"] = open_revisions(p)
        print(json.dumps(report, indent=2))
        sys.exit(1 if problems else 0)
    if args.command == "beats":
        problems = beat_problems(p)
        print(
            json.dumps(
                {"ok": not problems, "profile": profile(p), "beats": beat_report(p), "problems": problems},
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.exit(1 if problems else 0)
    if args.command == "lint":
        problems = card_problems(p)
        print(json.dumps({"ok": not problems, "problems": problems}, indent=2, ensure_ascii=False))
        sys.exit(1 if problems else 0)
    if args.command == "plan":
        print(json.dumps(plan(p, args.changed), indent=2))
        return
    if args.command == "build":
        print(build(p, path))
        return
    if args.command == "feedback":
        out = apply_feedback(p, json.loads(args.feedback.read_text()), path)
    elif args.command == "verdict":
        out = record_verdict(p, path, json.loads(args.verdict.read_text()))
    elif args.command == "check":
        out = record_check(p, path, args.kind, json.loads(args.verdict.read_text()))
    elif args.command == "approve":
        out = approve(p, path, args.user_words, args.waive_review)
    else:
        out = note(p, args.user_words, args.interpretation)
    validate(out)
    write_atomic(path, out)
    print(build(out, path))


if __name__ == "__main__":
    main()
