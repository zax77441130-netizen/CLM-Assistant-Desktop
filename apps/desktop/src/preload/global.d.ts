import type { RuntimeStatus } from "../main/runtimeTypes";

declare global {
  interface Window {
    clmAssistant: {
      runtimeStatus: () => Promise<RuntimeStatus | null>;
      shutdownRuntime: () => Promise<RuntimeStatus | null>;
    };
  }
}

export {};
