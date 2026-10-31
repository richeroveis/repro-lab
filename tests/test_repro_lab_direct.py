import pytest

CONTRACT = "contracts/repro_lab.py"
ARTIFACT_URL = "https://arxiv.org/abs/2401.00001"
LOG_URL = "https://github.com/lab/replication-log"
NOTE = "ab12" * 16
EOO = "0x" + "e" * 40
T0 = "2026-01-01T00:00:00+00:00"
T0_EPOCH = 1767225600
E1 = 10 ** 18
BOND = 5 * 10 ** 17
CHALLENGE_BOND = 10 ** 18
LONG_PAGE = "reproducible science artifact with headline metrics reported herein" * 2
BAND_EXACT = "EXACT_REPLICATION_VERIFIED"
BAND_PARTIAL = "PARTIAL_CONVERGENCE_TIER"
BAND_INCONCLUSIVE = "INCONCLUSIVE_VARIANCE_REFUND"
BAND_FRAUD = "FABRICATED_DATA_SLASH"


def hexof(addr):
    """Return the same lowercase hex account key the contract uses. Test
    fixtures hand back either an SDK Address or raw 20 bytes."""
    raw = getattr(addr, "as_bytes", None)
    return "0x" + bytes(raw if raw is not None else addr).hex()


def deploy(direct_deploy, direct_vm, direct_alice):
    direct_vm.warp(T0)
    return direct_deploy(CONTRACT, direct_alice)


def mock_pages(direct_vm):
    direct_vm.mock_web(r".*arxiv\.org.*", {"status": 200, "body": LONG_PAGE})
    direct_vm.mock_web(r".*github\.com.*", {"status": 200, "body": LONG_PAGE})


def mock_audit(direct_vm, baseline, methodology=True, fabrication=False):
    direct_vm.mock_llm(
        r".*Metrics audit.*",
        '{"effect_size_bps": %d}' % baseline,
    )
    direct_vm.mock_llm(
        r".*Replication audit.*",
        '{"methodology_valid": %s, "fabrication_detected": %s}'
        % ("true" if methodology else "false",
           "true" if fabrication else "false"),
    )


def fund(direct_vm, direct_alice, c=None, amount=50 * E1):
    """Fund the escrow pool; when amount is below minimum this soft-fails."""
    direct_vm.sender = direct_alice
    direct_vm.value = amount
    if c is not None:
        c.fund_endowment_payable()
        direct_vm.value = 0
    return amount


def register(direct_vm, c, direct_alice, endowment=10 * E1, baseline=5000,
             tw=300, aw=60, twt=600):
    direct_vm.sender = direct_alice
    direct_vm.value = endowment
    c.register_study_bounty_payable(
        "Perplexity Drift Study", ARTIFACT_URL, "perplexity_drift_reduction",
        baseline, endowment, tw, aw, twt)
    direct_vm.value = 0
    return endowment


def stake(direct_vm, c, lab, study_id=1, replicated=5000, integrity=9500):
    direct_vm.sender = lab
    direct_vm.value = BOND
    c.stake_replication_trial_payable(
        study_id, replicated, integrity, NOTE, LOG_URL)
    direct_vm.value = 0


def funded_registered(direct_vm, c, direct_alice, direct_bob, **kw):
    replicated = kw.pop("replicated", 5000)
    integrity = kw.pop("integrity", 9500)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, **kw)
    direct_vm.sender = direct_bob
    direct_vm.value = BOND
    c.stake_replication_trial_payable(1, replicated, integrity, NOTE, LOG_URL)
    direct_vm.value = 0


# ---------------------------------------------------------------- deployment

def test_deploy_overview_empty(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    ov = c.get_lab_overview()
    assert ov["study_count"] == "0"
    assert ov["endowment_pool_atto"] == "0"


def test_deploy_custody_summary(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    summary = c.get_custody_accounting_summary()
    assert summary["vault_custody_balance"] == "0"
    assert summary["pool_covers_reserve"] in (True, "true")


def test_refundable_balance_zero(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    assert int(c.get_refundable_balance(direct_alice)) == 0


# ------------------------------------------------------- fund soft-failure

def test_fund_credits_pool(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    assert c.get_lab_overview()["endowment_pool_atto"] == str(50 * E1)


def test_fund_below_minimum_soft_fail(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, E1 // 2)
    assert c.get_lab_overview()["endowment_pool_atto"] == "0"
    assert int(c.get_refundable_balance(direct_alice)) == E1 // 2
    assert "below minimum" in c.get_last_payable_rejection(direct_alice)


def test_fund_zero_value_raise(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, None, 0)
    with direct_vm.expect_revert("below minimum"):
        c.fund_endowment_payable()


def test_soft_fail_increments_counter(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, 1)
    assert c.get_lab_overview()["soft_fail_count"] == "1"


# ---------------------------------------------------------------- register

def test_register_requires_funded_pool(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, 3 * E1)
    direct_vm.sender = direct_alice
    direct_vm.value = 3 * E1
    c.register_study_bounty_payable(
        "T", ARTIFACT_URL, "target", 5000, 3 * E1, 300, 60, 600)
    direct_vm.value = 0
    assert c.get_lab_overview()["study_count"] == "0"
    assert "150 percent reservation" in c.get_last_payable_rejection(direct_alice)


def test_register_success(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    assert c.get_lab_overview()["study_count"] == "1"
    card = c.get_study_card(1)
    assert card["status"] == "ACTIVE"
    assert card["endowment_atto"] == str(10 * E1)


def test_register_baseline_off_grid(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, baseline=5010)
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_rejects_http_artifact(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    direct_vm.sender = direct_alice
    direct_vm.value = 10 * E1
    c.register_study_bounty_payable(
        "T", "http://arxiv.org/abs/1", "target", 5000, 10 * E1, 300, 60, 600)
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_trial_window_ceiling(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, tw=8 * 24 * 3600)
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_trial_window_floor(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, tw=5)
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_author_window_ceiling(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, aw=3 * 24 * 3600)
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_timeout_window_bounds(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, twt=301)  # below tw + 60
    assert c.get_lab_overview()["study_count"] == "0"
    register(direct_vm, c, direct_alice, twt=300 + 11 * 24 * 3600)  # above max
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_basline_out_of_range(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, baseline=10250)
    assert c.get_lab_overview()["study_count"] == "0"


def test_register_surplus_soft_credited(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    direct_vm.sender = direct_alice
    direct_vm.value = 12 * E1
    c.register_study_bounty_payable(
        "T", ARTIFACT_URL, "target", 5000, 10 * E1, 300, 60, 600)
    direct_vm.value = 0
    assert c.get_lab_overview()["study_count"] == "1"
    assert int(c.get_refundable_balance(direct_alice)) == 2 * E1


def test_register_reservation_ceiling(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)  # pool 50, max endowment keeps 1.5x cover
    register(direct_vm, c, direct_alice, endowment=20 * E1)
    assert c.get_lab_overview()["study_count"] == "1"
    register(direct_vm, c, direct_alice, endowment=20 * E1)
    assert c.get_lab_overview()["study_count"] == "1"


# ------------------------------------------------------------------- stake

def test_stake_unknown_study(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_bob
    direct_vm.value = BOND
    c.stake_replication_trial_payable(99, 5000, 9500, NOTE, LOG_URL)
    assert "unknown study" in c.get_last_payable_rejection(direct_bob)


def test_stake_pi_self_replication_blocked(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_alice)
    assert c.get_study_card(1)["claims"] == "0"


def test_stake_bond_minimum(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    direct_vm.sender = direct_bob
    direct_vm.value = E1 // 10
    c.stake_replication_trial_payable(1, 5000, 9500, NOTE, LOG_URL)
    direct_vm.value = 0
    assert c.get_study_card(1)["claims"] == "0"


def test_stake_bad_checksum(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    direct_vm.sender = direct_bob
    direct_vm.value = BOND
    c.stake_replication_trial_payable(1, 5000, 9500, "xyz", LOG_URL)
    direct_vm.value = 0
    assert c.get_study_card(1)["claims"] == "0"


def test_stake_off_grid_claim(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob, replicated=5100)
    assert c.get_study_card(1)["claims"] == "0"


def test_stake_success_sets_awaiting(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    card = c.get_study_card(1)
    assert card["status"] == "AWAITING_AUTHOR_RESPONSE"
    assert card["claims"] == "1"
    book = c.get_trial_book(1)
    assert book[0]["bond_atto"] == str(BOND)


def test_stake_duplicate_lab_blocked(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    stake(direct_vm, c, direct_bob)
    assert c.get_study_card(1)["claims"] == "1"


def test_stake_after_close_blocked(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    direct_vm.warp("2026-01-01T01:00:00+00:00")
    stake(direct_vm, c, direct_bob)
    assert c.get_study_card(1)["claims"] == "0"


def test_stake_reservation_race_check(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, 16 * E1)
    register(direct_vm, c, direct_alice, endowment=10 * E1)
    # pool is 16 but 15 must stay reserved, so a 2 bond cannot be covered
    direct_vm.sender = direct_bob
    direct_vm.value = 2 * E1
    c.stake_replication_trial_payable(1, 5000, 9500, NOTE, LOG_URL)
    direct_vm.value = 0
    assert c.get_study_card(1)["claims"] == "0"


# ------------------------------------------------------------ author gate

def test_author_response_only_pi(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only the PI"):
        c.submit_author_response(1, "note")


def test_author_response_sets_ready(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "methods clarified")
    assert c.get_study_card(1)["status"] == "READY_FOR_EVALUATION"


def test_evaluate_gated_before_author_response(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    with direct_vm.expect_revert("evaluation gate closed"):
        c.evaluate_replication_trial(1)


def test_evaluate_gated_after_author_deadline_expiry(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    direct_vm.warp("2026-01-01T00:30:00+00:00")  # past trial close + deadline
    assert c.get_study_card(1)["can_evaluate_now"] in (True, "true")


def test_evaluate_unknown_study_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("unknown study"):
        c.evaluate_replication_trial(7)


# ------------------------------------------------------------- evaluation

def test_evaluate_exact_band(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    state = c.evaluate_replication_trial(1)
    assert state["status"] == "EVALUATED_PENDING_CHALLENGE"
    card = c.get_study_card(1)
    assert card["verdict_band"] == BAND_EXACT
    assert card["derived_replicator_grant"] == str(10 * E1)
    assert card["deviation_bps"] == "0"


def test_evaluate_partial_band(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5250)
    funded_registered(direct_vm, c, direct_alice, direct_bob, replicated=5750)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    card = c.get_study_card(1)
    assert card["verdict_band"] == BAND_PARTIAL
    assert card["derived_replicator_grant"] == str(6 * E1)
    assert card["derived_pi_refund"] == str(4 * E1)


def test_evaluate_inconclusive_band(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob, replicated=7500)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    card = c.get_study_card(1)
    assert card["verdict_band"] == BAND_INCONCLUSIVE
    assert card["derived_pi_refund"] == str(10 * E1)


def test_evaluate_fabrication_band(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000, fabrication=True)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    card = c.get_study_card(1)
    assert card["verdict_band"] == BAND_FRAUD
    assert card["derived_fraud_slash"] == str(BOND)


def test_evaluate_integrity_bucket_quantization(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob, integrity=9250)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    card = c.get_study_card(1)
    # integrity floor fails at bucket 9000? 9499 buckets to 9000, still exact
    assert card["audited_integrity_bps"] == "9000"
    assert card["verdict_band"] == BAND_EXACT


# -------------------------------------------------------------- settlement

def settle_after_challenge(direct_vm, c, offset="00:09:00"):
    direct_vm.warp("2026-01-01T" + offset + "+00:00")
    return c.settle_replication_grant(1)


def test_settle_blocked_during_challenge_window(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    with direct_vm.expect_revert("challenge window open"):
        c.settle_replication_grant(1)


def test_settle_exact_pays_replicator(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    state = settle_after_challenge(direct_vm, c)
    assert state["status"] == "FINALIZED"
    assert int(c.get_refundable_balance(direct_bob)) == 10 * E1 + BOND


def test_settle_partial_splits_grant(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5250)
    funded_registered(direct_vm, c, direct_alice, direct_bob, replicated=5750)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    settle_after_challenge(direct_vm, c)
    assert int(c.get_refundable_balance(direct_bob)) == 6 * E1 + BOND
    assert int(c.get_refundable_balance(direct_alice)) == 4 * E1


def test_settle_inconclusive_refunds_principal(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob, replicated=7500)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    settle_after_challenge(direct_vm, c)
    assert int(c.get_refundable_balance(direct_alice)) == 10 * E1
    assert int(c.get_refundable_balance(direct_bob)) == BOND


def test_settle_fraud_slashes_bond_to_whistleblower(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000, fabrication=True)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    settle_after_challenge(direct_vm, c)
    # offending replicator keeps nothing, PI receives principal refund
    assert int(c.get_refundable_balance(direct_bob)) == 0
    assert int(c.get_refundable_balance(direct_alice)) == 10 * E1 + BOND


def test_settle_not_evaluated_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    with direct_vm.expect_revert("not evaluated"):
        c.settle_replication_grant(1)


def test_settle_overview_stats(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    settle_after_challenge(direct_vm, c)
    ov = c.get_lab_overview()
    assert ov["settled_studies"] == "1"
    assert ov["total_granted"] == str(10 * E1)
    index = c.get_reproducibility_index(0, 10)
    assert index[0]["band"] == BAND_EXACT
    assert ov["open_studies"] == "0"


# ---------------------------------------------------------------- challenge

def test_challenge_self_challenge_blocked(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    direct_vm.sender = direct_alice
    direct_vm.value = CHALLENGE_BOND
    c.challenge_replication_ruling_payable(1, "I am the PI")
    direct_vm.value = 0
    assert c.get_study_card(1)["status"] == "EVALUATED_PENDING_CHALLENGE"


def test_challenge_forces_reevaluation(direct_deploy, direct_vm, direct_alice, direct_bob, direct_charlie):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    direct_vm.sender = direct_charlie
    direct_vm.value = CHALLENGE_BOND
    c.challenge_replication_ruling_payable(1, "independent audit doubts")
    direct_vm.value = 0
    card = c.get_study_card(1)
    assert card["status"] == "READY_FOR_EVALUATION"
    assert card["challenge_bond_atto"] == str(CHALLENGE_BOND)


def test_challenge_window_closed_soft_fail(direct_deploy, direct_vm, direct_alice, direct_bob, direct_charlie):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    direct_vm.warp("2026-01-01T00:30:00+00:00")
    direct_vm.sender = direct_charlie
    direct_vm.value = CHALLENGE_BOND
    c.challenge_replication_ruling_payable(1, "late")
    direct_vm.value = 0
    assert int(c.get_refundable_balance(direct_charlie)) == CHALLENGE_BOND


# ------------------------------------------------------- zero-winner rules

def test_zero_winner_blocked_before_close(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    with direct_vm.expect_revert("refund gate closed"):
        c.claim_unreplicated_or_expired_refund(1)


def test_zero_winner_refunds_principal(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    direct_vm.warp("2026-01-01T00:10:00+00:00")
    state = c.claim_unreplicated_or_expired_refund(1)
    assert state["status"] == "EXPIRED_NO_VALID_REPLICATION"
    assert int(c.get_refundable_balance(direct_alice)) == 10 * E1
    assert c.get_lab_overview()["total_endowment_locked"] == "0"


def test_timeout_refund_with_bonds(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, tw=300, aw=0, twt=360)
    stake(direct_vm, c, direct_bob)
    direct_vm.warp("2026-01-01T00:07:00+00:00")  # past audit timeout
    c.claim_unreplicated_or_expired_refund(1)
    assert int(c.get_refundable_balance(direct_bob)) == BOND
    assert int(c.get_refundable_balance(direct_alice)) == 10 * E1


# ---------------------------------------------------------- refund channel

def test_withdraw_refund_success(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, E1 // 2)
    direct_vm.sender = direct_alice
    c.withdraw_refund(u256_value(E1 // 2))
    assert int(c.get_refundable_balance(direct_alice)) == 0
    assert c.get_custody_accounting_summary()["external_payouts_atto"] == str(E1 // 2)


def u256_value(x):
    # u256 is an int subclass in the SDK; plain int passes through calldata
    return x


def test_withdraw_refund_over_credit_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("exceeds credit"):
        c.withdraw_refund(1)


def test_withdraw_refund_zero_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, E1 // 2)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("refund amount exceeds credit"):
        c.withdraw_refund(0)


def test_claim_refundable_balance(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, E1 // 2)
    direct_vm.sender = direct_alice
    c.claim_refundable_balance()
    assert int(c.get_refundable_balance(direct_alice)) == 0
    assert c.get_last_payable_rejection(direct_alice).startswith("claimed")


def test_claim_refundable_empty_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("nothing to claim"):
        c.claim_refundable_balance()


# ------------------------------------------------------------- rlt vault

def test_rlt_deposit_zero_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("positive"):
        c.deposit_rlt_custody(0)


def test_rlt_received_only_token(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only RLT token"):
        c.on_rlt_received(hexof(direct_bob), E1, 1)


def test_rlt_received_mismatch_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice  # rlt_token_address is alice in deploy args
    c.deposit_rlt_custody(2 * E1)
    with direct_vm.expect_revert("custody credit mismatch"):
        c.on_rlt_received(hexof(direct_alice), E1, 1)


def test_rlt_credit_flow(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    c.deposit_rlt_custody(2 * E1)
    c.on_rlt_received(hexof(direct_alice), 2 * E1, 1)
    assert c.get_custody_accounting_summary()["vault_custody_balance"] == str(2 * E1)
    assert int(c.get_rlt_balance(direct_alice)) == 2 * E1


def test_rlt_credit_rejects_unknown_depositor(
    direct_deploy, direct_vm, direct_alice, direct_bob
):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    c.deposit_rlt_custody(2 * E1)
    with direct_vm.expect_revert("custody credit depositor mismatch"):
        c.on_rlt_received(hexof(direct_bob), 2 * E1, 1)


def test_rlt_withdraw_insufficient_raises(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("insufficient RLT custody"):
        c.withdraw_rlt_custody(E1)


def test_rlt_withdraw_reduces_vault(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    c.deposit_rlt_custody(3 * E1)
    c.on_rlt_received(hexof(direct_alice), 3 * E1, 1)
    c.withdraw_rlt_custody(E1)
    assert int(c.get_rlt_balance(direct_alice)) == 2 * E1
    assert c.get_custody_accounting_summary()["vault_custody_balance"] == str(2 * E1)


# --------------------------------------------------------------- read side

def test_study_card_not_found(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    assert c.get_study_card(42)["status"] == "NOT_FOUND"


def test_trial_book_lists_labs(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    book = c.get_trial_book(1)
    assert len(book) == 1
    assert book[0]["data_checksum_sha256"] == NOTE


def test_reproducibility_index_pagination(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, endowment=5 * E1)
    register(direct_vm, c, direct_alice, endowment=5 * E1)
    register(direct_vm, c, direct_alice, endowment=5 * E1)
    page = c.get_reproducibility_index(0, 2)
    assert len(page) == 2
    page2 = c.get_reproducibility_index(2, 25)
    assert len(page2) == 1


def test_custody_summary_reservation_math(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    summary = c.get_custody_accounting_summary()
    assert summary["total_endowment_locked"] == str(10 * E1)
    # 150 percent of 10 plus the 0.5 bond
    assert summary["reserve_required_atto"] == str(15 * E1 + BOND)
    assert summary["pool_covers_reserve"] in (True, "true")


def test_sanitization_strips_angle_brackets(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    direct_vm.sender = direct_alice
    direct_vm.value = 10 * E1
    c.register_study_bounty_payable(
        "<script>alert(1)</script> Study", ARTIFACT_URL, "target",
        5000, 10 * E1, 300, 60, 600)
    card = c.get_study_card(1)
    assert "<" not in card["title"]
    assert ">" not in card["title"]


def test_second_lab_bond_tracked_separately(direct_deploy, direct_vm, direct_alice, direct_bob, direct_charlie):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice)
    stake(direct_vm, c, direct_bob)
    stake(direct_vm, c, direct_charlie)
    card = c.get_study_card(1)
    assert card["claims"] == "2"
    assert card["first_claim_bond_atto"] == str(BOND)
    assert len(c.get_trial_book(1)) == 2


def test_address_key_is_case_insensitive(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c, E1 // 2)
    upper = hexof(direct_alice).upper().replace("0X", "0x")
    assert int(c.get_refundable_balance(upper)) == E1 // 2


def test_card_deadlines_follow_warp(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    fund(direct_vm, direct_alice, c)
    register(direct_vm, c, direct_alice, tw=300, aw=60, twt=600)
    card = c.get_study_card(1)
    base = T0_EPOCH
    assert card["trial_close_epoch"] == str(base + 300)
    assert card["author_response_deadline_epoch"] == str(base + 360)
    assert card["audit_timeout_epoch"] == str(base + 600)


def test_settle_returns_challenge_bond_to_replicator(direct_deploy, direct_vm, direct_alice, direct_bob, direct_charlie):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    direct_vm.sender = direct_charlie
    direct_vm.value = CHALLENGE_BOND
    c.challenge_replication_ruling_payable(1, "doubts")
    direct_vm.value = 0
    direct_vm.warp("2026-01-01T00:12:00+00:00")
    c.evaluate_replication_trial(1)
    direct_vm.warp("2026-01-01T00:15:00+00:00")
    c.settle_replication_grant(1)
    # exact band: replicator receives bounty plus its own and the challenger bond
    assert int(c.get_refundable_balance(direct_bob)) == 10 * E1 + BOND + CHALLENGE_BOND


def test_deposit_twice_reverts_when_pending(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    c.deposit_rlt_custody(E1)
    with direct_vm.expect_revert("pending deposit in flight"):
        c.deposit_rlt_custody(E1)


def test_on_rlt_received_wrong_ref_reverts(direct_deploy, direct_vm, direct_alice):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    c.deposit_rlt_custody(E1)
    with direct_vm.expect_revert("custody credit mismatch"):
        c.on_rlt_received(hexof(direct_alice), E1, 7)


def test_fraud_slash_target_is_the_pi(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = deploy(direct_deploy, direct_vm, direct_alice)
    mock_pages(direct_vm)
    mock_audit(direct_vm, 5000, fabrication=True)
    funded_registered(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    c.submit_author_response(1, "ok")
    direct_vm.warp("2026-01-01T00:06:00+00:00")
    c.evaluate_replication_trial(1)
    card = c.get_study_card(1)
    assert card["slash_target"] == hexof(direct_alice).lower()
