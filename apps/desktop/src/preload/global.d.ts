import type { RuntimeStatus } from "@clm/contracts";

declare global {
  interface Window {
    clmAssistant: {
      runtimeStatus: () => Promise<RuntimeStatus | null>;
      shutdownRuntime: () => Promise<RuntimeStatus | null>;
    };
  }
}

export {};
