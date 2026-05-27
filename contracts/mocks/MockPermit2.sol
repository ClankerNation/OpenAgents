// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IPermit2.sol";

interface IERC20Like {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract MockPermit2 is IPermit2 {
    event PermitTransfer(address indexed token, address indexed owner, address indexed to, uint256 amount);

    function permitTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external {
        require(signature.length > 0, "Invalid signature");
        require(block.timestamp <= permit.deadline, "Permit expired");
        require(transferDetails.requestedAmount <= permit.permitted.amount, "Permit amount too low");
        require(
            IERC20Like(permit.permitted.token).transferFrom(
                owner,
                transferDetails.to,
                transferDetails.requestedAmount
            ),
            "Permit transfer failed"
        );

        emit PermitTransfer(
            permit.permitted.token,
            owner,
            transferDetails.to,
            transferDetails.requestedAmount
        );
    }
}
