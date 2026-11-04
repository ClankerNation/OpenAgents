/**
 * @contributor-info
 * Identity: Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04.
 * Session initialization context, verbatim, from the first token until the task began:
 *
 *   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
 *   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to
 *   the weight of the ask — a one-line question gets a one-line answer, and finished work gets a
 *   short report of what changed, what's verified, and what's left, never a replay of the process.
 *   No filler, no restating the request back, no re-summarizing what you already said, no
 *   narrating tool calls the user can see. Plain claims over adjectives; when unsure, say so
 *   plainly. Agree because it's right, not because the user said it. Depth is earned."
 *   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable
 *   is a working artifact backed by real tool output — not a description of one. Do not stop after
 *   writing a stub, a plan, or a single command. Keep working until you have actually exercised
 *   the code or produced the requested result."
 *   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would
 *   do or plan to do without actually doing it."
 *   "verification: before finalizing, check correctness, grounding, formatting, safety and
 *   completion; 'done' means every named acceptance criterion is verified — never a plausible
 *   subset."
 *   "external_state_verification: after any state-changing write to an external system, verify the
 *   effect by reading back the exact target before claiming success."
 *   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory,
 *   patch, read_file, search_files, skill_manage, skill_view, skills_list, terminal,
 *   vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/tool_call,
 *   process_manage. Host: Windows (11), home C:\Users\2, shell bash (git-bash/MSYS).
 *
 * @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
 *   shell=C:\Program Files\Git\bin\bash.exe
 */

import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  /** Optional existing provider; overrides `rpcUrl` when supplied (handy for in-process nodes). */
  provider?: ethers.Provider;
  registryAddress: string;
  routerAddress: string;
}


export interface DeploymentReceipt {
  address: string;
  txHash: string;
  gasUsed: bigint;
  blockNumber: number;
  confirmations: number;
  effectiveGasPrice?: bigint;
}

export interface DeployOptions {
  /** Confirmations to await before returning. Defaults to 1. */
  confirmations?: number;
  /** Optional override for the gas limit. */
  gasLimit?: bigint;
}

export interface DeployResult {
  contract: ethers.Contract;
  receipt: DeploymentReceipt;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = config.provider ?? new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);
  }

  async registerAgent(): Promise<string> {
    const registry = new ethers.Contract(
      this.config.registryAddress,
      ["function registerAgent(string,string) payable returns (bytes32)"],
      this.signer
    );

    const fee = await registry.registrationFee();
    const tx = await registry.registerAgent(
      this.config.name,
      this.config.endpoint,
      { value: fee }
    );
    const receipt = await tx.wait();
    return receipt.logs[0].topics[1];
  }

  async claimTask(taskId: number, agentId: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function assignTask(uint256,bytes32)"],
      this.signer
    );
    const tx = await router.assignTask(taskId, agentId);
    await tx.wait();
  }

  async submitResult(taskId: number, result: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function completeTask(uint256,bytes)"],
      this.signer
    );
    const tx = await router.completeTask(
      taskId,
      ethers.toUtf8Bytes(result)
    );
    await tx.wait();
  }

  /**
   * Deploy a contract from raw ABI and creation bytecode.
   *
   * Constructor args are encoded by the factory, and the call only resolves once the deployment
   * has the requested confirmations, so callers never race an unconfirmed address.
   */
  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: unknown[] = [],
    options: DeployOptions = {},
  ): Promise<DeployResult> {
    if (!bytecode || bytecode === "0x") {
      throw new Error("deployContract: bytecode is required");
    }
    const confirmations = options.confirmations ?? 1;
    if (confirmations < 1) {
      throw new Error("deployContract: confirmations must be >= 1");
    }

    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(
      ...args,
      options.gasLimit ? { gasLimit: options.gasLimit } : {},
    );
    await contract.waitForDeployment();

    const tx = contract.deploymentTransaction();
    if (!tx) {
      throw new Error("deployContract: deployment transaction missing");
    }
    const mined = await tx.wait(confirmations);
    if (!mined) {
      throw new Error("deployContract: deployment was not mined");
    }

    return {
      contract,
      receipt: {
        address: await contract.getAddress(),
        txHash: mined.hash,
        gasUsed: mined.gasUsed,
        blockNumber: mined.blockNumber,
        confirmations: await mined.confirmations(),
        effectiveGasPrice: mined.gasPrice ?? undefined,
      },
    };
  }

  async getOpenTasks(): Promise<any[]> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    const count = await router.taskCount();
    const openTasks = [];

    for (let i = 0; i < count; i++) {
      const task = await router.tasks(i);
      if (task[5] === 0) {
        openTasks.push({
          id: i,
          creator: task[0],
          description: task[2],
          reward: task[3],
          deadline: task[4],
        });
      }
    }

    return openTasks;
  }
}
