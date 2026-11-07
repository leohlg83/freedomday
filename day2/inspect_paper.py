"""Read one snapshot from the visually confirmed Day2 PAPER Gateway."""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


async def inspect_paper(port, expected_account, client_id, make_gateway):
    if not 1 <= port <= 65535 or port in {4001, 7496}:
        raise ValueError("Use the visually confirmed PAPER port. LIVE ports are forbidden.")
    if not re.fullmatch(r"DU[0-9]+", expected_account):
        raise ValueError("Set DAY2_PAPER_ACCOUNT to the verified Day2 PAPER account locally.")
    if not 0 < client_id <= 2**31 - 1:
        raise ValueError("Use a positive client ID reserved for Day2.")

    gateway = make_gateway()
    gateway.wrapper.clientId = client_id
    gateway.RaiseRequestErrors = True
    try:
        async with asyncio.timeout(20):
            # Connect at the protocol level to avoid automatic account sync
            # and order binding before checking the account identity.
            await gateway.client.connectAsync("127.0.0.1", port, clientId=client_id, timeout=5)
            if gateway.client.getAccounts() != [expected_account]:
                raise PermissionError("Gateway did not report exactly the expected Day2 PAPER account.")

            next_valid_id = gateway.client.getReqId()
            summary = await gateway.accountSummaryAsync(expected_account)
            positions = await gateway.reqPositionsAsync()
            open_orders = await gateway.reqAllOpenOrdersAsync()
            completed_orders = await gateway.reqCompletedOrdersAsync(apiOnly=False)
            executions = await gateway.reqExecutionsAsync()
            if not gateway.isConnected() or gateway.client.getAccounts() != [expected_account]:
                raise ConnectionError("PAPER session changed during the inspection.")
            if any(row.account != expected_account for row in positions) or any(
                trade.order.account != expected_account for trade in (*open_orders, *completed_orders)
            ) or any(fill.execution.acctNumber != expected_account for fill in executions):
                raise PermissionError("Broker snapshot contains activity outside the verified account.")

            balances = {}
            for tag in ("NetLiquidation", "TotalCashValue", "BuyingPower"):
                matches = [row for row in summary if row.account == expected_account and row.tag == tag]
                if len(matches) != 1 or not matches[0].currency:
                    raise RuntimeError(f"Missing or ambiguous PAPER balance {tag}.")
                row = matches[0]
                try:
                    valid = Decimal(row.value).is_finite()
                except InvalidOperation:
                    valid = False
                if not valid:
                    raise RuntimeError(f"Invalid PAPER balance {tag}.")
                balances[tag] = {"value": row.value, "currency": row.currency}

            return {
                "observed_utc": datetime.now(timezone.utc).isoformat(),
                "account_verified": True,
                "next_valid_id": next_valid_id,
                "balances": balances,
                "positions": len(positions),
                "open_orders": len(open_orders),
                "completed_orders": len(completed_orders),
                "executions": len(executions),
                "market_data": "NOT_PROBED",
                "instrument_permissions": "NOT_PROBED",
            }
    finally:
        gateway.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmed-paper-port", type=int, required=True)
    parser.add_argument("--client-id", type=int, required=True)
    args = parser.parse_args()

    def make_gateway():
        from ib_async import IB

        return IB()

    snapshot = asyncio.run(inspect_paper(
        args.confirmed_paper_port, os.environ.get("DAY2_PAPER_ACCOUNT", ""), args.client_id, make_gateway
    ))
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
