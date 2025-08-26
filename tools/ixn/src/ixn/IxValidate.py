import time


class IxValidate:
    def __init__(self, ix_network):
        self._ix_network = ix_network

    def validate_802_1CB_4(self):
        for i in range(10):
            statsView = self._ix_network.Statistics.View.find(Caption="Flow Statistics")
            RxRates = statsView.GetColumnValues(Arg2="Rx Rate (Kbps)")
            print(RxRates)
            time.sleep(1)

        # TODO: Invoke script to test the scenario
        statsView = self._ix_network.Statistics.View.find(Caption="Flow Statistics")
        # print(statsView)

        # For this scenario, success/failure is based on the receive bit rate of each traffic
        # item to see that the proper flow meters are applied by the switch.
        RxRates = statsView.GetColumnValues(Arg2="Rx Rate (Kbps)")
        # print("RxRates: ", RxRates)

        streamName = ["1", "2", "3", "4", "5", "6", "N/A (unmetered)"]
        streamTrafficMembers = [
            [5],
            [0, 1, 2, 3],
            [],
            [6, 7],
            [4],
            [8, 9],
            [10],
        ]
        streamExpectedRxRate = [
            1000.0,
            2000.0,
            3000.0,
            4000.0,
            5000.0,
            0.0,
            20000.0,
        ]
        streamRateUnits = [
            "Kbps",
            "Kbps",
            "Kbps",
            "Kbps",
            "Kbps",
            "Kbps",
            "Kbps",
        ]

        # A tolerance needs to be applied as the values won't be exact based on how the flow meter is applied.
        # Currently, there seems to be some source of error we have not figured out, so the tolerance
        # needs to be a bit higher than ideal.  For example, a flow restricted to 5000 Kbps we might see 5020 Kbps.
        # The error seems to be more a constant than a ratio of the traffic, so a flow restricted to 100 Kbps might see 120 Kbps.
        # For now, using a constant tolerance of 1% but that might not work for scenarios using lower flow meter rates.

        longestName = len(max(streamName, key=len))

        for i in range(len(streamName)):
            rate = 0.0
            expectedRxRate = float(streamExpectedRxRate[i])
            tolerance = expectedRxRate * 0.01

            # Pad with spaces so all names are same length to make output look nice
            name = streamName[i].ljust(longestName)
            if len(streamTrafficMembers[i]) == 0:
                emptyStream = True
            else:
                emptyStream = False
                for j in range(len(streamTrafficMembers[i])):
                    rate += float(RxRates[streamTrafficMembers[i][j]])
            testResult = abs(rate - expectedRxRate) <= tolerance
            if emptyStream:
                print(
                    "N/A : Stream",
                    name,
                    "- scenario does not match any traffic items to this stream",
                )
            else:
                if testResult:
                    print("PASS: ", end="")
                else:
                    print("FAIL: ", end="")
                print(
                    "Stream",
                    name,
                    "- expected rate:",
                    expectedRxRate,
                    streamRateUnits[i],
                    "actual rate:",
                    rate,
                    streamRateUnits[i],
                )
