// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../AgentRegistry.sol";

contract AgentRegistryHarness is AgentRegistry {
    constructor(uint256 registrationFee) AgentRegistry(registrationFee) {}
}
