// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title TWAPOracle
/// @notice Time-weighted average price oracle using cumulative price observations
/// @dev Records price snapshots and computes TWAP over a configurable window
contract TWAPOracle {
    struct Observation {
        uint256 timestamp;
        uint256 blockNumber;
        uint256 priceCumulative;
        uint256 spotPrice;
    }

    address public pair;
    address public admin;

    Observation[] public observations;
    uint256 public constant PRECISION = 1e18;
    uint256 public constant MIN_WINDOW_SIZE = 30 minutes;
    uint256 public constant MAX_STALENESS = 2 hours;

    uint256 public windowSize = MIN_WINDOW_SIZE;

    event ObservationRecorded(uint256 timestamp, uint256 blockNumber, uint256 spotPrice, uint256 priceCumulative);
    event WindowUpdated(uint256 newWindow);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(address _pair) {
        admin = msg.sender;
        pair = _pair;
    }

    function recordObservation(uint256 spotPrice) external {
        require(spotPrice > 0, "Zero price");

        uint256 lastCumulative = 0;
        uint256 lastTimestamp = block.timestamp;

        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            require(block.number > last.blockNumber, "Observation already recorded this block");

            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
            lastTimestamp = block.timestamp;
        }

        observations.push(Observation({
            timestamp: lastTimestamp,
            blockNumber: block.number,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        }));

        emit ObservationRecorded(lastTimestamp, block.number, spotPrice, lastCumulative);
    }

    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];
        require(block.timestamp - latest.timestamp <= MAX_STALENESS, "Stale price");

        // Find the oldest observation within the window
        uint256 targetTime = latest.timestamp - windowSize;
        uint256 oldIndex = 0;

        for (uint256 i = observations.length - 1; i > 0; i--) {
            if (observations[i].timestamp <= targetTime) {
                oldIndex = i;
                break;
            }
        }

        Observation storage old = observations[oldIndex];
        uint256 timeElapsed = latest.timestamp - old.timestamp;
        require(timeElapsed >= windowSize, "Insufficient window");

        if (timeElapsed == 0) {
            return latest.spotPrice;
        }

        return (latest.priceCumulative - old.priceCumulative) / timeElapsed;
    }

    function getLatestPrice() external view returns (uint256) {
        require(observations.length > 0, "No observations");
        return observations[observations.length - 1].spotPrice;
    }

    function setWindowSize(uint256 _windowSize) external onlyAdmin {
        require(_windowSize >= MIN_WINDOW_SIZE, "Window too short");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observations.length;
    }
}
