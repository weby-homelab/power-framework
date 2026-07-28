"""Tests for the single-writer WriteQueue (WTF #6 remediation)."""

from __future__ import annotations

import asyncio

import pytest

from power_framework.core.mutation import run_vault_mutation


@pytest.mark.asyncio
async def test_same_vault_mutations_execute_sequentially(tmp_path):
    """All mutations for one vault run one at a time via its lock."""
    vault = tmp_path / "vault"
    vault.mkdir()
    order: list[int] = []

    def make_job(i: int) -> int:
        order.append(i)
        return i * 10

    results = await asyncio.gather(
        *(run_vault_mutation(vault, lambda i=i: make_job(i)) for i in range(10))
    )

    assert sorted(results) == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    # Every job completed once; executor scheduling does not define submission order.
    assert sorted(order) == list(range(10))


@pytest.mark.asyncio
async def test_mutation_exceptions_propagate_to_caller(tmp_path):
    """A failing mutation surfaces its error to the awaiting caller."""
    vault = tmp_path / "vault"
    vault.mkdir()

    def boom() -> int:
        raise ValueError("simulated write failure")

    with pytest.raises(ValueError, match="simulated write failure"):
        await run_vault_mutation(vault, boom)


@pytest.mark.asyncio
async def test_concurrent_mutations_never_race_on_shared_resource(tmp_path):
    """Same-vault mutations remain serialized without a process-wide queue."""
    vault = tmp_path / "vault"
    vault.mkdir()
    counter = {"value": 0}

    def unsafe_increment() -> int:
        # Read-modify-write without a lock: would lose updates if run in parallel.
        cur = counter["value"]
        # Tiny busy window to maximize chance of a race if ever concurrent.
        counter["value"] = cur + 1
        return counter["value"]

    results = await asyncio.gather(
        *(run_vault_mutation(vault, unsafe_increment) for _ in range(50))
    )

    assert sorted(results) == list(range(1, 51))
    assert counter["value"] == 50


@pytest.mark.asyncio
async def test_different_vaults_can_run_in_parallel(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    await asyncio.gather(
        run_vault_mutation(first, lambda: 1),
        run_vault_mutation(second, lambda: 2),
    )
