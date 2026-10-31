"""Direct tests for the RLT endowment token that backs ReproLab custody."""

TOKEN = "contracts/rlt_token.py"
E1 = 10 ** 18
SUPPLY = 1000000 * E1


def hexof(addr):
    raw = getattr(addr, "as_bytes", None)
    return "0x" + bytes(raw if raw is not None else addr).hex()


def deploy_token(direct_deploy, direct_vm, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00+00:00")
    direct_vm.sender = direct_alice
    direct_vm.origin = direct_alice
    return direct_deploy(TOKEN)


def test_supply_minted_to_creator(direct_deploy, direct_vm, direct_alice):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    assert int(t.balanceOf(direct_alice)) == SUPPLY
    assert int(t.total_supply) == SUPPLY


def test_transfer_moves_balance(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    t.transfer(hexof(direct_bob), 5 * E1)
    assert int(t.balanceOf(direct_bob)) == 5 * E1
    assert int(t.balanceOf(direct_alice)) == SUPPLY - 5 * E1


def test_transfer_zero_reverts(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("insufficient RLT balance"):
        t.transfer(hexof(direct_bob), 0)


def test_transfer_over_balance_reverts(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("insufficient RLT balance"):
        t.transfer(hexof(direct_bob), SUPPLY + 1)


def test_transfer_bad_address_reverts(direct_deploy, direct_vm, direct_alice):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("bad address"):
        t.transfer("not-an-address", E1)


def test_allowance_starts_zero(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    assert int(t.allowanceOf(direct_alice, direct_bob)) == 0


def test_approve_records_allowance(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    t.approve(hexof(direct_bob), 7 * E1)
    assert int(t.allowanceOf(direct_alice, direct_bob)) == 7 * E1


def test_approve_negative_reverts(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("negative allowance"):
        t.approve(hexof(direct_bob), -1)


def deposit(t, direct_vm, direct_alice, direct_bob, amount, ref=1, ledger=None):
    """Call the ledger-only deposit path as the pinned ledger would."""
    direct_vm.sender = ledger or direct_bob
    return t.deposit_into_ledger(hexof(direct_bob), hexof(direct_alice), amount, ref)


def test_deposit_requires_allowance(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("allowance too small"):
        deposit(t, direct_vm, direct_alice, direct_bob, E1)


def test_deposit_only_ledger_may_call(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    t.approve(hexof(direct_bob), E1)
    with direct_vm.expect_revert("only ledger may deposit"):
        t.deposit_into_ledger(hexof(direct_bob), hexof(direct_alice), E1, 1)


def test_deposit_positive_amount_only(direct_deploy, direct_vm, direct_alice, direct_bob):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    t.approve(hexof(direct_bob), E1)
    with direct_vm.expect_revert("deposit must be positive"):
        deposit(t, direct_vm, direct_alice, direct_bob, 0)


def test_deposit_credits_ledger_and_spend_allowance(
    direct_deploy, direct_vm, direct_alice, direct_bob
):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    t.approve(hexof(direct_bob), 4 * E1)
    assert deposit(t, direct_vm, direct_alice, direct_bob, 3 * E1, 2) in (True, 1)
    assert int(t.balanceOf(direct_bob)) == 3 * E1
    assert int(t.balanceOf(direct_alice)) == SUPPLY - 3 * E1
    assert int(t.allowanceOf(direct_alice, direct_bob)) == E1


def test_deposit_exceeding_balance_reverts(
    direct_deploy, direct_vm, direct_alice, direct_bob
):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    t.approve(hexof(direct_bob), SUPPLY * 2)
    with direct_vm.expect_revert("insufficient RLT balance"):
        deposit(t, direct_vm, direct_alice, direct_bob, SUPPLY + E1)


def test_deposit_rejects_bad_ledger_address(direct_deploy, direct_vm, direct_alice):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("bad address"):
        t.deposit_into_ledger("0xnope", hexof(direct_alice), E1, 1)


def test_deposit_rejects_bad_depositor_address(
    direct_deploy, direct_vm, direct_alice, direct_bob
):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("bad address"):
        direct_vm.sender = direct_bob
        t.deposit_into_ledger(hexof(direct_bob), "not-an-address", E1, 1)


def test_balance_of_unknown_account_is_zero(direct_deploy, direct_vm, direct_alice):
    t = deploy_token(direct_deploy, direct_vm, direct_alice)
    assert int(t.balanceOf("0x" + "1" * 40)) == 0
