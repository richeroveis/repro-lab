"""Compile the ReproLab demo brief: a 48 to 52 second subtitled MP4 with audio.

Everything on screen is read back from this repository's own studionet evidence:

  * frontend/public/snapshot.json          live ledger state and study cards
  * evidence/explorer-verification.json    explorer verified transaction records
  * evidence/identity.txt                  four way source identity hashes

No stock media, no third party footage. Frames are drawn with Pillow, the stereo
ambience is synthesized with numpy, and ffmpeg (from imageio-ffmpeg when no
system build is present) muxes with libx264 video and aac audio.

Usage:
    python scripts/compile_empirical_video_brief.py

Outputs:
    docs/demo-video-subtitled.mp4
    frontend/public/demo-video-subtitled.mp4
    docs/demo-video-subtitles.srt
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 24
SAMPLE_RATE = 44100

INK = (11, 19, 43)
SLATE = (28, 37, 65)
PANEL = (17, 26, 51)
CYAN = (6, 182, 212)
GREEN = (16, 185, 129)
AMBER = (245, 158, 11)
RED = (244, 63, 94)
TEXT = (226, 232, 240)
DIM = (148, 163, 184)
GRID = (38, 50, 84)

FONT_DIR = "C:/Windows/Fonts"
SERIF = os.path.join(FONT_DIR, "georgiabi.ttf")
SERIF_R = os.path.join(FONT_DIR, "georgia.ttf")
SANS = os.path.join(FONT_DIR, "arial.ttf")
SANS_B = os.path.join(FONT_DIR, "arialbd.ttf")
MONO = os.path.join(FONT_DIR, "consolab.ttf")
MONO_R = os.path.join(FONT_DIR, "consola.ttf")

BANDS = {
    "EXACT_REPLICATION_VERIFIED": GREEN,
    "PARTIAL_CONVERGENCE_TIER": CYAN,
    "INCONCLUSIVE_VARIANCE_REFUND": AMBER,
    "FABRICATED_DATA_SLASH": RED,
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (path, MONO_R, SANS):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def gen(wei) -> str:
    try:
        return f"{int(str(wei)) / 1e18:.2f}"
    except (TypeError, ValueError):
        return "0.00"


def load_data() -> dict:
    data = {"snapshot": {}, "explorer": {}, "identity": "", "txs": [], "reconciliation": {}}
    if os.path.exists("frontend/public/snapshot.json"):
        with open("frontend/public/snapshot.json", encoding="utf-8") as handle:
            data["snapshot"] = json.load(handle)
    if os.path.exists("frontend/public/custody-reconciliation.json"):
        with open("frontend/public/custody-reconciliation.json", encoding="utf-8") as handle:
            data["reconciliation"] = json.load(handle)
    if os.path.exists("evidence/explorer-verification.json"):
        with open("evidence/explorer-verification.json", encoding="utf-8") as handle:
            data["explorer"] = json.load(handle)
    if os.path.exists("evidence/identity.txt"):
        with open("evidence/identity.txt", encoding="utf-8") as handle:
            data["identity"] = handle.read()
    if os.path.exists("evidence/_txs.jsonl"):
        with open("evidence/_txs.jsonl", encoding="utf-8") as handle:
            data["txs"] = [json.loads(line) for line in handle if line.strip()]
    return data


def find_tx(data: dict, step: str) -> dict:
    for row in data["explorer"].get("records", []):
        if row.get("step") == step:
            return row
    return {}


def short_band(band: str) -> str:
    return {
        "EXACT_REPLICATION_VERIFIED": "EXACT",
        "PARTIAL_CONVERGENCE_TIER": "PARTIAL",
        "INCONCLUSIVE_VARIANCE_REFUND": "VARIANCE",
        "FABRICATED_DATA_SLASH": "FRAUD",
    }.get(band, band[:10] or "OPEN")


def band_label(card: dict) -> str:
    """Band chip for a study row: the bound band, or why there is none."""
    band = str(card.get("verdict_band", ""))
    if band:
        return short_band(band)
    status = str(card.get("status", ""))
    if status.startswith("EXPIRED"):
        return "EXPIRED"
    if status == "OPEN":
        return "OPEN"
    return "CHALLENGED"


def band_colour(card: dict) -> tuple:
    band = str(card.get("verdict_band", ""))
    if band:
        return BANDS.get(band, DIM)
    if str(card.get("status", "")).startswith("EXPIRED"):
        return AMBER
    return DIM


def audited(card: dict, *names: str) -> int:
    """Read an audited value, tolerating the card alias for a decision field."""
    for name in names:
        value = card.get(name)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


# ---------------------------------------------------------------------------
# drawing helpers


def plate(draw: ImageDraw.ImageDraw, box, fill=PANEL, outline=GRID, radius=14, width=2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def header(draw: ImageDraw.ImageDraw, kicker: str, title: str) -> None:
    draw.text((64, 42), kicker.upper(), font=font(MONO, 20), fill=CYAN)
    size = 42
    f = font(SERIF_R, size)
    # Long module names shrink to fit the plate instead of running off frame.
    while size > 24 and draw.textlength(title, font=f) > W - 128:
        size -= 2
        f = font(SERIF_R, size)
    draw.text((64, 70), title, font=f, fill=TEXT)
    draw.line([(64, 132), (W - 64, 132)], fill=GRID, width=2)


def caption_band(draw: ImageDraw.ImageDraw, text: str) -> None:
    box = [0, H - 118, W, H - 34]
    draw.rectangle(box, fill=(6, 11, 26))
    draw.line([(box[0], box[1]), (box[2], box[1])], fill=GRID, width=2)
    f = font(SANS, 30)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=f)
    x = (W - (right - left)) // 2
    draw.text((x, box[1] + 22), text, font=f, fill=(235, 241, 249))


def rule_row(draw: ImageDraw.ImageDraw, y: int, label: str, value: str, colour=TEXT) -> None:
    draw.text((88, y), label, font=font(SANS, 26), fill=DIM)
    right = draw.textlength(value, font=font(MONO, 26))
    draw.text((W - 96 - right, y), value, font=font(MONO, 26), fill=colour)


# ---------------------------------------------------------------------------
# scenes


def scene_title(draw, t: float, data: dict) -> None:
    fade = min(1.0, t / 0.7)
    tint = tuple(int(a + (b - a) * fade) for a, b in zip(INK, (13, 22, 48)))
    draw.rectangle([0, 0, W, H], fill=tint)
    ring_r = 150 + 26 * math.sin(t * 1.1)
    draw.ellipse([W // 2 - ring_r, 250 - ring_r, W // 2 + ring_r, 250 + ring_r], outline=CYAN, width=3)
    for index in range(40):
        angle = index * 2 * math.pi / 40
        major = index % 4 == 0
        r0 = ring_r - (22 if major else 10)
        draw.line(
            [
                (W // 2 + r0 * math.cos(angle), 250 + r0 * math.sin(angle)),
                (W // 2 + ring_r * math.cos(angle), 250 + ring_r * math.sin(angle)),
            ],
            fill=CYAN if major else SLATE,
            width=4 if major else 2,
        )
    for shift, colour in ((-16, AMBER), (14, GREEN)):
        pts = []
        for x in range(W // 2 - 110, W // 2 + 112, 6):
            k = (x - (W // 2 - 110)) / 220
            y = 250 + shift * (1 - k) ** 1.8 + 9 * math.sin(k * 9 + t * 2) * (1 - k)
            pts.append((x, y))
        draw.line(pts, fill=colour, width=5)
    title = "ReproLab"
    f = font(SERIF, 76)
    left, _, right, _ = draw.textbbox((0, 0), title, font=f)
    draw.text(((W - (right - left)) / 2, 432), title, font=f, fill=TEXT)
    sub = "Empirical Replication Notebook and Peer-Review Ledger"
    f2 = font(SANS, 27)
    left, _, right, _ = draw.textbbox((0, 0), sub, font=f2)
    draw.text(((W - (right - left)) / 2, 520), sub, font=f2, fill=DIM)
    tag = "GenLayer studionet  chain id 61999  intelligent contract"
    f3 = font(MONO, 21)
    left, _, right, _ = draw.textbbox((0, 0), tag, font=f3)
    draw.text(((W - (right - left)) / 2, 562), tag, font=f3, fill=CYAN)


def scene_registry(draw, t: float, data: dict) -> None:
    header(draw, "module one", "Empirical Study Registry and Endowment Custody Vault")
    snap = data["snapshot"]
    overview = snap.get("overview", {})
    cards = snap.get("cards", {})
    rule_row(draw, 158, "Endowment pool held by the ledger", gen(overview.get("endowment_pool_atto", 0)) + " GEN", GREEN)
    rule_row(draw, 198, "RLT endowment in vault custody", gen(overview.get("vault_custody_balance", 0)) + " RLT", CYAN)
    rule_row(draw, 238, "Studies registered / settled", f"{overview.get('study_count', 0)} / {overview.get('settled_studies', 0)}", TEXT)
    rule_row(draw, 278, "Soft failed payables absorbed as credit", str(overview.get("soft_fail_count", 0)), AMBER)

    y = 320
    titles = {
        "1": "Sanger Sequencing Read Accuracy Benchmark",
        "2": "LLM Quantization Perplexity Drift Study",
        "3": "CRISPR Off-Target Cleavage Dataset Benchmark",
        "4": "Superconductor Meissner Curve Reproduction",
    }
    for index, sid in enumerate(["1", "2", "3", "4"]):
        card = cards.get(sid, {})
        if not card:
            continue
        reveal = max(0.0, min(1.0, (t - 0.5 - index * 0.45) / 0.5))
        if reveal <= 0:
            continue
        row_h = 56
        plate(draw, [64, y, 64 + int((W - 128) * reveal), y + row_h], fill=(15, 24, 46))
        if reveal > 0.85:
            colour = band_colour(card)
            draw.text((84, y + 6), titles[sid], font=font(SERIF_R, 24), fill=TEXT)
            draw.text((84, y + 32), str(card.get("status", "OPEN")), font=font(MONO, 17), fill=DIM)
            draw.text((700, y + 6), "endowment " + gen(card.get("endowment_atto", 0)) + " GEN", font=font(MONO, 19), fill=DIM)
            draw.text((700, y + 30), "grant " + gen(card.get("derived_replicator_grant", 0)) + " GEN", font=font(MONO, 19), fill=colour)
            label = band_label(card)
            tw = draw.textlength(label, font=font(MONO, 22))
            bx = W - 96 - tw - 24
            plate(draw, [bx, y + 10, W - 96, y + row_h - 10], fill=(10, 18, 36), outline=colour, radius=8)
            draw.text((bx + 12, y + 14), label, font=font(MONO, 22), fill=colour)
        y += row_h + 8
    draw.text((64, 578), "Rejected payables are credited and withdrawable, they never revert with value attached",
              font=font(SANS, 20), fill=DIM)


def scene_matrix(draw, t: float, data: dict) -> None:
    header(draw, "module two", "Statistical Convergence and Effect-Size Deviation Matrix")
    cards = data["snapshot"].get("cards", {})
    labels = {"1": "sequencing", "2": "drift", "3": "crispr", "4": "meissner"}
    col_w = (W - 128 - 30) // 4
    top = 190
    height = 300
    for index in range(5):
        y = top + height - index * (height // 4)
        draw.line([(64, y), (W - 64, y)], fill=GRID, width=1)
        draw.text((34, y - 12), f"{index * 2500}", font=font(MONO, 16), fill=DIM)
    for column, sid in enumerate(["1", "2", "3", "4"]):
        card = cards.get(sid, {})
        x0 = 64 + column * (col_w + 10)
        baseline = audited(card, "audited_baseline_bps", "quantized_reported_baseline_bps")
        replicated = audited(card, "audited_replicated_bps", "quantized_replicated_score_bps")
        integrity = audited(card, "audited_integrity_bps", "dataset_integrity_bps")
        deviation = audited(card, "deviation_bps")
        colour = band_colour(card)
        evaluated = bool(str(card.get("verdict_band", "")))
        for slot, value in enumerate((baseline, replicated, integrity)):
            if value <= 0:
                continue
            grow = max(0.0, min(1.0, (t - 0.4 - column * 0.35 - slot * 0.18) / 0.55))
            bar_h = int(height * value / 10000 * grow)
            bx = x0 + 26 + slot * (col_w // 3)
            bw = col_w // 3 - 18
            shade = (30, 44, 78) if slot < 2 else colour
            draw.rectangle([bx, top + height - bar_h, bx + bw, top + height], fill=shade)
            if grow > 0.9:
                draw.text((bx, top + height - bar_h - 24), f"{value}", font=font(MONO, 18), fill=DIM)
        draw.text((x0 + 26, top + height + 22), labels[sid], font=font(MONO, 21), fill=TEXT)
        detail = f"dev {deviation} bps" if evaluated else "no valid trial"
        draw.text((x0 + 26, top + height + 50), detail, font=font(MONO, 19), fill=colour)
        if evaluated:
            draw.text((x0 + 26, top + height + 78), short_band(str(card.get("verdict_band", ""))), font=font(MONO, 19), fill=colour)
    draw.text((64, 578), "Baseline, replication and integrity are quantized on the same grid before a band binds",
              font=font(SANS, 20), fill=DIM)


def scene_transcript(draw, t: float, data: dict) -> None:
    header(draw, "module three", "Peer-Review Equivalence Transcript and Protocol Safeguard Drawer")
    ev = find_tx(data, "evaluate-drift")
    row = next((r for r in data["txs"] if r.get("step") == "evaluate-drift"), {})
    card = data["snapshot"].get("cards", {}).get("2", {})
    plate(draw, [64, 148, W - 64, 286], fill=(15, 24, 46))
    draw.text((88, 162), "live consensus evaluation  evaluate_replication_trial", font=font(SERIF_R, 26), fill=TEXT)
    draw.text((88, 198), "tx " + str(ev.get("hash", ""))[:56], font=font(MONO, 19), fill=CYAN)
    draw.text((88, 226), "status " + str(ev.get("status", "")) + "   leader " + str(ev.get("leader_exec", "")) +
              "   equivalence output groups " + str(ev.get("eq_output_groups", 0)), font=font(MONO, 19), fill=TEXT)
    draw.text((88, 254), "consensus " + str(row.get("result_name", "")) + "   rounds " + str(row.get("rounds", "")) +
              "   state " + str(ev.get("state_hash_head", "")), font=font(MONO, 19), fill=DIM)

    votes = {}
    for part in str(ev.get("votes", "")).split(","):
        if "=" in part:
            key, count = part.split("=", 1)
            votes[key] = int(count)
    draw.text((64, 306), "validator votes on the audited ruling", font=font(SANS, 23), fill=DIM)
    x = 64
    for index in range(5):
        colour = GREEN if index < votes.get("agree", 0) else SLATE
        label = "AGREE" if index < votes.get("agree", 0) else "idle"
        plate(draw, [x, 338, x + 210, 378], fill=(10, 18, 36), outline=colour, radius=8)
        draw.text((x + 16, 344), label, font=font(MONO, 21), fill=colour)
        x += 226

    fields = [
        ("verdict_band", short_band(str(card.get("verdict_band", "")))),
        ("quantized_reported_baseline_bps", str(audited(card, "audited_baseline_bps"))),
        ("quantized_replicated_score_bps", str(audited(card, "audited_replicated_bps"))),
        ("dataset_integrity_bps", str(audited(card, "audited_integrity_bps"))),
        ("derived_replicator_grant", gen(card.get("derived_replicator_grant", 0)) + " GEN"),
        ("derived_pi_refund", gen(card.get("derived_pi_refund", 0)) + " GEN"),
        ("derived_fraud_slash", gen(card.get("derived_fraud_slash", 0)) + " GEN"),
    ]
    draw.text((64, 398), "seven decision fields that must match exactly", font=font(SANS, 23), fill=DIM)
    y = 430
    for slot, (name, value) in enumerate(fields):
        if t < 0.5 + 0.30 * slot:
            continue
        draw.text((88, y), name, font=font(MONO, 19), fill=DIM)
        right = draw.textlength(value, font=font(MONO, 19))
        draw.text((W - 96 - right, y), value, font=font(MONO, 19), fill=GREEN)
        draw.line([(88, y + 23), (W - 88, y + 23)], fill=(24, 34, 60), width=1)
        y += 24


def scene_refunds(draw, t: float, data: dict) -> None:
    header(draw, "custody", "Refunds, Expired Studies and the Invariant")
    reconciliation = data.get("reconciliation", {})
    rows = [
        ("inbound native to the ledger", gen(reconciliation.get("inbound_native_atto", 0)) + " GEN", CYAN),
        ("recorded external payouts", gen(reconciliation.get("external_payouts_atto", 0)) + " GEN", AMBER),
        ("ledger native balance", gen(reconciliation.get("ledger_gen_atto", 0)) + " GEN", TEXT),
        ("outstanding liabilities", gen(reconciliation.get("liabilities_atto", 0)) + " GEN", TEXT),
        ("refundable credit left unclaimed", gen(reconciliation.get("credits_outstanding_atto", 0)) + " GEN", GREEN),
    ]
    y = 160
    for index, (label, value, colour) in enumerate(rows):
        if t < 0.4 + index * 0.4:
            continue
        rule_row(draw, y, label, value, colour)
        y += 44
    gate_rows = [r for r in data["explorer"].get("records", []) if r.get("leader_exec") == "ERROR"]
    draw.text((64, y + 22), "temporal gates that reverted and applied no state delta", font=font(SANS, 24), fill=DIM)
    yy = y + 58
    for row in gate_rows:
        if t < 2.6 or yy > 588:
            continue
        draw.text((88, yy), str(row.get("step", "")), font=font(MONO, 21), fill=RED)
        right = draw.textlength("state " + str(row.get("state_hash_head", "")), font=font(MONO, 21))
        draw.text((W - 96 - right, yy), "state " + str(row.get("state_hash_head", "")), font=font(MONO, 21), fill=DIM)
        yy += 32
    draw.text((64, 578), "an early attempt must fail and a late attempt must succeed, both run live",
              font=font(SANS, 20), fill=DIM)


def scene_close(draw, t: float, data: dict) -> None:
    snap = data["snapshot"]
    header(draw, "prove it", "Sources, Address and Verification")
    rule_row(draw, 160, "ReproLab ledger", str(snap.get("ledger", ""))[:46], CYAN)
    rule_row(draw, 200, "RLT endowment token", str(snap.get("rlt_token", ""))[:46], CYAN)
    rule_row(draw, 240, "transactions explorer verified", str(data["explorer"].get("transactions", 0)) + " of 37 FINALIZED", GREEN)
    rule_row(draw, 280, "four way source identity", "sha256 identical for both contracts", GREEN)
    hash_line = ""
    for line in str(data["identity"]).splitlines():
        if "aae879" in line or "repro_lab.py" in line:
            hash_line = line.strip()[:110]
            break
    if hash_line and t > 1.4:
        draw.text((88, 320), hash_line, font=font(MONO, 19), fill=DIM)
    plate(draw, [64, 372, W - 64, 470], fill=(15, 24, 46))
    draw.text((88, 388), "richeroveis.github.io/repro-lab", font=font(SANS, 26), fill=TEXT)
    draw.text((88, 424), "github.com/richeroveis/repro-lab", font=font(SANS, 26), fill=TEXT)
    draw.text((64, 512), "ReproLab  replication claims settle on consensus, not on trust",
              font=font(SERIF_R, 30), fill=GREEN)
    draw.text((64, 560), "py-genlayer pinned runner  no admin override  no manual clock advance",
              font=font(MONO, 21), fill=DIM)


SCENES = [
    ("title", 5.0, scene_title, "ReproLab settles replication claims with validator consensus"),
    ("registry", 9.0, scene_registry, "Four studies registered against a real endowment pool on studionet"),
    ("matrix", 10.0, scene_matrix, "Audited scores snap to a 250 basis point grid before a band is bound"),
    ("transcript", 11.0, scene_transcript, "Live evaluators fetched the artifacts and agreed on all seven decision fields"),
    ("refunds", 8.0, scene_refunds, "Rejected payables become withdrawable credit and the custody books still balance"),
    ("close", 7.0, scene_close, "Every claim in this brief is backed by a transaction and a source hash"),
]


def timeline() -> list[tuple[str, float, float, object, str]]:
    out = []
    start = 0.0
    for name, dur, fn, cap in SCENES:
        out.append((name, start, start + dur, fn, cap))
        start += dur
    return out


def captions() -> list[tuple[float, float, str]]:
    out = []
    for name, begin, end, _fn, cap in timeline():
        span = end - begin
        pieces = [cap]
        if name == "transcript":
            pieces = [cap, "Two independent labs bonded stakes and one challenged the first ruling"]
        if name == "registry":
            pieces = [cap, "The author self-replication attempt was absorbed as a refundable credit"]
        if name == "refunds":
            pieces = [cap, "Every rejected payable became withdrawable credit and was claimed"]
        count = len(pieces)
        for index, text in enumerate(pieces):
            out.append((begin + span * index / count, begin + span * (index + 1) / count, text))
    return out


def check_caption_quality(lines: list[tuple[float, float, str]]) -> None:
    for _begin, _end, text in lines:
        if "\u2014" in text or "--" in text:
            raise SystemExit(f"em dash or double hyphen in caption: {text}")
        if ",," in text or " ," in text or ", ." in text:
            raise SystemExit(f"comma artifact in caption: {text}")
        if not re.fullmatch(r"[A-Za-z0-9 ,.'/:()%-]+", text):
            raise SystemExit(f"unexpected character in caption: {text}")


def srt(lines: list[tuple[float, float, str]], path: str) -> None:
    def stamp(seconds: float) -> str:
        total_ms = int(round(seconds * 1000))
        hh, rem = divmod(total_ms, 3600000)
        mm, rem = divmod(rem, 60000)
        ss, ms = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

    blocks = [f"{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n" for i, (a, b, text) in enumerate(lines, 1)]
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(blocks))


# ---------------------------------------------------------------------------
# audio: synthesized laboratory ambience, stereo


def ambience(duration: float, path: str) -> None:
    n = int(SAMPLE_RATE * duration)
    time = np.arange(n) / SAMPLE_RATE
    rng = np.random.default_rng(20261031)

    def pinkish(seed: int, delay_samples: int) -> np.ndarray:
        local = np.random.default_rng(seed)
        white = local.standard_normal(n + delay_samples)
        base = white[delay_samples: delay_samples + n]
        out = np.zeros(n)
        for lag, coefficient in ((1, 0.63), (7, 0.24), (23, 0.13)):
            tail = white[delay_samples - lag: delay_samples - lag + n]
            out += coefficient * (base * 0.5 + tail * 0.5)
        # One pole low pass gives the room tone its rolled off top end.
        soft = np.zeros(n)
        acc = 0.0
        alpha = 0.022
        for index, value in enumerate(out):
            acc += alpha * (value - acc)
            soft[index] = acc
        return soft + 0.12 * base

    left_room = pinkish(11, 1024)
    right_room = pinkish(23, 1920)

    hum = np.zeros(n)
    for harmonic, level in ((52.0, 1.0), (104.0, 0.42), (156.0, 0.17)):
        hum += level * np.sin(2 * np.pi * harmonic * time)
    breathe = 0.55 + 0.45 * np.sin(2 * np.pi * 0.055 * time + 0.4)
    hum *= 0.016 * breathe

    pad = np.zeros(n)
    chords = [(196.0, 261.63, 329.63), (174.61, 246.94, 311.13), (196.0, 261.63, 349.23)]
    for index, (root, third, fifth) in enumerate(chords):
        start = duration * index / len(chords)
        stop = duration * (index + 1) / len(chords)
        mask = (time >= start) & (time < stop)
        local = time - start
        envelope = np.clip(local / 2.2, 0, 1) * np.clip((stop - time) / 2.4, 0, 1)
        for note, detune in ((root, 0.0), (third, 0.6), (fifth, -0.5)):
            pad += mask * envelope * 0.030 * np.sin(2 * np.pi * (note + detune) * time)
            pad += mask * envelope * 0.010 * np.sin(4 * np.pi * note * time)

    ticks = np.zeros(n)
    step = 1.035
    position = 0.9
    while position < duration - 0.4:
        idx = int(position * SAMPLE_RATE)
        length = int(0.045 * SAMPLE_RATE)
        if idx + length < n:
            local = np.arange(length) / SAMPLE_RATE
            shape = np.exp(-local * 92.0)
            tone = np.sin(2 * np.pi * (1180.0 + 260.0 * rng.random()) * local) * shape
            ticks[idx: idx + length] += 0.055 * tone
            click = np.zeros(length)
            click[: int(0.004 * SAMPLE_RATE)] = 0.05 * rng.standard_normal(int(0.004 * SAMPLE_RATE))
            ticks[idx: idx + length] += click * np.exp(-local * 260.0)
        position += step * (0.86 + 0.28 * rng.random())

    centrifuge = np.zeros(n)
    band_center = 240.0
    for index in range(0, n, SAMPLE_RATE // 4):
        length = min(SAMPLE_RATE // 2, n - index)
        local = np.arange(length) / SAMPLE_RATE
        swell = np.sin(np.pi * local / (length / SAMPLE_RATE)) ** 2
        centrifuge[index: index + length] += 0.02 * swell * np.sin(2 * np.pi * band_center * local)

    left = 0.55 * left_room + hum + pad + ticks + centrifuge
    right = 0.55 * right_room + hum * 0.9 + pad * 0.95 + ticks * 0.82 + centrifuge * 1.05

    def shape(channel: np.ndarray) -> np.ndarray:
        fade = int(1.4 * SAMPLE_RATE)
        channel = channel.copy()
        ramp = np.linspace(0.0, 1.0, fade)
        channel[:fade] *= ramp
        channel[-fade:] *= ramp[::-1]
        peak = float(np.max(np.abs(channel))) or 1.0
        return channel * (0.86 / peak)

    left, right = shape(left), shape(right)
    stereo = np.stack([left, right], axis=1)
    pcm = (stereo * 32767.0).astype("<i2")
    with wave.open(path, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    print(f"audio: {duration:.2f} s stereo wav written to {path}")


# ---------------------------------------------------------------------------
# render and mux


def ffmpeg_exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    from imageio_ffmpeg import get_ffmpeg_exe

    return get_ffmpeg_exe()


def main() -> None:
    data = load_data()
    if not data["snapshot"]:
        raise SystemExit("frontend/public/snapshot.json is missing; run the lifecycle driver first")

    lines = captions()
    check_caption_quality(lines)
    duration = sum(dur for _n, dur, _f, _c in SCENES)
    if not (48.0 <= duration <= 52.0):
        raise SystemExit(f"scene durations must total 48 to 52 s, got {duration}")
    frames_dir = "build/frames"
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs("build", exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    os.makedirs("frontend/public", exist_ok=True)

    total_frames = int(round(duration * FPS))
    marks = timeline()
    for frame_index in range(total_frames):
        t = frame_index / FPS
        image = Image.new("RGB", (W, H), INK)
        draw = ImageDraw.Draw(image)
        for name, begin, end, fn, _cap in marks:
            if begin <= t < end:
                fn(draw, t - begin, data)
                break
        caption = ""
        for a, b, text in lines:
            if a <= t < b:
                caption = text
                break
        if caption:
            caption_band(draw, caption)
        # A thin timecode strip keeps the brief readable as a lab recording.
        draw.rectangle([0, 0, W, 6], fill=(8, 14, 32))
        draw.rectangle([0, 0, W * (t / duration), 6], fill=CYAN)
        image.save(os.path.join(frames_dir, f"{frame_index:04d}.png"))
    print(f"video: {total_frames} frames at {FPS} fps rendered")

    wav_path = "build/lab-ambience.wav"
    ambience(duration, wav_path)
    srt(lines, "docs/demo-video-subtitles.srt")

    out_path = "docs/demo-video-subtitled.mp4"
    exe = ffmpeg_exe()
    command = [
        exe, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", os.path.join(frames_dir, "%04d.png"),
        "-i", wav_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(command, check=True)
    shutil.copyfile(out_path, "frontend/public/demo-video-subtitled.mp4")

    size = os.path.getsize(out_path)
    probe = subprocess.run([exe, "-i", out_path], capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    seconds = 0.0
    if match:
        hh, mm, ss = match.groups()
        seconds = int(hh) * 3600 + int(mm) * 60 + float(ss)
    print(f"muxed: {out_path} {size / (1024 * 1024):.2f} MB duration {seconds:.2f} s")
    print("copied: frontend/public/demo-video-subtitled.mp4")
    if size > 15 * 1024 * 1024:
        raise SystemExit("demo video exceeds the 15 MB limit")
    if not (48.0 <= seconds <= 52.0):
        raise SystemExit(f"demo video duration {seconds:.2f} s is outside 48 to 52 s")
    shutil.rmtree(frames_dir, ignore_errors=True)
    print("scratch frames removed")


if __name__ == "__main__":
    main()
