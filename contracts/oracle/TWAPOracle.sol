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

    uint256 public constant OBSERVATION_BUFFER = 100;
    Observation[] public observations;
    uint256 public constant PRECISION = 1e18;

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

        uint256 lastCumulative = 0;
        uint256 lastTimestamp = block.timestamp;

        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
            lastTimestamp = block.timestamp;
        }

        // BUG: Price can be manipulated in same block — no check that block.timestamp
        // has advanced since last observation, so multiple observations per block are
        // allowed, letting an attacker overwrite the price within a single transaction
        observations[observationCount % OBSERVATION_BUFFER] = observation;
            timestamp: lastTimestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        }));

        emit ObservationRecorded(lastTimestamp, spotPrice, lastCumulative);
    }

    // BUG: No staleness check — if no observation has been recorded for hours/days,
    // the TWAP still returns an outdated price without warning, misleading consumers
    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];

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
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observations.length;
    }
}
