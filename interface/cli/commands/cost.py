"""Cost subcommands — summary, budget."""

from __future__ import annotations

import typer

from interface.cli.formatters import console, print_cost_summary, print_error
from interface.cli.main import _get_container, _run

cost_app = typer.Typer()


@cost_app.command("summary")
def summary() -> None:
    """Show cost summary (daily, monthly, local rate, budget)."""
    c = _get_container()
    daily = _run(c.cost_repo.get_daily_total())
    monthly = _run(c.cost_repo.get_monthly_total())
    local_rate = _run(c.cost_repo.get_local_usage_rate())
    budget = c.settings.default_monthly_budget_usd
    remaining = max(budget - monthly, 0.0)
    print_cost_summary(
        daily_usd=daily,
        monthly_usd=monthly,
        local_rate=local_rate,
        budget_usd=budget,
        remaining_usd=remaining,
    )


@cost_app.command("budget")
def budget_set(
    amount: float = typer.Argument(..., help="New monthly budget in USD."),
) -> None:
    """Set the monthly budget (in-memory, resets on restart)."""
    c = _get_container()
    if amount < 0:
        print_error("Budget must be non-negative")
        raise typer.Exit(code=1)
    c.settings.default_monthly_budget_usd = amount
    console.print(f"[green]Budget set:[/] ${amount:.2f}/month")
