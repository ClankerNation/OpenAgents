// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

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
    uint256 public constant MIN_WINDOW = 1800;
    uint256 public constant MAX_STALE_WINDOW = 3600;

    uint256 public windowSize = 1800;

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

        if (observations.length > 0) {
            Observation storage last = observations[observations.length - 1];
            require(block.timestamp > last.timestamp, "Same block");
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
            spotPrice: spotPrice
        }));

        emit ObservationRecorded(block.timestamp, spotPrice, lastCumulative);
    }

    function getTWAP() external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");

        Observation storage latest = observations[observations.length - 1];
        require(block.timestamp - latest.timestamp <= MAX_STALE_WINDOW, "Stale");

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
        require(_windowSize >= MIN_WINDOW, "Below minimum");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return observations.length;
    }
}
