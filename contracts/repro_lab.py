# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from dataclasses import dataclass, fields
import re

# ReproLab reproducibility bounty ledger: payables soft-fail and never revert
# value; every bounty and bond stays reserved at 150 percent maximum liability.

ERROR_EXPECTED = "[EXPECTED]"
ERROR_TRANSIENT = "[TRANSIENT]"
ERROR_LLM = "[LLM_ERROR]"

GRID_BPS = 250
MAX_BPS = 10000
BAND_EXACT = "EXACT_REPLICATION_VERIFIED"
BAND_PARTIAL = "PARTIAL_CONVERGENCE_TIER"
BAND_INCONCLUSIVE = "INCONCLUSIVE_VARIANCE_REFUND"
BAND_FRAUD = "FABRICATED_DATA_SLASH"
EXACT_DEV_CAP_BPS = 250
EXACT_INTEGRITY_FLOOR_BPS = 9000
PARTIAL_DEV_CAP_BPS = 1000
PARTIAL_GRANT_BPS = 6000
INTEGRITY_BUCKET_GRID = 1000

STATUS_ACTIVE = "ACTIVE"
STATUS_AWAITING_AUTHOR = "AWAITING_AUTHOR_RESPONSE"
STATUS_READY = "READY_FOR_EVALUATION"
STATUS_EVALUATED = "EVALUATED_PENDING_CHALLENGE"
STATUS_FINALIZED = "FINALIZED"
STATUS_EXPIRED = "EXPIRED_NO_VALID_REPLICATION"
OPEN_STATUSES = (STATUS_ACTIVE, STATUS_AWAITING_AUTHOR, STATUS_READY)
SEALED_STATUSES = (STATUS_FINALIZED, STATUS_EXPIRED)

_RESERVE_BPS = 15000
_MIN_ENDOWMENT = 1000000000000000000
_MIN_TRIAL_BOND = 500000000000000000
_MIN_CHALLENGE_BOND = 1000000000000000000
_MIN_WINDOW = 30
_MAX_WINDOW = 60 * 60 * 24 * 7
_MAX_AUTHOR_WINDOW = 60 * 60 * 24 * 2
_MIN_TIMEOUT_WINDOW = 60
_MAX_TIMEOUT_WINDOW = 60 * 60 * 24 * 10
_MAX_TIMEOUT_FROM_NOW = 60 * 60 * 24 * 30
CHALLENGE_WINDOW_SECONDS = 120

_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9 ._:/?=&%#+-]")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _addr(a) -> str:
    """Normalize any address encoding to a lowercase hex key."""
    if isinstance(a, (bytes, bytearray)):
        return "0x" + a.hex()
    return str(a).lower()


def _tkey(study_id, lab: str) -> str:
    return str(int(study_id)) + "|" + _addr(lab)


def _err(reason: str):
    return gl.vm.UserError(ERROR_EXPECTED + " " + reason)


def _sanitize_token(value: str, max_len: int) -> str:
    cleaned = _SAFE_TOKEN.sub("", str(value))
    if cleaned == "":
        raise _err("empty sanitized string")
    return cleaned[:max_len]


def _require_https_url(value: str, label: str) -> str:
    cleaned = _sanitize_token(value, 300)
    if not cleaned.startswith("https://") or len(cleaned) < 16:
        raise _err("bad https url " + label)
    return cleaned


def _require_grid_bps(value: int, label: str) -> int:
    v = int(value)
    if v < 0 or v > MAX_BPS or v % GRID_BPS != 0:
        raise _err("bad grid " + label)
    return v


def _require_sha256_hex(value: str, label: str) -> str:
    cleaned = _sanitize_token(value, 120).lower()
    if not _HEX64.match(cleaned):
        raise _err("bad hex " + label)
    return cleaned


def _now_epoch() -> int:
    """Deterministic GenVM transaction timestamp, never a local clock."""
    raw = gl.message_raw["datetime"]
    if isinstance(raw, int):
        return int(raw)
    text = str(raw).strip()
    if text.isdigit():
        return int(text)
    head = text.split(".")[0].replace("Z", "").replace("T", " ")
    if "+" in head:
        head = head.split("+")[0]
    elif len(head) >= 22 and "-" in head[10:]:
        head = head[: 10 + head[10:].rindex("-")]
    parts = head.split(" ")
    date_bits = parts[0].split("-")
    time_bits = parts[1].split(":") if len(parts) > 1 else ["0", "0", "0"]
    y, mo, d = int(date_bits[0]), int(date_bits[1]), int(date_bits[2])
    # Civil UTC date to days since the Unix epoch.
    yy = y - 1 if mo <= 2 else y
    era = yy // 400
    yoe = yy - era * 400
    mp = mo - 3 if mo > 2 else mo + 9
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468
    return days * 86400 + int(time_bits[0]) * 3600 + int(time_bits[1]) * 60 + int(time_bits[2])


def _num(resp: dict, field: str) -> float:
    raw = resp.get(field)
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError):
        raise gl.vm.UserError(ERROR_LLM + " not numeric " + field)


def _flag(resp: dict, field: str) -> bool:
    raw = resp.get(field)
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    raise gl.vm.UserError(ERROR_LLM + " not bool " + field)


def _need_dict(resp) -> dict:
    if not isinstance(resp, dict):
        raise gl.vm.UserError(ERROR_LLM + " response not dict")
    return resp


def _lazy(value):
    # Lazy is not star-exported; duck-type on the class name.
    if type(value).__name__ == "Lazy":
        return value.get()
    return value


def _derive_payouts(band: str, endowment: int, first_bond: int) -> tuple:
    """Consensus-bound payout thresholds for one band."""
    if band == BAND_FRAUD:
        return 0, endowment, first_bond
    if band == BAND_EXACT:
        return endowment, 0, 0
    if band == BAND_PARTIAL:
        grant = endowment * PARTIAL_GRANT_BPS // 10000
        return grant, endowment - grant, 0
    return 0, endowment, 0


@allow_storage
@dataclass
class ReplicationTrial:
    lab: str
    bond_atto: u256
    claimed_replicated_score_bps: u256
    claimed_dataset_integrity_bps: u256
    data_checksum_sha256: str
    replication_log_url: str
    submitted_at_epoch: u256


@allow_storage
@dataclass
class Study:
    study_id: u256
    title: str
    pi_address: str
    paper_artifact_url: str
    baseline_reported_bps: u256
    endowment_atto: u256
    trial_close_epoch: u256
    author_response_deadline_epoch: u256
    audit_timeout_epoch: u256
    peer_challenge_deadline_epoch: u256
    status: str
    author_responded: bool
    claim_count: u256
    claim_labs: DynArray[str]
    first_claim_lab: str
    first_claim_bond_atto: u256
    challenge_bond_atto: u256
    other_bonds_atto: u256
    bonds_consumed_atto: u256
    verdict_band: str
    audited_baseline_bps: u256
    audited_replicated_bps: u256
    audited_integrity_bps: u256
    slash_target: str
    evaluated_at_epoch: u256


class RLTToken:
    class View:
        def balanceOf(self, owner: Address) -> u256: ...
    class Write:
        def transfer(self, to: Address, value: u256) -> bool: ...
        def deposit_into_ledger(self, ledger: str, depositor: str, value: u256, ref: u256) -> bool: ...


RLTFace = gl.contract_interface(RLTToken)


class ReproLab(gl.Contract):
    rlt_token_address: Address
    vault_custody_balance: u256
    token_balances: TreeMap[str, u256]
    pending_rlt_credit_amount: u256
    pending_rlt_credit_ref: u256

    refundable_balances: TreeMap[str, u256]
    last_payable_rejection: TreeMap[str, str]

    studies: TreeMap[u256, Study]
    trials: TreeMap[str, ReplicationTrial]
    study_ids: DynArray[u256]
    study_counter: u256
    endowment_pool_atto: u256
    external_payouts_atto: u256
    soft_fail_count: u256
    pending_rlt_credit_depositor: str
    def __init__(self, rlt_token: Address):
        self.rlt_token_address = Address(rlt_token)
        self.study_counter = u256(0)


    def _soft_fail_payable(self, reason: str) -> None:
        """Joaquin rule: a payable carrying value never reverts."""
        sender = _addr(gl.message.sender_address)
        value = int(gl.message.value)
        if value > 0:
            self.refundable_balances[sender] = self.refundable_balances.get(sender, u256(0)) + value
        self.last_payable_rejection[sender] = _sanitize_token(reason, 200)
        self.soft_fail_count = u256(int(self.soft_fail_count) + 1)
    def _fail(self, reason: str) -> None:
        """Rule 8: soft-fail with value, revert without."""
        if int(gl.message.value) > 0:
            self._soft_fail_payable(reason)
        else:
            raise _err(reason)

    def _credit_native(self, target: str, amount: int, reason: str) -> None:
        if amount <= 0:
            return
        self.refundable_balances[target] = self.refundable_balances.get(target, u256(0)) + amount
        self.last_payable_rejection[target] = _sanitize_token(reason, 200)
    def _pay_from_pool(self, target: str, amount: int, reason: str) -> None:
        if amount <= 0:
            return
        self.endowment_pool_atto = u256(int(self.endowment_pool_atto) - amount)
        self._credit_native(target, amount, reason)
    def _reserve_for(self, endowment_atto: int) -> int:
        return int(endowment_atto) * _RESERVE_BPS // 10000
    def _outstanding_bonds(self, study: Study) -> int:
        return (int(study.first_claim_bond_atto) + int(study.other_bonds_atto)
                + int(study.challenge_bond_atto) - int(study.bonds_consumed_atto))
    def _locked_and_bonds(self) -> tuple:
        locked = 0
        bonds = 0
        for sid in self.study_ids:
            study = self.studies.get(sid)
            if study is not None and study.status not in SEALED_STATUSES:
                locked += int(study.endowment_atto)
                bonds += max(0, self._outstanding_bonds(study))
        return locked, bonds
    def _total_locked(self) -> int:
        return self._locked_and_bonds()[0]
    def _reserve_required_total(self) -> int:
        """150 percent of escrowed endowments plus every open bond."""
        locked, bonds = self._locked_and_bonds()
        return self._reserve_for(locked) + bonds
    def _compute_study_audit_state(self, study: Study, snapshot_at: int) -> dict:
        """The one invariant gate shared by views and settlement."""
        deviation_bps = abs(int(study.audited_baseline_bps) - int(study.audited_replicated_bps))
        open_status = study.status in OPEN_STATUSES
        reserve = self._reserve_for(int(study.endowment_atto))
        return {
            "study_id": str(int(study.study_id)),
            "status": study.status,
            "band": study.verdict_band,
            "claims": str(int(study.claim_count)),
            "deviation_bps": str(deviation_bps),
            "reserve_required_atto": str(reserve),
            "pool_covered": bool(int(self.endowment_pool_atto) >= reserve),
            "can_evaluate_now": bool(
                open_status and snapshot_at >= int(study.trial_close_epoch)
                and study.claim_count > 0
                and (study.author_responded or snapshot_at >= int(study.author_response_deadline_epoch))),
            "can_settle_now": bool(
                study.status == STATUS_EVALUATED
                and snapshot_at >= int(study.peer_challenge_deadline_epoch)),
            "can_refund_zero_winner": bool(
                open_status and (
                    (snapshot_at >= int(study.trial_close_epoch) and study.claim_count == 0)
                    or snapshot_at >= int(study.audit_timeout_epoch))),
        }
    def _fetch_page_text(self, url: str, label: str) -> str:
        body = str(_lazy(gl.nondet.web.render(url, mode="text")))
        if len(body) < 24:
            raise gl.vm.UserError(ERROR_TRANSIENT + " short fetch " + label)
        return body
    def _run_trial_audit(
        self, artifact_url: str, log_url: str, target: str,
        claimed_rep_bps: int, claimed_int_bps: int, checksum: str,
        endowment: int, first_bond: int,
    ) -> dict:
        """Nondeterministic core: live fetch, quantize, band, derive payouts."""
        artifact_text = self._fetch_page_text(artifact_url, "artifact")[:5000]
        log_text = self._fetch_page_text(log_url, "log")[:5000]

        baseline_resp = _lazy(gl.nondet.exec_prompt(
            "Metrics audit: from the artifact below find the headline "
            "quantitative result named " + target + ". Express it as a 0..10000 "
            "basis-point integer (percentage times 100). Answer 0 only if no "
            "such number exists. JSON {\"effect_size_bps\": number}.\n" + artifact_text,
            response_format="json",
        ))
        live_baseline = _num(_need_dict(baseline_resp), "effect_size_bps")
        quantized_reported_baseline_bps = int(round(live_baseline)) // GRID_BPS * GRID_BPS
        if quantized_reported_baseline_bps > MAX_BPS:
            raise _err("baseline above grid")
        if quantized_reported_baseline_bps == 0:
            raise _err("no quantitative baseline")

        audit_resp = _lazy(gl.nondet.exec_prompt(
            "Replication audit. Verify ledger claims against the log, never "
            "invent numbers: replicated score " + str(claimed_rep_bps) + " bps, "
            "integrity " + str(claimed_int_bps) + " bps, checksum " + checksum
            + ". Judge methodology_valid (real independent replication "
            "protocol), fabrication_detected (checksum tampering, p-hacking, "
            "synthetic logs). JSON {\"methodology_valid\": bool, "
            "\"fabrication_detected\": bool}.\n" + log_text,
            response_format="json",
        ))
        methodology_valid = _flag(_need_dict(audit_resp), "methodology_valid")
        fabrication_detected = _flag(audit_resp, "fabrication_detected")

        quantized_replicated_score_bps = int(claimed_rep_bps)
        dataset_integrity_bps = int(claimed_int_bps) // INTEGRITY_BUCKET_GRID * INTEGRITY_BUCKET_GRID
        deviation_bps = abs(quantized_reported_baseline_bps - quantized_replicated_score_bps)

        if fabrication_detected:
            verdict_band = BAND_FRAUD
        elif deviation_bps <= EXACT_DEV_CAP_BPS and dataset_integrity_bps >= EXACT_INTEGRITY_FLOOR_BPS:
            verdict_band = BAND_EXACT
        elif deviation_bps <= PARTIAL_DEV_CAP_BPS and methodology_valid:
            verdict_band = BAND_PARTIAL
        else:
            verdict_band = BAND_INCONCLUSIVE
        grant, pi_refund, fraud_slash = _derive_payouts(verdict_band, endowment, first_bond)
        return {
            "verdict_band": verdict_band,
            "quantized_reported_baseline_bps": quantized_reported_baseline_bps,
            "quantized_replicated_score_bps": quantized_replicated_score_bps,
            "dataset_integrity_bps": dataset_integrity_bps,
            "derived_replicator_grant": grant,
            "derived_pi_refund": pi_refund,
            "derived_fraud_slash": fraud_slash,
        }


    @gl.public.write
    def deposit_rlt_custody(self, amount_atto: u256) -> None:
        """Pull RLT from the caller into vault custody."""
        if int(amount_atto) <= 0:
            raise _err("deposit must be positive")
        if int(self.pending_rlt_credit_amount) > 0:
            raise _err("pending deposit in flight")
        ref = u256(int(self.pending_rlt_credit_ref) + 1)
        self.pending_rlt_credit_amount = amount_atto
        self.pending_rlt_credit_ref = ref
        self.pending_rlt_credit_depositor = _addr(gl.message.sender_address)
        RLTFace(self.rlt_token_address).emit().deposit_into_ledger(
            str(gl.message.contract_address), self.pending_rlt_credit_depositor,
            amount_atto, ref)
    @gl.public.write.min_gas(leader=1000000, validator=1000000).payable
    def on_rlt_received(self, depositor: str, amount_atto: u256, ref: u256) -> None:
        """Callback credit; only the pinned RLT token may settle."""
        if _addr(gl.message.sender_address) != _addr(self.rlt_token_address):
            raise _err("only RLT token may credit")
        if int(amount_atto) <= 0 or int(ref) != int(self.pending_rlt_credit_ref):
            raise _err("custody credit mismatch")
        if int(self.pending_rlt_credit_amount) != int(amount_atto):
            raise _err("custody credit mismatch")
        depositor = _addr(depositor)
        if depositor != self.pending_rlt_credit_depositor:
            raise _err("custody credit depositor mismatch")
        self.pending_rlt_credit_depositor = ""
        self.token_balances[depositor] = self.token_balances.get(depositor, u256(0)) + amount_atto
        self.vault_custody_balance = u256(int(self.vault_custody_balance) + int(amount_atto))
        self.pending_rlt_credit_amount = u256(0)
    @gl.public.write
    def withdraw_rlt_custody(self, amount_atto: u256) -> None:
        """Return vaulted RLT to the caller's token balance."""
        sender = _addr(gl.message.sender_address)
        held = int(self.token_balances.get(sender, u256(0)))
        if int(amount_atto) <= 0 or held < int(amount_atto) or int(self.vault_custody_balance) < int(amount_atto):
            raise _err("insufficient RLT custody")
        self.token_balances[sender] = u256(held - int(amount_atto))
        self.vault_custody_balance = u256(int(self.vault_custody_balance) - int(amount_atto))
        RLTFace(self.rlt_token_address).emit().transfer(sender, amount_atto)


    @gl.public.write.payable
    def fund_endowment_payable(self) -> None:
        """Lock endowment principal into the escrow pool."""
        value = int(gl.message.value)
        if value < _MIN_ENDOWMENT:
            self._fail("endowment below minimum " + str(_MIN_ENDOWMENT))
            return
        self.endowment_pool_atto = u256(int(self.endowment_pool_atto) + value)
        self.last_payable_rejection[_addr(gl.message.sender_address)] = "funded " + str(value)
    @gl.public.write.payable
    def register_study_bounty_payable(
        self, title: str, paper_artifact_url: str, replication_target: str,
        baseline_reported_bps: u256, endowment_atto: u256,
        trial_open_window_seconds: u256, author_response_window_seconds: u256,
        audit_timeout_window_seconds: u256,
    ) -> None:
        sender = _addr(gl.message.sender_address)
        value = int(gl.message.value)
        now = _now_epoch()
        clean_title = _sanitize_token(title, 120)
        endowment = int(endowment_atto)
        tw = int(trial_open_window_seconds)
        aw = int(author_response_window_seconds)
        twt = int(audit_timeout_window_seconds)
        bad = ""
        artifact_url = target = ""
        baseline_bps = 0
        try:
            artifact_url = _require_https_url(paper_artifact_url, "artifact")
            target = _sanitize_token(replication_target, 80)
            baseline_bps = _require_grid_bps(int(baseline_reported_bps), "baseline")
        except BaseException:
            bad = "bad study inputs"
        if bad != "":
            pass
        elif endowment < _MIN_ENDOWMENT:
            bad = "endowment too small"
        elif tw < _MIN_WINDOW or tw > _MAX_WINDOW:
            bad = "trial window out of band"
        elif aw > _MAX_AUTHOR_WINDOW:
            bad = "author window out of band"
        elif twt < tw + _MIN_TIMEOUT_WINDOW or twt > tw + _MAX_TIMEOUT_WINDOW:
            bad = "timeout window out of band"
        elif twt > _MAX_TIMEOUT_FROM_NOW:
            bad = "timeout too far ahead"
        elif value < endowment:
            bad = "send at least the endowment"
        else:
            # Fail-closed 150 percent reservation.
            pool_after = int(self.endowment_pool_atto) + value - endowment
            reserve_after = self._reserve_for(self._total_locked() + endowment) + self._locked_and_bonds()[1]
            if pool_after < reserve_after:
                bad = "pool fails 150 percent reservation"
        if bad != "":
            self._fail(bad)
            return

        study_id = u256(int(self.study_counter) + 1)
        self.study_counter = study_id
        self.studies[study_id] = Study(
            study_id=study_id, title=clean_title + " [" + target + "]",
            pi_address=sender, paper_artifact_url=artifact_url,
            baseline_reported_bps=baseline_bps, endowment_atto=endowment_atto,
            trial_close_epoch=now + tw,
            author_response_deadline_epoch=now + tw + aw,
            audit_timeout_epoch=now + twt, peer_challenge_deadline_epoch=0,
            status=STATUS_ACTIVE, author_responded=False, claim_count=0,
            claim_labs=[],
            first_claim_lab="", first_claim_bond_atto=0,
            challenge_bond_atto=0, other_bonds_atto=0, bonds_consumed_atto=0,
            verdict_band="", audited_baseline_bps=0, audited_replicated_bps=0,
            audited_integrity_bps=0, slash_target="", evaluated_at_epoch=0)
        self.study_ids.append(study_id)
        self.endowment_pool_atto = u256(pool_after)
        surplus = value - endowment
        if surplus > 0:
            # Surplus is credited back, never locked twice.
            self.endowment_pool_atto = u256(int(self.endowment_pool_atto) - surplus)
            self._credit_native(sender, surplus, "registration surplus returned")
        self.last_payable_rejection[sender] = "study " + str(int(study_id)) + " registered"
    @gl.public.write.payable
    def stake_replication_trial_payable(
        self, study_id: u256, claimed_replicated_score_bps: u256,
        claimed_dataset_integrity_bps: u256, data_checksum_sha256: str,
        replication_log_url: str,
    ) -> None:
        sender = _addr(gl.message.sender_address)
        value = int(gl.message.value)
        now = _now_epoch()
        study = self.studies.get(study_id)
        bad = ""
        claimed_rep = claimed_int = 0
        checksum = log_url = ""
        if study is None:
            bad = "unknown study"
        elif study.status not in OPEN_STATUSES:
            bad = "trials not open"
        elif now >= int(study.trial_close_epoch):
            bad = "trial window closed"
        elif sender == study.pi_address:
            bad = "PI cannot self-replicate"
        elif _tkey(study_id, sender) in self.trials:
            bad = "lab already staked"
        elif value < _MIN_TRIAL_BOND:
            bad = "bond below minimum"
        elif int(self.endowment_pool_atto) - value < self._reserve_required_total():
            bad = "pool cannot reserve new bond"
        else:
            try:
                claimed_rep = _require_grid_bps(int(claimed_replicated_score_bps), "replicated")
                claimed_int = _require_grid_bps(int(claimed_dataset_integrity_bps), "integrity")
                checksum = _require_sha256_hex(data_checksum_sha256, "checksum")
                log_url = _require_https_url(replication_log_url, "log")
            except BaseException:
                bad = "bad trial inputs"
        if bad != "":
            self._fail(bad)
            return

        self.trials[_tkey(study_id, sender)] = ReplicationTrial(
            lab=sender, bond_atto=value,
            claimed_replicated_score_bps=claimed_rep,
            claimed_dataset_integrity_bps=claimed_int,
            data_checksum_sha256=checksum, replication_log_url=log_url,
            submitted_at_epoch=now)
        updated = study
        prior_claims = int(study.claim_count)
        updated.claim_count = u256(prior_claims + 1)
        if prior_claims == 0:
            updated.first_claim_lab = sender
            updated.first_claim_bond_atto = value
        else:
            updated.other_bonds_atto = u256(int(updated.other_bonds_atto) + value)
        updated.claim_labs.append(sender)
        if updated.status == STATUS_ACTIVE:
            updated.status = STATUS_AWAITING_AUTHOR
        self.studies[study_id] = updated
        self.endowment_pool_atto = u256(int(self.endowment_pool_atto) - value)
    @gl.public.write
    def submit_author_response(self, study_id: u256, rebuttal_note: str) -> None:
        now = _now_epoch()
        study = self.studies.get(study_id)
        if study is None:
            raise _err("unknown study")
        if _addr(gl.message.sender_address) != study.pi_address:
            raise _err("only the PI may respond")
        if study.status not in (STATUS_ACTIVE, STATUS_AWAITING_AUTHOR):
            raise _err("response window passed")
        if now >= int(study.trial_close_epoch):
            raise _err("trials closed")
        note = _sanitize_token(rebuttal_note, 200)
        updated = study
        updated.author_responded = True
        updated.status = STATUS_READY
        self.studies[study_id] = updated
        self.last_payable_rejection[study.pi_address] = "author responded " + note[:80]
    @gl.public.write
    def evaluate_replication_trial(self, study_id: u256) -> dict:
        """Live validator audit; gated behind trial close plus rebuttal."""
        now = _now_epoch()
        study = self.studies.get(study_id)
        if study is None:
            raise _err("unknown study")
        gate = self._compute_study_audit_state(study, now)
        if not gate["can_evaluate_now"]:
            raise _err("evaluation gate closed")
        book_key = _tkey(study_id, study.first_claim_lab)
        if book_key not in self.trials:
            raise _err("no staked trial")
        trial = self.trials[book_key]
        if int(self.endowment_pool_atto) < self._reserve_required_total():
            raise _err("pool below reservation")

        # Snapshot storage into plain locals before nondet.
        artifact_url = str(study.paper_artifact_url)
        target = str(study.title)
        endowment = int(study.endowment_atto)
        claimed_rep = int(trial.claimed_replicated_score_bps)
        claimed_int = int(trial.claimed_dataset_integrity_bps)
        checksum = str(trial.data_checksum_sha256)
        log_url = str(trial.replication_log_url)
        first_bond = int(study.first_claim_bond_atto)

        def leader_fn():
            return self._run_trial_audit(
                artifact_url, log_url, target, claimed_rep, claimed_int,
                checksum, endowment, first_bond)

        verdict = _lazy(gl.eq_principle.prompt_comparative(
            leader_fn,
            "All seven decision fields must match exactly between leader and "
            "validator: verdict_band, quantized_reported_baseline_bps, "
            "quantized_replicated_score_bps, dataset_integrity_bps, "
            "derived_replicator_grant, derived_pi_refund, derived_fraud_slash. "
            "One basis point of disagreement on any of them is a veto.")
        )

        updated = study
        updated.status = STATUS_EVALUATED
        updated.verdict_band = str(verdict["verdict_band"])
        updated.audited_baseline_bps = int(verdict["quantized_reported_baseline_bps"])
        updated.audited_replicated_bps = int(verdict["quantized_replicated_score_bps"])
        updated.audited_integrity_bps = int(verdict["dataset_integrity_bps"])
        updated.slash_target = str(study.pi_address)
        updated.peer_challenge_deadline_epoch = now + CHALLENGE_WINDOW_SECONDS
        updated.evaluated_at_epoch = now
        self.studies[study_id] = updated
        return self._compute_study_audit_state(updated, _now_epoch())
    @gl.public.write.payable
    def challenge_replication_ruling_payable(self, study_id: u256, note: str) -> None:
        sender = _addr(gl.message.sender_address)
        value = int(gl.message.value)
        now = _now_epoch()
        study = self.studies.get(study_id)
        bad = ""
        if study is None:
            bad = "unknown study"
        elif study.status != STATUS_EVALUATED:
            bad = "no ruling pending"
        elif now >= int(study.peer_challenge_deadline_epoch):
            bad = "challenge window closed"
        elif sender == study.pi_address or sender == study.first_claim_lab:
            bad = "party cannot self-challenge"
        elif value < _MIN_CHALLENGE_BOND:
            bad = "challenge bond too small"
        elif int(self.endowment_pool_atto) - 2 * value < self._reserve_required_total():
            bad = "pool cannot reserve challenge"
        if bad != "":
            self._fail(bad)
            return
        updated = study
        updated.status = STATUS_READY
        updated.challenge_bond_atto = u256(int(study.challenge_bond_atto) + value)
        self.studies[study_id] = updated
        self.endowment_pool_atto = u256(int(self.endowment_pool_atto) - value)
        self.last_payable_rejection[sender] = "challenge posted " + _sanitize_token(note, 120)
    @gl.public.write
    def settle_replication_grant(self, study_id: u256) -> dict:
        """Rule 10: settles only after the peer-challenge deadline."""
        now = _now_epoch()
        study = self.studies.get(study_id)
        if study is None:
            raise _err("unknown study")
        if study.status != STATUS_EVALUATED:
            raise _err("not evaluated")
        if now < int(study.peer_challenge_deadline_epoch):
            raise _err("challenge window open")
        band = str(study.verdict_band)
        endowment = int(study.endowment_atto)
        first_bond = int(study.first_claim_bond_atto)
        other_bonds = int(study.other_bonds_atto)
        challenge_bond = int(study.challenge_bond_atto)
        grant, pi_refund, fraud_slash = _derive_payouts(band, endowment, first_bond)
        outlay = grant + pi_refund + other_bonds + challenge_bond
        if band == BAND_FRAUD:
            outlay += endowment
        if int(self.endowment_pool_atto) < outlay:
            raise _err("pool cannot settle")

        # Race-safe transition before any payout effect.
        updated = study
        updated.status = STATUS_FINALIZED
        self.studies[study_id] = updated
        self.endowment_pool_atto = u256(int(self.endowment_pool_atto) + endowment)
        replicator = updated.first_claim_lab
        bonds_to_take = first_bond + other_bonds + challenge_bond
        if band == BAND_FRAUD:
            # The offending bond is already escrowed, so it pays the PI.
            self.refundable_balances[updated.slash_target] = self.refundable_balances.get(updated.slash_target, u256(0)) + fraud_slash
            self.last_payable_rejection[updated.slash_target] = _sanitize_token("fraud slash payout", 200)
            self._credit_native(replicator, other_bonds + challenge_bond, "innocent bonds returned")
            self._pay_from_pool(updated.pi_address, endowment, "fraud principal refund")
            updated.bonds_consumed_atto = u256(int(updated.bonds_consumed_atto) + first_bond)
        else:
            self._pay_from_pool(replicator, grant, "replication grant " + band)
            self._pay_from_pool(updated.pi_address, pi_refund, "sponsor share " + band)
            self._credit_native(replicator, bonds_to_take, "bond returned")
            updated.bonds_consumed_atto = u256(int(updated.bonds_consumed_atto) + bonds_to_take)
        self.studies[study_id] = updated
        return self._compute_study_audit_state(updated, _now_epoch())
    @gl.public.write
    def claim_unreplicated_or_expired_refund(self, study_id: u256) -> dict:
        """ProphetGrid: zero-winner or expired studies refund in full."""
        now = _now_epoch()
        study = self.studies.get(study_id)
        if study is None:
            raise _err("unknown study")
        gate = self._compute_study_audit_state(study, now)
        if not gate["can_refund_zero_winner"]:
            raise _err("refund gate closed")
        principal = int(study.endowment_atto)
        outstanding = max(0, self._outstanding_bonds(study))
        if int(self.endowment_pool_atto) < principal + outstanding:
            raise _err("pool cannot fund refund")

        updated = study
        updated.status = STATUS_EXPIRED
        self.studies[study_id] = updated
        self.endowment_pool_atto = u256(int(self.endowment_pool_atto) + principal)
        self._pay_from_pool(updated.pi_address, principal, "zero-winner principal refund")
        if outstanding > 0:
            for lab_addr in updated.claim_labs:
                t = self.trials.get(_tkey(study_id, lab_addr))
                if t is not None:
                    self._credit_native(lab_addr, int(t.bond_atto), "expired trial bond refund")
            updated.bonds_consumed_atto = u256(int(updated.bonds_consumed_atto) + outstanding)
            self.studies[study_id] = updated
        return self._compute_study_audit_state(updated, _now_epoch())
    @gl.public.write
    def withdraw_refund(self, amount: u256) -> None:
        sender = _addr(gl.message.sender_address)
        credit = int(self.refundable_balances.get(sender, u256(0)))
        if int(amount) <= 0 or credit < int(amount):
            raise _err("refund amount exceeds credit")
        self.refundable_balances[sender] = u256(credit - int(amount))
        gl.get_contract_at(Address(sender)).emit_transfer(value=amount)
        self.external_payouts_atto = u256(int(self.external_payouts_atto) + int(amount))
        self.last_payable_rejection[sender] = "withdrew " + str(int(amount))
    @gl.public.write
    def claim_refundable_balance(self) -> None:
        sender = _addr(gl.message.sender_address)
        credit = int(self.refundable_balances.get(sender, u256(0)))
        if credit <= 0:
            raise _err("nothing to claim")
        self.refundable_balances[sender] = u256(0)
        gl.get_contract_at(Address(sender)).emit_transfer(value=u256(credit))
        self.external_payouts_atto = u256(int(self.external_payouts_atto) + credit)
        self.last_payable_rejection[sender] = "claimed " + str(credit)


    @gl.public.view
    def get_study_card(self, study_id: u256) -> dict:
        study = self.studies.get(study_id)
        if study is None:
            return {"study_id": str(int(study_id)), "status": "NOT_FOUND"}
        card = {}
        for f in fields(Study):
            if f.name == "claim_labs":
                card[f.name] = ",".join(str(x) for x in study.claim_labs)
            else:
                card[f.name] = str(getattr(study, f.name))
        grant, pi_refund, fraud_slash = _derive_payouts(
            str(study.verdict_band), int(study.endowment_atto), int(study.first_claim_bond_atto))
        card["derived_replicator_grant"] = str(grant)
        card["derived_pi_refund"] = str(pi_refund)
        card["derived_fraud_slash"] = str(fraud_slash)
        card["now_epoch"] = str(_now_epoch())
        card.update(self._compute_study_audit_state(study, _now_epoch()))
        return card
    @gl.public.view
    def get_trial_book(self, study_id: u256) -> list:
        out = []
        study = self.studies.get(study_id)
        if study is not None:
            for lab_addr in study.claim_labs:
                t = self.trials.get(_tkey(study_id, lab_addr))
                if t is None:
                    continue
                row = {"lab_addr": str(lab_addr)}
                for f in fields(ReplicationTrial):
                    row[f.name] = str(getattr(t, f.name))
                out.append(row)
        return out
    @gl.public.view
    def get_lab_overview(self) -> dict:
        locked, open_bonds = self._locked_and_bonds()
        granted = refunded = slashed = settled = 0
        for sid in self.study_ids:
            study = self.studies.get(sid)
            if study is None or study.status not in SEALED_STATUSES:
                continue
            settled += 1
            grant, refund, slash = _derive_payouts(
                str(study.verdict_band), int(study.endowment_atto),
                int(study.first_claim_bond_atto))
            granted += grant
            refunded += refund
            slashed += slash
        return {
            "study_count": str(len(self.study_ids)),
            "settled_studies": str(settled),
            "open_studies": str(len(self.study_ids) - settled),
            "endowment_pool_atto": str(int(self.endowment_pool_atto)),
            "total_endowment_locked": str(locked),
            "open_bonds_atto": str(open_bonds),
            "reserve_required_atto": str(self._reserve_for(locked) + open_bonds),
            "vault_custody_balance": str(int(self.vault_custody_balance)),
            "total_granted": str(granted),
            "total_refunded": str(refunded),
            "total_slashed": str(slashed),
            "soft_fail_count": str(int(self.soft_fail_count)),
            "snapshot_at_epoch": str(_now_epoch()),
        }
    @gl.public.view
    def get_reproducibility_index(self, start_index: u256, page_size: u256) -> list:
        out = []
        start = int(start_index)
        limit = min(int(page_size), 25)
        for i in range(start, min(start + limit, len(self.study_ids))):
            study = self.studies.get(self.study_ids[i])
            if study is not None:
                out.append(self._compute_study_audit_state(study, _now_epoch()))
        return out
    @gl.public.view
    def get_refundable_balance(self, target: str) -> u256:
        return self.refundable_balances.get(_addr(target), u256(0))
    @gl.public.view
    def get_last_payable_rejection(self, target: str) -> str:
        return str(self.last_payable_rejection.get(_addr(target), "none"))
    @gl.public.view
    def get_rlt_balance(self, target: str) -> u256:
        return self.token_balances.get(_addr(target), u256(0))
    @gl.public.view
    def get_custody_accounting_summary(self) -> dict:
        credits = 0
        for _addr, amount in self.refundable_balances.items():
            credits += int(amount)
        locked = self._total_locked()
        reserve_required = self._reserve_required_total()
        return {
            "endowment_pool_atto": str(int(self.endowment_pool_atto)),
            "total_endowment_locked": str(locked),
            "reserve_required_atto": str(reserve_required),
            "pool_covers_reserve": bool(int(self.endowment_pool_atto) >= reserve_required),
            "vault_custody_balance": str(int(self.vault_custody_balance)),
            "external_payouts_atto": str(int(self.external_payouts_atto)),
            "credits_outstanding_atto": str(credits),
            "snapshot_at_epoch": str(_now_epoch()),
        }
