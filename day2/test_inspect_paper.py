import unittest
from collections import namedtuple

from day2.inspect_paper import inspect_paper


AccountValue = namedtuple("AccountValue", "account tag value currency modelCode")


class Gateway:
    def __init__(self, accounts):
        self.client = self
        self.wrapper = self
        self.accounts = accounts
        self.connected = False

    async def connectAsync(self, host, port, clientId, timeout):
        self.endpoint = (host, port, clientId)
        self.connected = True

    def getAccounts(self):
        return self.accounts

    def getReqId(self):
        return 17

    def isConnected(self):
        return self.connected

    def disconnect(self):
        self.connected = False


class ReadableGateway(Gateway):
    async def accountSummaryAsync(self, account):
        return [
            AccountValue(account, "NetLiquidation", "1000000", "USD", ""),
            AccountValue(account, "TotalCashValue", "999900", "USD", ""),
            AccountValue(account, "BuyingPower", "2000000", "USD", ""),
        ]

    async def reqPositionsAsync(self):
        return []

    async def reqAllOpenOrdersAsync(self):
        return []

    async def reqCompletedOrdersAsync(self, apiOnly):
        return []

    async def reqExecutionsAsync(self):
        return []


class PaperInspectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_live_ports_are_rejected_before_connecting(self):
        for port in (4001, 7496):
            with self.subTest(port=port), self.assertRaises(ValueError):
                await inspect_paper(port, "DU10000", 123456, None)

    async def test_live_account_configuration_is_rejected_before_connecting(self):
        with self.assertRaises(ValueError):
            await inspect_paper(4102, "U10000", 123456, None)

    async def test_wrong_or_mixed_accounts_stop_before_reading_broker_state(self):
        for accounts in ([], ["U10000"], ["DU20000"], ["DU10000", "U10000"]):
            with self.subTest(accounts=accounts):
                gateway = Gateway(accounts)
                with self.assertRaises(PermissionError):
                    await inspect_paper(4102, "DU10000", 123456, lambda: gateway)
                self.assertFalse(gateway.connected)

    async def test_exact_paper_account_produces_read_only_snapshot(self):
        gateway = ReadableGateway(["DU10000"])
        result = await inspect_paper(4102, "DU10000", 123456, lambda: gateway)
        self.assertEqual(gateway.endpoint, ("127.0.0.1", 4102, 123456))
        self.assertEqual(result["next_valid_id"], 17)
        self.assertEqual(result["balances"]["TotalCashValue"], {"value": "999900", "currency": "USD"})
        self.assertEqual(result["open_orders"], 0)
        self.assertEqual(result["positions"], 0)
        self.assertEqual(result["executions"], 0)
        self.assertNotIn("DU10000", str(result))
        self.assertFalse(gateway.connected)

    async def test_timed_out_snapshot_does_not_report_empty_broker_state(self):
        class TimedOutGateway(ReadableGateway):
            async def reqAllOpenOrdersAsync(self):
                raise TimeoutError("open orders timed out")

        gateway = TimedOutGateway(["DU10000"])
        with self.assertRaises(TimeoutError):
            await inspect_paper(4102, "DU10000", 123456, lambda: gateway)
        self.assertFalse(gateway.connected)
