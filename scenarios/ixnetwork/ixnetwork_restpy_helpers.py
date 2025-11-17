import logging
import time

import pytest


logger = logging.getLogger(__name__)


class StatsViewSnapshot:
    """
    Takes a snapshot of an Ixnetwork.Statistics.View and provides an ergonomic
    list of dictionaries for querying the stats within.  Each list entry
    represents a row and each row is a dictionary indexed by column name.

    Example:
    >>> ports = StatsViewSnapshot(ixn, "Port Statistics")
    >>> assert ports[0]["Frames Tx."] == 10
    """

    def __init__(self, ixn, view_caption: str):
        self._view = ixn.Statistics.View.find(Caption=f"^{view_caption}$")
        self._snapshot = self._snapshot()

    def _snapshot(self):
        cols = self._view.Data.ColumnCaptions
        rows = self._view.Data.RowValues.values()
        rows = [row[0] for row in rows]

        return self._list_of_lists_to_list_of_dicts(rows, cols)

    def _list_of_lists_to_list_of_dicts(
        self, list_of_lists: list[list[str]], column_captions: list[str]
    ) -> list[dict[str, str | int]]:
        list_of_dicts = []
        for row in list_of_lists:
            row_dict = {}
            for i, cell in enumerate(row):
                key = column_captions[i]
                try:
                    row_dict[key] = int(cell)
                except Exception:
                    row_dict[key] = cell
            list_of_dicts.append(row_dict)
        return list_of_dicts

    def __getitem__(self, i: int) -> dict[str, str | int]:
        return self._snapshot[i]


class AssertStats:
    def __init__(self, ixn, view_caption: str, timeout: int = 60):
        self._caption = view_caption
        self._entity = self._caption.split()[0]
        self._view = ixn.Statistics.View.find(Caption=f"^{view_caption}$")

        logger.info(f"Waiting for {self._caption}")
        for _ in range(timeout):
            is_ready = self._view.Data.IsReady
            if is_ready:
                break
            time.sleep(1)

        if not is_ready:
            raise RuntimeError(f"{self._caption} not ready after {timeout} seconds")

    def assert_equal_eventually(
        self, index: int, stat: str, value: str | int, timeout: int = 10
    ):
        expected = value

        for _ in range(timeout):
            values = self._view.GetColumnValues(stat)
            actual = self._cast_as(values[index], value)
            if actual == expected:
                break
            time.sleep(1)

        logger.info(
            f"Assert {self._entity} {index} {stat} equals {expected} (actual={actual})"
        )
        assert actual == expected

    def assert_approx_eventually(
        self,
        index: int,
        stat: str,
        value: int,
        tolerance: float = 1e-3,
        timeout: int = 10,
    ):
        expected = pytest.approx(float(value), rel=tolerance)

        for _ in range(timeout):
            values = self._view.GetColumnValues(stat)
            actual = self._cast_as(values[index], value)
            if actual == expected:
                break
            time.sleep(1)

        logger.info(
            f"AssertStats('{self._caption}').assert_approx_eventually(index={index} stat='{stat}' actual={actual} expected={expected})"
        )
        assert actual == expected

    def _cast_as(self, value, reference):
        match reference:
            case int():
                return int(float(value))
            case float():
                return float(value)
            case _:
                raise RuntimeError()


class RunTraffic:
    def __init__(self, ixn):
        self.ixn = ixn

    def __enter__(self):
        logger.info("Starting traffic")

        # Generate and apply
        self.ixn.Traffic.TrafficItem.find().Generate()
        self.ixn.Traffic.Apply()
        self.ixn.ClearStats()

        # Start traffic
        self.ixn.Globals.Testworkflow.Start(False)
        _wait_for_testworkflow_operation_complete(self.ixn)
        logger.info("Started traffic")

    def __exit__(self, type, value, traceback):
        logger.info("Stopping traffic")

        # Stop traffic
        self.ixn.Globals.Testworkflow.Stop()
        _wait_for_testworkflow_operation_complete(self.ixn)


def _wait_for_testworkflow_operation_complete(ixn, timeout: int = 30):
    """
    If initial state is idle, wait for another.
    If current status is idle, and previous state is not idle, then break.
    """

    previous_state = None

    for _ in range(timeout):
        current_state = ixn.Globals.Testworkflow.CurrentState
        match (previous_state, current_state):
            case (None, "kIdle"):
                pass
            case (_, "kIdle"):
                break
            case _:
                pass

        previous_state = current_state
        time.sleep(1)

    if current_state != "kIdle":
        raise RuntimeError(
            f"State not idle after {timeout} seconds.  State is {current_state}."
        )


def run_traffic_blocking(ixn, timeout_secs: int = 10):
    """
    Runs traffic until completion (e.g., fixed frame count transmitted) or
    until timeout.
    """
    logger.info("Starting traffic")

    # Generate and apply
    ixn.Traffic.TrafficItem.find().Generate()
    ixn.Traffic.Apply()
    ixn.ClearStats()

    # Start traffic
    ixn.Globals.Testworkflow.Starttraffic()
    ixn.Traffic.StartApplicationTraffic()

    # Wait until auto stopped or timeout
    traffic = ixn.Traffic.find()
    for _ in range(10):
        if traffic.State == "stopped":
            break
        time.sleep(1)

    logger.info("Stopping traffic")
