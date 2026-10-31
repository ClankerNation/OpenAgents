import { describe, it } from 'node:test';
import assert from 'node:assert';
import { hashMessage, hashPersonalMessage, hashTypedData, recoverAddress, keccak256 } from '../src/utils/crypto.ts';

describe('crypto.ts', () => {
  describe('hashMessage', () => {
    it('produces EIP-191 compliant hash', () => {
      const hash = hashMessage('hello');
      assert.ok(hash.length === 64, 'Hash should be 64 hex chars');
      const expected = keccak256('\x19Ethereum Signed Message:\n5hello');
      assert.strictEqual(hash, expected);
    });

    it('handles empty message', () => {
      const hash = hashMessage('');
      assert.ok(hash.length === 64);
    });
  });

  describe('hashPersonalMessage', () => {
    it('produces same result as hashMessage', () => {
      assert.strictEqual(hashPersonalMessage('hello'), hashMessage('hello'));
      assert.strictEqual(hashPersonalMessage(''), hashMessage(''));
    });
  });

  describe('hashTypedData', () => {
    it('handles EIP-712 domain + types', () => {
      const domain = {
        name: 'Test',
        version: '1',
        chainId: 1,
        verifyingContract: '0x0000000000000000000000000000000000000000',
      };
      const types = {
        EIP712Domain: [
          { name: 'name', type: 'string' },
          { name: 'version', type: 'string' },
          { name: 'chainId', type: 'uint256' },
          { name: 'verifyingContract', type: 'address' },
        ],
        Person: [
          { name: 'name', type: 'string' },
          { name: 'wallet', type: 'address' },
        ],
      };
      const value = {
        name: 'Alice',
        wallet: '0x0000000000000000000000000000000000000001',
      };
      const hash = hashTypedData(domain, types, value);
      assert.ok(hash.length === 64, 'Hash should be 64 hex chars');
    });
  });

  describe('recoverAddress', () => {
    it('returns empty string for invalid signature', () => {
      const addr = recoverAddress('hello', '0x' + '00'.repeat(65));
      assert.strictEqual(addr, '');
    });

    it('returns string type', () => {
      const addr = recoverAddress('hello', '0x' + '00'.repeat(65));
      assert.ok(typeof addr === 'string');
    });
  });

  describe('keccak256', () => {
    it('produces 64-char hex hash', () => {
      const hash = keccak256('hello');
      assert.ok(hash.length === 64);
    });

    it('is deterministic', () => {
      assert.strictEqual(keccak256('hello'), keccak256('hello'));
    });
  });
});
