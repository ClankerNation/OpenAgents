// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IPermit2.sol";

interface IERC20Like {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract MockPermit2 is IPermit2 {
    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external override {
        require(signature.length > 0, "Invalid signature");
        require(block.timestamp <= permit.deadline, "Permit expired");
        require(transferDetails.requestedAmount <= permit.permitted.amount, "Invalid amount");
        require(IERC20Like(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount), "Transfer failed");
    }
}
