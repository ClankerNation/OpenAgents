// @contributor rafaio1
// @date 2026-08-21T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title TWAPOracle
/// @notice Time-weighted average price oracle using cumulative price observations
/// @dev Records price snapshots and computes TWAP over a configurable window
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
    uint256 public constant MIN_WINDOW_SIZE = 1800; // 30 minutes minimum

    uint256 public windowSize = 1800; // Default 30 minutes
    uint256 public lastObservationBlock; // Track block number to prevent same-block manipulation

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
        // Enforce one observation per block to prevent same-block manipulation
        require(block.number > lastObservationBlock, "Oracle: only one observation per block");

        uint256 lastCumulative = 0;

        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        observations.push(Observation({
            timestamp: block.timestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        }));

        lastObservationBlock = block.number;
        emit ObservationRecorded(block.timestamp, spotPrice, lastCumulative);
    }

    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];

        // Staleness check: revert if latest observation is older than windowSize
        require(block.timestamp - latest.timestamp <= windowSize, "Oracle: stale price");

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
        require(_windowSize >= MIN_WINDOW_SIZE, "Oracle: window too short");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observations.length;
    }
}
