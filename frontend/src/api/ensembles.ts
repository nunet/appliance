// frontend/src/api/ensembles.ts
import { api } from "./api";
import {
  UploadTemplateResponse,
  FormSchema,
  FormTemplatesResponse,
  YamlTemplatesResponse,
} from "@/types";

// ------- Lists --------
export async function listFormTemplates(page = 1, pageSize = 10) {
  const res = await api.get<FormTemplatesResponse>(
    "/ensemble/templates/forms",
    {
      params: {
        page,
        page_size: pageSize,
        include_schema: true,
        require_yaml_match: true,
      },
    }
  );
  return res.data;
}

export async function listYamlTemplates(
  page = 1,
  pageSize = 10,
  withContent = false
) {
  const res = await api.get<YamlTemplatesResponse>(
    "/ensemble/templates/yamls",
    {
      params: { page, page_size: pageSize, with_content: withContent },
    }
  );
  return res.data;
}

// ------- Upload & Fetch -------
export async function uploadTemplate(form: FormData) {
  // FormData fields supported by backend:
  // - file (yaml) [required]
  // - sidecar (json) [optional]
  // - category [optional]
  // - confirm_overwrite [optional: "true"/"false"]
  // - contract_required [optional: "true"/"false"]  -- controls which default JSON form is applied
  const res = await api.post<UploadTemplateResponse>(
    "/ensemble/templates/upload",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return res.data;
}

export async function getEffectiveSchema(
  templatePath: string,
  source: "auto" | "sidecar" | "inferred" = "auto"
) {
  // Returns FormSchema directly
  const res = await api.get<FormSchema>(
    "/ensemble/templates/schema",
    { params: { template_path: templatePath, source } }
  );
  return res.data;
}

export interface TemplateDetailResponse {
  status: string;
  yaml_path: string;
  json_path?: string | null;
  category: string;
  yaml_content: string;
  json_content?: string | null;
  modified_at?: string;
  size?: number;
}

export async function getTemplateDetail(templatePath: string) {
  const res = await api.get<TemplateDetailResponse>(
    "/ensemble/templates/detail",
    { params: { template_path: templatePath } }
  );
  return res.data;
}

export async function updateTemplateContent(payload: {
  template_path: string;
  yaml_content: string;
  json_content?: string | null;
}) {
  const res = await api.put<UploadTemplateResponse>(
    "/ensemble/templates/detail",
    payload
  );
  return res.data;
}

export async function deleteTemplate(templatePath: string) {
  const res = await api.delete(
    "/ensemble/templates/detail",
    { params: { template_path: templatePath } }
  );
  return res.data;
}
