const { expect } = require('chai');
const { ethers } = require('hardhat');

const AGENT_REGISTERED_TOPIC = '0x186c9e760261cf9d36dfc9a09ca598dbff789d7d4201868118b92d46e56dac80';

describe('AgentRegistry', function () {
  let registry, owner, agent1, agent2;
  const REGISTRATION_FEE = ethers.parseEther('0.1');

  beforeEach(async function () {
    [owner, agent1, agent2] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory('AgentRegistry');
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
  });

  function getAgentRegisteredLogs(receipt) {
    return receipt.logs.filter(l => l.topics[0] === AGENT_REGISTERED_TOPIC);
  }

  describe('registerAgent', function () {
    it('should register a single agent', async function () {
      const tx = await registry.connect(agent1).registerAgent(
        'TestAgent',
        'https://agent1.example.com',
        { value: REGISTRATION_FEE }
      );
      const receipt = await tx.wait();
      const logs = getAgentRegisteredLogs(receipt);
      expect(logs.length).to.equal(1);
      const parsed = registry.interface.decodeEventLog(
        registry.interface.getEvent('AgentRegistered(bytes32,address,string)').name,
        logs[0].data, logs[0].topics
      );
      expect(parsed.name).to.equal('TestAgent');
      expect(parsed.owner).to.equal(agent1.address);
    });

    it('should reject insufficient fee', async function () {
      await expect(
        registry.connect(agent1).registerAgent('TestAgent', 'https://t.com', { value: REGISTRATION_FEE - 1n })
      ).to.be.revertedWith('Insufficient fee');
    });

    it('should reject invalid name (empty)', async function () {
      await expect(
        registry.connect(agent1).registerAgent('', 'https://t.com', { value: REGISTRATION_FEE })
      ).to.be.revertedWith('Invalid name');
    });

    it('should reject invalid name (too long)', async function () {
      const longName = 'a'.repeat(65);
      await expect(
        registry.connect(agent1).registerAgent(longName, 'https://t.com', { value: REGISTRATION_FEE })
      ).to.be.revertedWith('Invalid name');
    });
  });

  describe('batchRegister', function () {
    it('should register a batch of agents in one transaction', async function () {
      const names = ['AgentA', 'AgentB', 'AgentC'];
      const endpoints = ['https://a.example.com', 'https://b.example.com', 'https://c.example.com'];
      const totalFee = REGISTRATION_FEE * BigInt(names.length);
      const tx = await registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      const logs = getAgentRegisteredLogs(receipt);
      expect(logs.length).to.equal(3);
      for (let i = 0; i < 3; i++) {
        const parsed = registry.interface.decodeEventLog(
          registry.interface.getEvent('AgentRegistered(bytes32,address,string)').name,
          logs[i].data, logs[i].topics
        );
        expect(parsed.name).to.equal(names[i]);
      }
    });

    it('should support batch of 1 (edge case)', async function () {
      const names = ['SingleAgent'];
      const endpoints = ['https://single.example.com'];
      const totalFee = REGISTRATION_FEE;
      const tx = await registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      const logs = getAgentRegisteredLogs(receipt);
      expect(logs.length).to.equal(1);
    });

    it('should support batch of 50 (max)', async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 50; i++) {
        names.push('Agent' + i);
        endpoints.push('https://agent' + i + '.example.com');
      }
      const totalFee = REGISTRATION_FEE * 50n;
      const tx = await registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      const logs = getAgentRegisteredLogs(receipt);
      expect(logs.length).to.equal(50);
    });

    it('should reject batch larger than 50', async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 51; i++) {
        names.push('Agent' + i);
        endpoints.push('https://agent' + i + '.example.com');
      }
      const totalFee = REGISTRATION_FEE * 51n;
      await expect(
        registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith('Batch too large');
    });

    it('should reject array length mismatch', async function () {
      const names = ['AgentA', 'AgentB'];
      const endpoints = ['https://a.example.com'];
      const totalFee = REGISTRATION_FEE * 2n;
      await expect(
        registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith('Array length mismatch');
    });

    it('should reject empty names array', async function () {
      await expect(
        registry.connect(agent1).batchRegister([], [], { value: 0 })
      ).to.be.revertedWith('Empty names array');
    });

    it('should reject insufficient fee in batch', async function () {
      const names = ['AgentA', 'AgentB'];
      const endpoints = ['https://a.com', 'https://b.com'];
      const totalFee = REGISTRATION_FEE - 1n;
      await expect(
        registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith('Insufficient fee');
    });

    it('should reject invalid name in batch', async function () {
      const names = ['Valid', ''];
      const endpoints = ['https://a.com', 'https://b.com'];
      const totalFee = REGISTRATION_FEE * 2n;
      await expect(
        registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith('Invalid name');
    });

    it('should assign unique IDs to each agent', async function () {
      const names = ['UniqueA', 'UniqueB'];
      const endpoints = ['https://a.com', 'https://b.com'];
      const totalFee = REGISTRATION_FEE * 2n;
      const tx = await registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      const logs = getAgentRegisteredLogs(receipt);
      const iface = registry.interface;
      const evt = iface.getEvent('AgentRegistered(bytes32,address,string)');
      const parsed0 = iface.decodeEventLog(registry.interface.getEvent('AgentRegistered(bytes32,address,string)').name, logs[0].data, logs[0].topics);
      const parsed1 = iface.decodeEventLog(registry.interface.getEvent('AgentRegistered(bytes32,address,string)').name, logs[1].data, logs[1].topics);
      expect(parsed0.agentId).to.not.equal(parsed1.agentId);
    });

    it('should store agent data correctly', async function () {
      const names = ['DataAgent'];
      const endpoints = ['https://data.example.com'];
      const totalFee = REGISTRATION_FEE;
      await registry.connect(agent1).batchRegister(names, endpoints, { value: totalFee });
      const agentIds = await registry.agentIds(0);
      const agent = await registry.getAgent(agentIds);
      expect(agent.name).to.equal('DataAgent');
      expect(agent.endpoint).to.equal('https://data.example.com');
      expect(agent.owner).to.equal(agent1.address);
      expect(agent.reputation).to.equal(100);
      expect(agent.active).to.equal(true);
    });
  });

  describe('deactivateAgent', function () {
    it('should allow owner to deactivate their agent', async function () {
      await registry.connect(agent1).registerAgent('DeactAgent', 'https://d.com', { value: REGISTRATION_FEE });
      const agentId = await registry.agentIds(0);
      await registry.connect(agent1).deactivateAgent(agentId);
      const agent = await registry.getAgent(agentId);
      expect(agent.active).to.equal(false);
    });

    it('should reject non-owner deactivation', async function () {
      await registry.connect(agent1).registerAgent('DeactAgent', 'https://d.com', { value: REGISTRATION_FEE });
      const agentId = await registry.agentIds(0);
      await expect(registry.connect(agent2).deactivateAgent(agentId)).to.be.revertedWith('Not agent owner');
    });
  });

  describe('updateReputation', function () {
    it('should allow owner to increase reputation', async function () {
      await registry.connect(agent1).registerAgent('RepAgent', 'https://r.com', { value: REGISTRATION_FEE });
      const agentId = await registry.agentIds(0);
      await registry.updateReputation(agentId, 50);
      const agent = await registry.getAgent(agentId);
      expect(agent.reputation).to.equal(150);
    });

    it('should allow owner to decrease reputation', async function () {
      await registry.connect(agent1).registerAgent('RepAgent', 'https://r.com', { value: REGISTRATION_FEE });
      const agentId = await registry.agentIds(0);
      await registry.updateReputation(agentId, 50);
      await registry.updateReputation(agentId, -30);
      const agent = await registry.getAgent(agentId);
      expect(agent.reputation).to.equal(120);
    });

    it('should not allow negative reputation below zero', async function () {
      await registry.connect(agent1).registerAgent('RepAgent', 'https://r.com', { value: REGISTRATION_FEE });
      const agentId = await registry.agentIds(0);
      await registry.updateReputation(agentId, -200);
      const agent = await registry.getAgent(agentId);
      expect(agent.reputation).to.equal(0);
    });

    it('should reject updating unknown agent', async function () {
      const fakeId = ethers.keccak256(ethers.toUtf8Bytes('fake'));
      await expect(registry.updateReputation(fakeId, 10)).to.be.revertedWith('Agent not found');
    });
  });

  describe('getActiveAgentCount', function () {
    it('should return correct count of active agents', async function () {
      await registry.connect(agent1).registerAgent('Act1', 'https://a.com', { value: REGISTRATION_FEE });
      await registry.connect(agent1).registerAgent('Act2', 'https://b.com', { value: REGISTRATION_FEE });
      const count = await registry.getActiveAgentCount();
      expect(count).to.equal(2);
    });

    it('should exclude deactivated agents', async function () {
      await registry.connect(agent1).registerAgent('Act1', 'https://a.com', { value: REGISTRATION_FEE });
      await registry.connect(agent1).registerAgent('Inact', 'https://b.com', { value: REGISTRATION_FEE });
      const agentId = await registry.agentIds(1);
      await registry.connect(agent1).deactivateAgent(agentId);
      const count = await registry.getActiveAgentCount();
      expect(count).to.equal(1);
    });
  });

  describe('setRegistrationFee', function () {
    it('should allow owner to update fee', async function () {
      await registry.setRegistrationFee(ethers.parseEther('1'));
      expect(await registry.registrationFee()).to.equal(ethers.parseEther('1'));
    });

    it('should reject non-owner fee update', async function () {
      await expect(registry.connect(agent1).setRegistrationFee(ethers.parseEther('1'))).to.be.reverted;
    });
  });
});
