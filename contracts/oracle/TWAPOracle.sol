// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title TWAPOracle
/// @notice Time-weighted average price oracle using cumulative price observations
/// @dev Records price snapshots and computes TWAP over a configurable window
/**
 * @custom:contributor CodexBaseUSDCHunter
 * @custom:date 2026-08-05
 * @custom:runtime darwin/arm64; shell /bin/zsh
 * @custom:note Private session initialization text is intentionally omitted.
 */
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

    uint256 public constant MIN_WINDOW = 30 minutes;
    uint256 public windowSize = MIN_WINDOW;

    event ObservationRecorded(uint256 timestamp, uint256 spotPrice, uint256 priceCumulative);
    event WindowUpdated(uint256 newWindow);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(address _pair) {
        require(_pair != address(0), "Zero pair");
        admin = msg.sender;
        pair = _pair;
    }

    function recordObservation(uint256 spotPrice) external {
        require(spotPrice > 0, "Zero price");

        uint256 lastCumulative = 0;
        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            require(block.timestamp > last.timestamp, "Same block");
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        observations.push(Observation({
            timestamp: block.timestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        }));

        emit ObservationRecorded(block.timestamp, spotPrice, lastCumulative);
    }

    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];
        uint256 latestAge = block.timestamp - latest.timestamp;
        require(latestAge <= windowSize, "Stale observations");

        uint256 targetTime = block.timestamp - windowSize;
        uint256 oldIndex = 0;
        bool found;

        for (uint256 i = observations.length - 1; i > 0; i--) {
            uint256 candidate = i - 1;
            if (observations[candidate].timestamp <= targetTime) {
                oldIndex = candidate;
                found = true;
                break;
            }
        }
        require(found, "Insufficient history");

        Observation storage old = observations[oldIndex];
        uint256 currentCumulative = latest.priceCumulative + (latest.spotPrice * latestAge);
        uint256 oldCumulative = old.priceCumulative + (old.spotPrice * (targetTime - old.timestamp));

        return (currentCumulative - oldCumulative) / windowSize;
    }

    function getLatestPrice() external view returns (uint256) {
        require(observations.length > 0, "No observations");
        return observations[observations.length - 1].spotPrice;
    }

    function setWindowSize(uint256 _windowSize) external onlyAdmin {
        require(_windowSize >= MIN_WINDOW, "Window too short");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observations.length;
    }
}
