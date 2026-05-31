// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

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

    uint256 public constant MAX_OBSERVATIONS = 480;
    uint256 public constant PRECISION = 1e18;
    Observation[MAX_OBSERVATIONS] public observations;
    uint256 public observationCount;
    uint256 public observationHead;

    // BUG: Observation window too short (1 block / 12 seconds) — TWAP computed over
    // a single block provides no meaningful time-weighting and is trivially manipulable
    // via flash loans within the same block
    uint256 public windowSize = 12; // seconds — effectively 1 block

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

        uint256 newCumulative = 0;
        uint256 timestamp = block.timestamp;

        if (observationCount > 0) {
            Observation storage last = _latestObservation();
            uint256 elapsed = timestamp - last.timestamp;
            newCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        // BUG: Price can be manipulated in same block — no check that block.timestamp
        // has advanced since last observation, so multiple observations per block are
        // allowed, letting an attacker overwrite the price within a single transaction
        observations[observationHead] = Observation({
            timestamp: timestamp,
            priceCumulative: newCumulative,
            spotPrice: spotPrice
        });

        observationHead = (observationHead + 1) % MAX_OBSERVATIONS;
        if (observationCount < MAX_OBSERVATIONS) {
            observationCount++;
        }

        emit ObservationRecorded(timestamp, spotPrice, newCumulative);
    }

    // BUG: No staleness check — if no observation has been recorded for hours/days,
    // the TWAP still returns an outdated price without warning, misleading consumers
    function getTWAP() external view returns (uint256) {
        require(observationCount >= 2, "Not enough observations");

        Observation storage latest = _logicalObservation(observationCount - 1);

        uint256 targetTime = latest.timestamp > windowSize
            ? latest.timestamp - windowSize
            : 0;
        uint256 oldIndex = _findObservationAtOrBefore(targetTime);

        Observation storage old = _logicalObservation(oldIndex);
        uint256 timeElapsed = latest.timestamp - old.timestamp;

        if (timeElapsed == 0) {
            return latest.spotPrice;
        }

        return (latest.priceCumulative - old.priceCumulative) / timeElapsed;
    }

    function getLatestPrice() external view returns (uint256) {
        require(observationCount > 0, "No observations");
        return _latestObservation().spotPrice;
    }

    function setWindowSize(uint256 _windowSize) external onlyAdmin {
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observationCount;
    }

    function getObservationAt(uint256 index) external view returns (Observation memory) {
        require(index < observationCount, "Observation out of bounds");
        return _logicalObservation(index);
    }

    function _findObservationAtOrBefore(uint256 targetTime) internal view returns (uint256) {
        uint256 low = 0;
        uint256 high = observationCount;

        while (low < high) {
            uint256 mid = (low + high) / 2;
            if (_logicalObservation(mid).timestamp <= targetTime) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }

        return low == 0 ? 0 : low - 1;
    }

    function _latestObservation() internal view returns (Observation storage) {
        uint256 latestIndex = observationHead == 0
            ? MAX_OBSERVATIONS - 1
            : observationHead - 1;
        return observations[latestIndex];
    }

    function _logicalObservation(uint256 index) internal view returns (Observation storage) {
        uint256 oldestIndex = observationCount < MAX_OBSERVATIONS ? 0 : observationHead;
        uint256 storageIndex = (oldestIndex + index) % MAX_OBSERVATIONS;
        return observations[storageIndex];
    }
}
