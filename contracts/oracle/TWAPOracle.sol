// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
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

    // Fixed-size circular buffer for gas-efficient observation storage
    uint256 public constant MAX_OBSERVATIONS = 256;
    Observation[MAX_OBSERVATIONS] public observations;
    uint256 public observationCount;
    uint256 public headIndex; // Next write position (circular)

    uint256 public constant PRECISION = 1e18;

    // Minimum 5-minute window to prevent flash loan manipulation
    uint256 public windowSize = 300;
    uint256 public lastObservationTimestamp;

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
        // Prevent multiple observations in the same block to avoid manipulation
        require(block.timestamp > lastObservationTimestamp, "Same block");

        uint256 lastCumulative = 0;

        if (observationCount > 0) {
            uint256 lastIndex = (headIndex + MAX_OBSERVATIONS - 1) % MAX_OBSERVATIONS;
            Observation storage last = observations[lastIndex];
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        observations[headIndex] = Observation({
            timestamp: block.timestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        });

        headIndex = (headIndex + 1) % MAX_OBSERVATIONS;
        if (observationCount < MAX_OBSERVATIONS) {
            observationCount++;
        }
        lastObservationTimestamp = block.timestamp;

        emit ObservationRecorded(block.timestamp, spotPrice, lastCumulative);
    }

    function getTWAP() external view returns (uint256) {
        require(observationCount >= 2, "Not enough observations");

        uint256 latestIndex = (headIndex + MAX_OBSERVATIONS - 1) % MAX_OBSERVATIONS;
        Observation storage latest = observations[latestIndex];

        // Staleness check: reject if latest observation is older than 2x window
        require(block.timestamp - latest.timestamp <= windowSize * 2, "Stale data");

        // Find the oldest observation within the window
        uint256 targetTime = latest.timestamp - windowSize;
        uint256 oldIdx = latestIndex;

        // Walk backwards through circular buffer
        for (uint256 i = 0; i < observationCount - 1; i++) {
            uint256 idx = (latestIndex + MAX_OBSERVATIONS - 1 - i) % MAX_OBSERVATIONS;
            if (observations[idx].timestamp <= targetTime) {
                oldIdx = idx;
                break;
            }
        }

        Observation storage old = observations[oldIdx];
        uint256 timeElapsed = latest.timestamp - old.timestamp;

        if (timeElapsed == 0) {
            return latest.spotPrice;
        }

        return (latest.priceCumulative - old.priceCumulative) / timeElapsed;
    }

    function getLatestPrice() external view returns (uint256) {
        require(observationCount > 0, "No observations");
        uint256 latestIndex = (headIndex + MAX_OBSERVATIONS - 1) % MAX_OBSERVATIONS;
        return observations[latestIndex].spotPrice;
    }

    function setWindowSize(uint256 _windowSize) external onlyAdmin {
        require(_windowSize >= 60, "Window too short");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observationCount;
    }
}
