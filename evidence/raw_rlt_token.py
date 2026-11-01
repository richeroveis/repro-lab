# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import re

# RLT: the endowment settlement token used by ReproLab. Tokens held by the
# ledger are genuinely transferred into the ledger address (real custody), and
# every deposit is settled back into the ledger through an emit callback so the
# ledger can never invent a custody credit for itself.

ERROR_EXPECTED = "[EXPECTED]"
_MINT_SUPPLY = 1000000 * 10 ** 18
_HEXA = re.compile(r"^0x[0-9a-fA-F]{40}$")


class CreditEvent(gl.Event):
    def __init__(self, owner: str, spender: str, /, **blob): ...


def _addr(a) -> str:
    if isinstance(a, (bytes, bytearray)):
        return "0x" + a.hex()
    return str(a).lower()


def _require_addr(value: str, label: str) -> str:
    text = str(value).strip()
    if not _HEXA.match(text):
        raise gl.vm.UserError(ERROR_EXPECTED + " bad address " + label)
    return text.lower()


class RLTToken(gl.Contract):
    """Fixed-supply RLT endowment token with a ledger deposit callback."""

    total_supply: u256
    balances: TreeMap[str, u256]
    allowances: TreeMap[str, u256]

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

        Only the ledger itself may invoke this (it is the spender), and the
        depositor is debited solely through the allowance that depositor
        granted to that ledger, so no caller can move a third party's tokens.
        Internal messages carry the emitting contract as origin, which is why
        the depositor is an explicit argument instead of `gl.message.origin`.
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
        CreditEvent(owner, spender, amount=str(amount), ref=str(int(ref))).emit()
        gl.get_contract_at(Address(spender)).emit().on_rlt_received(
            owner, amount_atto, ref)
        return True
