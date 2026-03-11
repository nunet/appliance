import { api } from "./api";
import type {
  FilesystemListResponse,
  FilesystemOperationResponse,
  FilesystemUploadResponse,
} from "@/types";

export async function listFilesystem(path: string) {
  const res = await api.get<FilesystemListResponse>("/filesystem/list", {
    params: { path },
  });
  return res.data;
}

export async function uploadFiles(params: {
  files: File[];
  path: string;
  overwrite?: boolean;
}) {
  const form = new FormData();
  params.files.forEach((file) => form.append("files", file));
  form.append("path", params.path);
  form.append("overwrite", String(Boolean(params.overwrite)));

  const res = await api.post<FilesystemUploadResponse>("/filesystem/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function copyFiles(payload: {
  sources: string[];
  destination: string;
  overwrite?: boolean;
}) {
  const res = await api.post<FilesystemOperationResponse>("/filesystem/copy", {
    ...payload,
    overwrite: Boolean(payload.overwrite),
  });
  return res.data;
}

export async function moveFiles(payload: {
  sources: string[];
  destination: string;
  overwrite?: boolean;
}) {
  const res = await api.post<FilesystemOperationResponse>("/filesystem/move", {
    ...payload,
    overwrite: Boolean(payload.overwrite),
  });
  return res.data;
}

export async function deleteFiles(payload: {
  paths: string[];
  recursive?: boolean;
}) {
  const res = await api.request<FilesystemOperationResponse>({
    url: "/filesystem",
    method: "DELETE",
    data: {
      ...payload,
      recursive: Boolean(payload.recursive),
    },
  });
  return res.data;
}

export async function downloadFile(path: string) {
  return api.get("/filesystem/download", {
    params: { path },
    responseType: "blob",
  });
}

export async function createFolder(payload: {
  path: string;
  parents?: boolean;
  exist_ok?: boolean;
}) {
  const res = await api.post("/filesystem/folder", {
    ...payload,
    parents: payload.parents ?? true,
    exist_ok: Boolean(payload.exist_ok),
  });
  return res.data as { status: string; message: string };
}
