import logging
import time


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


def run_traffic_blocking(ixn, timeout_secs: int = 10):
    """
    Runs traffic until completion (e.g., fixed frame count transmitted) or
    until timeout.
    """
    logger.info("Starting traffic")
    ixn.Globals.Testworkflow.Starttraffic()
    ixn.Traffic.StartApplicationTraffic()
    traffic = ixn.Traffic.find()
    for _ in range(10):
        if traffic.State == "stopped":
            break
        time.sleep(1)
    logger.info("Stopping traffic")
