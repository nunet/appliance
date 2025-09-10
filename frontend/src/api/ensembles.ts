// frontend/src/api/ensembles.ts
import axios from "axios";
import {
  UploadTemplateResponse,
  FormSchema,
  FormTemplatesResponse,
  YamlTemplatesResponse,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_URL;

// ------- Lists --------
export async function listFormTemplates(page = 1, pageSize = 10) {
  const res = await axios.get<FormTemplatesResponse>(
    `${API_BASE}/ensemble/templates/forms`,
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
  const res = await axios.get<YamlTemplatesResponse>(
    `${API_BASE}/ensemble/templates/yamls`,
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
  // - generate_json [optional: "true"/"false"]  -- we’ll always send true
  // - hints_json [optional]                     -- we’ll omit by default
  const res = await axios.post<UploadTemplateResponse>(
    `${API_BASE}/ensemble/templates/upload`,
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
  const res = await axios.get<FormSchema>(
    `${API_BASE}/ensemble/templates/schema`,
    { params: { template_path: templatePath, source } }
  );
  return res.data;
}
