# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from dataclasses import dataclass
import re

# RLT: the endowment settlement token used by ReproLab. Tokens held by the
# ledger are genuinely transferred into the ledger address (real custody), and
# every deposit is settled back into the ledger through an emit callback so the
# ledger can never invent a custody credit for itself.

ERROR_EXPECTED = "[EXPECTED]"
_MINT_SUPPLY = 1000000 * 10 ** 18
_HEXA = re.compile(r"^0x[0-9a-fA-F]{40}$")

STATUS_PENDING = "PENDING"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_RECOVERED = "RECOVERED"


class CreditEvent(gl.Event):
    def __init__(self, owner: str, spender: str, /, **blob): ...


@allow_storage
@dataclass
class DepositReceipt:
    deposit_id: u256
    depositor: str
    ledger: str
    study_id: u256
    amount: u256
    status: str
    created_at_epoch: u256


def _addr(a) -> str:
    if isinstance(a, (bytes, bytearray)):
        return "0x" + a.hex()
    return str(a).lower()


def _require_addr(value: str, label: str) -> str:
    text = str(value).strip()
    if not _HEXA.match(text):
        raise gl.vm.UserError(ERROR_EXPECTED + " bad address " + label)
    return text.lower()


def _now_epoch() -> int:
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
    yy = y - 1 if mo <= 2 else y
    era = yy // 400
    yoe = yy - era * 400
    mp = mo - 3 if mo > 2 else mo + 9
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468
    return days * 86400 + int(time_bits[0]) * 3600 + int(time_bits[1]) * 60 + int(time_bits[2])


class RLTToken(gl.Contract):
    """Fixed-supply RLT endowment token with bounded recovery for ledger deposits."""

    total_supply: u256
    balances: TreeMap[str, u256]
    allowances: TreeMap[str, u256]
    pending_deposits: TreeMap[u256, DepositReceipt]

    def __init__(self):
        creator = _addr(gl.message.sender_address)
        self.total_supply = u256(_MINT_SUPPLY)
        self.balances[creator] = u256(_MINT_SUPPLY)

    @gl.public.view
    def balanceOf(self, owner: str) -> u256:
        return self.balances.get(_addr(owner), u256(0))

    @gl.public.view
    def allowanceOf(self, owner: str, spender: str) -> u256:
        return self.allowances.get(_addr(owner) + "|" + _addr(spender), u256(0))

    @gl.public.write
    def approve(self, spender: str, value: u256) -> None:
        owner = _addr(gl.message.sender_address)
        if int(value) < 0:
            raise gl.vm.UserError(ERROR_EXPECTED + " negative allowance")
        self.allowances[owner + "|" + _require_addr(spender, "spender")] = value

    @gl.public.write
    def transfer(self, to: str, value: u256) -> bool:
        sender = _addr(gl.message.sender_address)
        target = _require_addr(to, "target")
        from_balance = int(self.balances.get(sender, u256(0)))
        if int(value) <= 0 or from_balance < int(value):
            raise gl.vm.UserError(ERROR_EXPECTED + " insufficient RLT balance")
        self.balances[sender] = u256(from_balance - int(value))
        self.balances[target] = self.balances.get(target, u256(0)) + value
        return True

    @gl.public.write
    def deposit_into_ledger(
        self, ledger: str, depositor: str, amount_atto: u256, ref: u256
    ) -> bool:
        """Pull `depositor` RLT into `ledger` and notify the ledger.

        Tracks a pending deposit receipt with a deterministic bounded recovery path.
        """
        spender = _require_addr(ledger, "ledger")
        owner = _require_addr(depositor, "depositor")
        if _addr(gl.message.sender_address) != spender:
            raise gl.vm.UserError(ERROR_EXPECTED + " only ledger may deposit")
        amount = int(amount_atto)
        if amount <= 0:
            raise gl.vm.UserError(ERROR_EXPECTED + " deposit must be positive")
        key = owner + "|" + spender
        allowed = int(self.allowances.get(key, u256(0)))
        if allowed < amount:
            raise gl.vm.UserError(ERROR_EXPECTED + " allowance too small")
        held = int(self.balances.get(owner, u256(0)))
        if held < amount:
            raise gl.vm.UserError(ERROR_EXPECTED + " insufficient RLT balance")
        self.allowances[key] = u256(allowed - amount)
        self.balances[owner] = u256(held - amount)
        self.balances[spender] = self.balances.get(spender, u256(0)) + amount_atto

        now = u256(_now_epoch())
        self.pending_deposits[ref] = DepositReceipt(
            deposit_id=ref,
            depositor=owner,
            ledger=spender,
            study_id=u256(0),
            amount=amount_atto,
            status=STATUS_PENDING,
            created_at_epoch=now,
        )

        CreditEvent(owner, spender, amount=str(amount), ref=str(int(ref))).emit()
        gl.get_contract_at(Address(spender)).emit().on_rlt_received(
            owner, amount_atto, ref)
        return True

    @gl.public.write
    def confirm_deposit(self, deposit_id: u256) -> bool:
        """Confirm receipt when ledger callback succeeds."""
        receipt = self.pending_deposits.get(deposit_id)
        if receipt is None:
            raise gl.vm.UserError(ERROR_EXPECTED + " unknown deposit")
        if _addr(gl.message.sender_address) != receipt.ledger:
            raise gl.vm.UserError(ERROR_EXPECTED + " only ledger may confirm")
        if receipt.status != STATUS_PENDING:
            raise gl.vm.UserError(ERROR_EXPECTED + " deposit not pending")
        self.pending_deposits[deposit_id] = DepositReceipt(
            deposit_id=receipt.deposit_id,
            depositor=receipt.depositor,
            ledger=receipt.ledger,
            study_id=receipt.study_id,
            amount=receipt.amount,
            status=STATUS_CONFIRMED,
            created_at_epoch=receipt.created_at_epoch,
        )
        return True

    @gl.public.write
    def recover_failed_deposit(self, deposit_id: u256) -> bool:
        """Bounded recovery path for stranded RLT when ledger callback fails.

        Callable by the original depositor. Marks the receipt RECOVERED, and
        refunds 100% of the stranded RLT tokens back to depositor's balance.
        """
        sender = _addr(gl.message.sender_address)
        receipt = self.pending_deposits.get(deposit_id)
        if receipt is None:
            raise gl.vm.UserError(ERROR_EXPECTED + " unknown deposit")
        if sender != receipt.depositor:
            raise gl.vm.UserError(ERROR_EXPECTED + " only depositor may recover")
        if receipt.status != STATUS_PENDING:
            raise gl.vm.UserError(ERROR_EXPECTED + " deposit not pending")

        self.pending_deposits[deposit_id] = DepositReceipt(
            deposit_id=receipt.deposit_id,
            depositor=receipt.depositor,
            ledger=receipt.ledger,
            study_id=receipt.study_id,
            amount=receipt.amount,
            status=STATUS_RECOVERED,
            created_at_epoch=receipt.created_at_epoch,
        )

        amount_to_refund = int(receipt.amount)
        ledger_bal = int(self.balances.get(receipt.ledger, u256(0)))
        if ledger_bal < amount_to_refund:
            raise gl.vm.UserError(ERROR_EXPECTED + " ledger balance too low for recovery")
        self.balances[receipt.ledger] = u256(ledger_bal - amount_to_refund)
        self.balances[receipt.depositor] = self.balances.get(receipt.depositor, u256(0)) + receipt.amount
        return True

    @gl.public.view
    def get_deposit_receipt(self, deposit_id: u256) -> dict:
        receipt = self.pending_deposits.get(deposit_id)
        if receipt is None:
            return {"status": "NOT_FOUND"}
        return {
            "deposit_id": str(int(receipt.deposit_id)),
            "depositor": str(receipt.depositor),
            "ledger": str(receipt.ledger),
            "study_id": str(int(receipt.study_id)),
            "amount": str(int(receipt.amount)),
            "status": str(receipt.status),
            "created_at_epoch": str(int(receipt.created_at_epoch)),
        }
