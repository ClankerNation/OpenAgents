// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T02:45:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

/// @title TWAPOracle
/// @notice Time-weighted average price oracle using circular buffer observations
/// @dev Fixed-size ring buffer with binary search for efficient TWAP calculation
contract TWAPOracle {
    struct Observation {
        uint256 timestamp;
        uint256 priceCumulative;
        uint256 spotPrice;
    }

    address public pair;
    address public admin;

    // Circular buffer with fixed capacity
    uint256 public constant BUFFER_SIZE = 480;
    Observation[BUFFER_SIZE] public observations;
    uint256 public head;       // Next write index
    uint256 public count;      // Total observations recorded (up to BUFFER_SIZE)
    
    uint256 public constant PRECISION = 1e18;
    uint256 public windowSize = 3600; // 1 hour default (was 12s)

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
        
        if (count > 0) {
            // Get previous observation (handle wrap-around)
            uint256 prevIndex = (head + BUFFER_SIZE - 1) % BUFFER_SIZE;
            Observation storage last = observations[prevIndex];
            
            // Prevent same-block manipulation
            require(block.timestamp > last.timestamp, "Same block");
            
            uint256 elapsed = block.timestamp - last.timestamp;
            lastCumulative = last.priceCumulative + (last.spotPrice * elapsed);
        }

        // Write to current head position (overwrites oldest when full)
        observations[head] = Observation({
            timestamp: block.timestamp,
            priceCumulative: lastCumulative,
            spotPrice: spotPrice
        });

        head = (head + 1) % BUFFER_SIZE;
        if (count < BUFFER_SIZE) {
            count++;
        }

        emit ObservationRecorded(block.timestamp, spotPrice, lastCumulative);
    }

    /// @notice Get TWAP over the configured window using binary search.
    /// @dev Gas cost is O(log n) regardless of observation count.
    function getTWAP() external view returns (uint256) {
        require(count >= 2, "Not enough observations");

        // Latest observation index
        uint256 latestIndex = (head + BUFFER_SIZE - 1) % BUFFER_SIZE;
        Observation storage latest = observations[latestIndex];

        uint256 targetTime = latest.timestamp - windowSize;

        // Binary search for oldest observation within window
        uint256 oldIndex = _binarySearchOldest(targetTime);
        Observation storage old = observations[oldIndex];

        uint256 timeElapsed = latest.timestamp - old.timestamp;
        if (timeElapsed == 0) {
            return latest.spotPrice;
        }

        return (latest.priceCumulative - old.priceCumulative) / timeElapsed;
    }

    /// @dev Binary search in circular buffer for observation at or after targetTime.
    function _binarySearchOldest(uint256 targetTime) internal view returns (uint256) {
        if (count <= 1) return (head + BUFFER_SIZE - 1) % BUFFER_SIZE;

        // Determine actual start index in buffer
        uint256 start = count < BUFFER_SIZE ? 0 : head;
        
        uint256 low = 0;
        uint256 high = count - 1;
        uint256 result = high; // Default to latest if all are after target

        while (low <= high) {
            uint256 mid = (low + high) / 2;
            uint256 actualIndex = (start + mid) % BUFFER_SIZE;
            
            if (observations[actualIndex].timestamp <= targetTime) {
                result = mid;
                if (mid == 0) break;
                low = mid + 1; // Search newer half
            } else {
                if (mid == 0) break;
                high = mid - 1; // Search older half
            }
        }

        return (start + result) % BUFFER_SIZE;
    }

    function getLatestPrice() external view returns (uint256) {
        require(count > 0, "No observations");
        uint256 latestIndex = (head + BUFFER_SIZE - 1) % BUFFER_SIZE;
        return observations[latestIndex].spotPrice;
    }

    function setWindowSize(uint256 _windowSize) external onlyAdmin {
        require(_windowSize > 0, "Invalid window");
        windowSize = _windowSize;
        emit WindowUpdated(_windowSize);
    }

    function getObservationCount() external view returns (uint256) {
        return count;
    }

    function getBufferSize() external pure returns (uint256) {
        return BUFFER_SIZE;
    }
}
