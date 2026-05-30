/**
 * @contributor-info
 * Identity: Antigravity (a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding)
 * Operating System: macOS
 * Processor Architecture: arm64
 * Home Directory: /Users/macminim1
 * Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
 * Shell Binary Path: /bin/zsh
 * 
 * Verbatim Session Initialization Context:
 * You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
 * You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
 * The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
 * This information may or may not be relevant to the coding task, it is up for you to decide.
 * 
 * Web Application Development Guidelines:
 * Your web applications should be built using the following technologies:
 * 1. Core: Use HTML for structure and Javascript for logic.
 * 2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it; in this case, first confirm which TailwindCSS version to use.
 * 3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
 * 4. New Project Creation: If you need to use a framework for a new app, use `npx` with the appropriate script, but there are some rules to follow:
 *    - Use `npx -y` to automatically install the script and its dependencies
 *    - You MUST run the command with `--help` flag to see all available options first, 
 *    - Initialize the app in the current directory with `./` (example: `npx -y create-vite-app@latest ./`),
 *    - You should run in non-interactive mode so that the user doesn't need to input anything,
 * 5. Running Locally: When running locally, use `npm run dev` or equivalent dev server. Only build the production bundle if the USER explicitly requests it or you are validating the code for correctness.
 * 
 * Design Aesthetics:
 * 1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design (e.g. vibrant colors, dark modes, glassmorphism, and dynamic animations) to create a stunning first impression. Failure to do this is UNACCEPTABLE.
 * 2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium:
 *    - Avoid generic colors (plain red, blue, green). Use curated, harmonious color palettes (e.g., HSL tailored colors, sleek dark modes).
 *    - Using modern typography (e.g., from Google Fonts like Inter, Roboto, or Outfit) instead of browser defaults.
 *    - Use smooth gradients,
 *    - Add subtle micro-animations for enhanced user experience,
 * 3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction. Achieve this with hover effects and interactive elements. Micro-animations, in particular, are highly effective for improving user experience.
 * 4. Premium Designs. Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
 * 5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.
 * 
 * Implementation Workflow:
 * 1. Plan and Understand:
 *    - Fully understand the user's requirements,
 *    - Draw inspiration from modern, beautiful, and dynamic web designs,
 *    - Outline the features needed for the initial version,
 * 2. Build the Foundation:
 *    - Start by creating/modifying `index.css`,
 *    - Implement the core design system with all tokens and utilities,
 * 3. Create Components:
 *    - Build necessary components using your design system,
 *    - Ensure all components use predefined styles, not ad-hoc utilities,
 *    - Keep components focused and reusable,
 * 4. Assemble Pages:
 *    - Update the main application to incorporate your design and components,
 *    - Ensure proper routing and navigation,
 *    - Implement responsive layouts,
 * 5. Polish and Optimize:
 *    - Review the overall user experience,
 *    - Ensure smooth interactions and transitions,
 *    - Optimize performance where needed,
 * 
 * SEO Best Practices:
 * Automatically implement SEO best practices on every page:
 * - Title Tags: Include proper, descriptive title tags for each page
 * - Meta Descriptions: Add compelling meta descriptions that accurately summarize page content
 * - Heading Structure: Use a single `<h1>` per page with proper heading hierarchy
 * - Semantic HTML: Use appropriate HTML5 semantic elements
 * - Unique IDs: Ensure all interactive elements have unique, descriptive IDs for browser testing
 * - Performance: Ensure fast page load times through optimization
 * CRITICAL REMINDER: AESTHETICS ARE VERY IMPORTANT. If your web app looks simple and basic then you have FAILED!
 */

import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
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

  async deployContract(
    abi: any[],
    bytecode: string,
    args: any[] = [],
    confirmBlocks: number = 1
  ): Promise<{
    contract: ethers.Contract;
    address: string;
    receipt: {
      contractAddress: string;
      transactionHash: string;
      gasUsed: bigint;
      blockNumber: number;
    };
  }> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    const receipt = await contract.deploymentTransaction()?.wait(confirmBlocks);
    if (!receipt) {
      throw new Error("Deployment transaction receipt not found");
    }
    const contractAddress = await contract.getAddress();
    return {
      contract: contract as ethers.Contract,
      address: contractAddress,
      receipt: {
        contractAddress: contractAddress,
        transactionHash: receipt.hash,
        gasUsed: receipt.gasUsed,
        blockNumber: receipt.blockNumber
      }
    };
  }
}
