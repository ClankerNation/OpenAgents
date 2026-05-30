// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IPermit2.sol";

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract MockPermit2 is IPermit2 {
    event MockPermitTransfer(
        address indexed token,
        address indexed from,
        address indexed to,
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes signature
    );

    function permitTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external override {
        require(
            IERC20(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount),
            "Permit2: transfer failed"
        );
        emit MockPermitTransfer(
            permit.permitted.token,
            owner,
            transferDetails.to,
            transferDetails.requestedAmount,
            permit.nonce,
            permit.deadline,
            signature
        );
    }
}
