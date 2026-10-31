import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('contracts.ts', () => {
  describe('ContractDeployer', () => {
    it('throws on invalid bytecode', async () => {
      const { ContractDeployer } = await import('../src/utils/contracts.ts');
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      const deployer = new ContractDeployer(provider, '0x123');
      await assert.rejects(
        deployer.deployContract([], 'invalid'),
        /Invalid bytecode/
      );
    });

    it('throws on empty bytecode', async () => {
      const { ContractDeployer } = await import('../src/utils/contracts.ts');
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      const deployer = new ContractDeployer(provider, '0x123');
      await assert.rejects(
        deployer.deployContract([], ''),
        /Invalid bytecode/
      );
    });

    it('getContract returns contract instance', async () => {
      const { ContractDeployer } = await import('../src/utils/contracts.ts');
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      const deployer = new ContractDeployer(provider, '0x123');
      const contract = deployer.getContract('0xabc', [{ name: 'test' }]);
      assert.strictEqual(contract.address, '0xabc');
      assert.deepStrictEqual(contract.abi, [{ name: 'test' }]);
    });
  });

  describe('deployContract', () => {
    it('is exported as function', async () => {
      const mod = await import('../src/utils/contracts.ts');
      assert.strictEqual(typeof mod.deployContract, 'function');
    });
  });

  describe('DeploymentResult', () => {
    it('ContractDeployer is exported', async () => {
      const mod = await import('../src/utils/contracts.ts');
      assert.strictEqual(typeof mod.ContractDeployer, 'function');
    });
  });
});
