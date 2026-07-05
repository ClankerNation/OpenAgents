// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentNFT is ERC721, Ownable {
    uint256 public nextId;
    mapping(uint256 => string) public tokenURIs;
    
    event AgentMinted(uint256 indexed tokenId, address indexed owner, string metadata);
    
    constructor() ERC721("AgentNFT", "ANFT") Ownable(msg.sender) {}
    
    function mint(address to, string calldata metadata) external onlyOwner returns (uint256) {
        uint256 id = ++nextId;
        _safeMint(to, id);
        tokenURIs[id] = metadata;
        emit AgentMinted(id, to, metadata);
        return id;
    }
    
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        require(_exists(tokenId), "Nonexistent token");
        return tokenURIs[tokenId];
    }
}
