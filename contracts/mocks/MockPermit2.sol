// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IPermit2.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract MockPermit2 is IPermit2 {
    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external override {
        IERC20(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount);
    }
}
