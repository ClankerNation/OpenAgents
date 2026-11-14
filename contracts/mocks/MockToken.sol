// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Configurable ERC-20 mock used by TaskRouter tests.
/// @dev Test double, not a production token. Same `transfer` /
/// `transferFrom` selectors as a real token, with switchable misbehaviour:
/// - default: well-behaved, returns true
/// - `failTransfer` / `failTransferFrom`: returns `false`, moves nothing
///   (USDT-style silent failure)
/// - `noReturn`: returns no data at all (legacy pre-standard token);
///   SafeERC20 tolerates it, a bare IERC20 call does not.
contract MockToken {
    string public name = "Mock Token";
    string public symbol = "MOCK";
    uint8 public decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    bool public failTransfer;
    bool public failTransferFrom;
    bool public noReturn;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function setFailTransfer(bool v) external {
        failTransfer = v;
    }

    function setFailTransferFrom(bool v) external {
        failTransferFrom = v;
    }

    function setNoReturn(bool v) external {
        noReturn = v;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        if (noReturn) {
            _move(msg.sender, to, amount);
            assembly {
                return(0, 0)
            }
        }
        if (failTransfer) return false;
        _move(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        if (noReturn) {
            _spend(from, amount);
            _move(from, to, amount);
            assembly {
                return(0, 0)
            }
        }
        if (failTransferFrom) return false;
        _spend(from, amount);
        _move(from, to, amount);
        return true;
    }

    function _spend(address from, uint256 amount) internal {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "Insufficient allowance");
        allowance[from][msg.sender] = allowed - amount;
    }

    function _move(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "Insufficient balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}
