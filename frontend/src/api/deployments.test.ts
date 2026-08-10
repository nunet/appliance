import { beforeEach, describe, expect, it, vi } from "vitest";

const { getMock, postMock } = vi.hoisted(() => {
  return {
    getMock: vi.fn(),
    postMock: vi.fn(),
  };
});

vi.mock("./api", () => ({
  api: {
    get: getMock,
    post: postMock,
  },
}));

import {
  getDeploymentInfo,
  getDeploymentLogsAsyncStatus,
  startDeploymentLogsAsync,
  stopDeploymentLogsAsync,
} from "./deployments";

describe("deployments API", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
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

  it("builds async status URL with allocation params", async () => {
    getMock.mockResolvedValue({
      data: {
        status: "success",
        message: "ok",
        fetch_status: "running",
      },
    });

    await getDeploymentLogsAsyncStatus("dep1", {
      allocation: "node1.alloc1",
      allocations: "node1.alloc1,node2.alloc2",
    });

    expect(getMock).toHaveBeenCalledWith("/ensemble/deployments/dep1/logs/async/status", {
      params: {
        allocations: "node1.alloc1,node2.alloc2",
        allocation: "node1.alloc1",
      },
    });
  });

  it("builds async start/stop URLs with allocation params", async () => {
    postMock.mockResolvedValue({
      data: { status: "success", message: "ok", fetch_status: "running" },
    });

    await startDeploymentLogsAsync("dep1", {
      allocation: "node1.alloc1",
      allocations: "node1.alloc1",
    });
    await stopDeploymentLogsAsync("dep1", {
      allocation: "node1.alloc1",
      allocations: "node1.alloc1",
    });

    expect(postMock).toHaveBeenNthCalledWith(
      1,
      "/ensemble/deployments/dep1/logs/async/start",
      null,
      { params: { allocations: "node1.alloc1", allocation: "node1.alloc1" } }
    );
    expect(postMock).toHaveBeenNthCalledWith(
      2,
      "/ensemble/deployments/dep1/logs/async/stop",
      null,
      { params: { allocations: "node1.alloc1", allocation: "node1.alloc1" } }
    );
  });
});

