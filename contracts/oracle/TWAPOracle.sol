// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TWAPOracle {
    struct Observation {
        uint256 timestamp;
        uint256 priceCumulative;
    }
    
    Observation[] public observations;
    uint256 public constant MAX_OBSERVATIONS = 100;
    
    function pushObservation(uint256 priceCumulative) external {
        if (observations.length >= MAX_OBSERVATIONS) {
            // Fix #132: rotate array instead of growing unbounded
            for (uint i = 0; i < MAX_OBSERVATIONS - 1; i++) {
                observations[i] = observations[i + 1];
            }
            observations[MAX_OBSERVATIONS - 1] = Observation(block.timestamp, priceCumulative);
        } else {
            observations.push(Observation(block.timestamp, priceCumulative));
        }
    }
    
    function getTWAP(uint256 window) external view returns (uint256) {
        require(observations.length >= 2, "Not enough observations");
        uint256 oldest = observations.length >= window ? observations.length - window : 0;
        uint256 timeElapsed = observations[observations.length - 1].timestamp - observations[oldest].timestamp;
        uint256 priceDiff = observations[observations.length - 1].priceCumulative - observations[oldest].priceCumulative;
        return priceDiff / timeElapsed;
    }
}
