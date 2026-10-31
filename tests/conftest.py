"""Shared pytest configuration for direct-mode tests.

Two shims make the in-memory direct runner behave like the GenVM validator:

1. Windows: the gltest direct loader tries to unlink the injected stdin temp
   file while fd 0 still references it, raising PermissionError. Deferring the
   unlink lets the same tests run on every platform.
2. Clock: the harness refreshes gl.message_raw for sender and value but not for
   datetime, while it patches datetime.datetime.now() instead. Contracts must
   read gl.message_raw["datetime"] and nothing else, so this shim mirrors the
   warped vm._datetime into that same dict field. It changes no contract code.
"""

import sys

import gltest.direct.loader as _loader

_orig_inject = _loader._inject_message_to_fd0

if sys.platform == "win32":

    def _inject_message_to_fd0(vm):
        import os
        import tempfile

        try:
            from genlayer.py import calldata
            from genlayer.py.types import Address
        except ImportError:
            _orig_inject(vm)
            return

        sender_addr = vm.sender
        if isinstance(sender_addr, bytes):
            sender_addr = Address(sender_addr)
        contract_addr = vm._contract_address
        if isinstance(contract_addr, bytes):
            contract_addr = Address(contract_addr)
        origin_addr = vm.origin
        if isinstance(origin_addr, bytes):
            origin_addr = Address(origin_addr)
        message_data = {
            "contract_address": contract_addr,
            "sender_address": sender_addr,
            "origin_address": origin_addr,
            "stack": [],
            "value": vm._value,
            "datetime": vm._datetime,
            "is_init": False,
            "chain_id": vm._chain_id,
            "entry_kind": 0,
            "entry_data": b"",
            "entry_stage_data": None,
        }
        encoded = calldata.encode(message_data)
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, encoded)
            os.lseek(fd, 0, os.SEEK_SET)
            original_stdin = os.dup(0)
            vm._original_stdin_fd = original_stdin
            os.dup2(fd, 0)
        finally:
            os.close(fd)
        # Windows: leave path for the OS to clean; unlink here always fails.

    _loader._inject_message_to_fd0 = _inject_message_to_fd0


def pytest_configure(config):
    """Mirror the warped timestamp into gl.message_raw["datetime"]."""
    from gltest.direct.vm import VMContext

    orig_refresh = VMContext._refresh_gl_message

    def _refresh(self):
        orig_refresh(self)
        if "genlayer.gl" not in sys.modules:
            return
        try:
            gl = sys.modules["genlayer.gl"]
            if getattr(gl, "message_raw", None) is not None:
                gl.message_raw["datetime"] = self._datetime
        except Exception:
            pass

    VMContext._refresh_gl_message = _refresh
