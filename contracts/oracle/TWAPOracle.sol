// @contributor rafaio1
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
        uint256 blockNumber;
    }

    address public pair;
    address public admin;

    Observation[] public observations;
    uint256 public constant PRECISION = 1e18;

    // Minimum 30-minute window to prevent flash loan manipulation
    uint256 public windowSize = 1800; // 30 minutes
    uint256 public constant MAX_STALENESS = 3600; // 1 hour max staleness

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

        // Prevent same-block manipulation: only one observation per block
        if (observations.length > 0) {
            require(
                observations[observations.length - 1].blockNumber < block.number,
                "TWAPOracle: only one observation per block"
            );
        }

        uint256 lastCumulative = 0;

        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        observations.push(Observation({
            timestamp: block.timestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice,
            blockNumber: block.number
        }));

        emit ObservationRecorded(block.timestamp, spotPrice, lastCumulative);
    }

    /// @notice Get TWAP with staleness protection
    /// @dev Reverts if latest observation is older than MAX_STALENESS
    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];

        // Staleness check: reject outdated prices
        require(
            block.timestamp - latest.timestamp <= MAX_STALENESS,
            "TWAPOracle: price data stale"
        );

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

        // Enforce minimum window to prevent manipulation
        require(timeElapsed >= windowSize, "TWAPOracle: insufficient window");

        return (latest.priceCumulative - old.priceCumulative) / timeElapsed;
    }

    function getLatestPrice() external view returns (uint256) {
        require(observations.length > 0, "No observations");
        return observations[observations.length - 1].spotPrice;
    }

    function setWindowSize(uint256 _windowSize) external onlyAdmin {
        require(_windowSize >= 1800, "TWAPOracle: min window 30 min");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observations.length;
    }
}
