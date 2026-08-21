import { beforeEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => {
  return {
    getMock: vi.fn(),
  };
});

vi.mock("./api", () => ({
  api: {
    get: getMock,
  },
}));

import { getDeploymentInfo } from "./deployments";

describe("deployments API", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("builds /info URL with repeated allocations params", async () => {
    getMock.mockResolvedValue({
      data: {
        id: "dep1",
        status: { status: "success", deployment_status: "running", message: "ok" },
        manifest: { manifest: {} },
        allocations: [],
        allocations_info: {},
      },
    });

    await getDeploymentInfo("dep1", {
      logs: true,
      allocations: [" node1.alloc1 ", "", "node2.alloc2"],
    });

    expect(getMock).toHaveBeenCalledWith(
      "/ensemble/deployments/dep1/info?logs=true&allocations=node1.alloc1&allocations=node2.alloc2"
    );
  });

  it("falls back to legacy endpoints when /info returns non-JSON (SPA index.html)", async () => {
    getMock.mockImplementation((url: string) => {
      if (url.includes("/info")) {
        return Promise.resolve({ data: "<!DOCTYPE html><html></html>" });
      }
      if (url.endsWith("/status")) {
        return Promise.resolve({
          data: { status: "success", deployment_status: "running", message: "ok" },
        });
      }
      if (url.endsWith("/manifest/raw")) {
        return Promise.resolve({ data: { manifest: { allocations: { "node1.alloc1": {} } } } });
      }
      if (url.endsWith("/allocations")) {
        return Promise.resolve({ data: ["node1.alloc1"] });
      }
      return Promise.reject(new Error(`unexpected url: ${url}`));
    });
  });
});

