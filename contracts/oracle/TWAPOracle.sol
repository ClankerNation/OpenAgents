// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor traceability:
 * Agent: Codex
 * Timestamp: 2026-05-25T11:11:02Z
 * Runtime: os=Windows, arch=x64, home_dir=C:\Users\tupm96,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
 */

/// @title TWAPOracle
/// @notice Time-weighted average price oracle using cumulative price observations
/// @dev Records price snapshots and computes TWAP over a configurable window.
contract TWAPOracle {
    struct Observation {
        uint256 timestamp;
        uint256 priceCumulative;
        uint256 spotPrice;
    }

    address public pair;
    address public admin;

    Observation[] public observations;
    uint256 public constant PRECISION = 1e18;
    uint256 public constant MIN_WINDOW_SIZE = 30 minutes;
    uint256 public windowSize = MIN_WINDOW_SIZE;
    uint256 public lastObservationBlock;

    event ObservationRecorded(uint256 timestamp, uint256 spotPrice, uint256 priceCumulative);
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
        require(block.number > lastObservationBlock, "Observation already recorded");

        uint256 lastCumulative = 0;
        uint256 observationTimestamp = block.timestamp;

        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        lastObservationBlock = block.number;
        observations.push(Observation({
            timestamp: observationTimestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        }));

        emit ObservationRecorded(observationTimestamp, spotPrice, lastCumulative);
    }

    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];
        require(block.timestamp <= latest.timestamp + windowSize, "Stale price");

        uint256 targetTime = latest.timestamp > windowSize ? latest.timestamp - windowSize : 0;
        uint256 oldIndex = 0;
        bool windowCovered = false;

        for (uint256 i = observations.length; i > 0; i--) {
            uint256 index = i - 1;
            if (observations[index].timestamp <= targetTime) {
                oldIndex = index;
                windowCovered = true;
                break;
            }
        }

        require(windowCovered, "Window not covered");

        Observation storage old = observations[oldIndex];
        uint256 timeElapsed = latest.timestamp - old.timestamp;
        require(timeElapsed > 0, "Invalid observation window");

        return (latest.priceCumulative - old.priceCumulative) / timeElapsed;
    }

    function getLatestPrice() external view returns (uint256) {
        require(observations.length > 0, "No observations");
        Observation storage latest = observations[observations.length - 1];
        require(block.timestamp <= latest.timestamp + windowSize, "Stale price");
        return latest.spotPrice;
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
