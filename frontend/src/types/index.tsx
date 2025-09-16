// frontend/src/types/index.ts

// ---------- Shared field types ----------
export type FieldType = "text" | "number" | "select" | "boolean";

export interface FormFieldOption {
  value: any;
  label: string;
}

export interface FormField {
  label: string;
  type: FieldType;
  options?: FormFieldOption[];
  default?: any;
  min?: number;
  max?: number;
  step?: number;
  required?: boolean;
  placeholder?: string;
  description?: string;
  category?: string;
  pattern?: string;
}

export interface FormSchema {
  name: string;
  description?: string;
  fields: Record<string, FormField>;
}

// ---------- API responses ----------
export interface UploadTemplateResponse {
  status: "success" | "error";
  yaml_path?: string;
  json_path?: string;
  name?: string;
  size?: number;
  modified_at?: string;
  message?: string;
}

// ---------- Lists for forms/yamls ----------
export interface FormTemplateListItem {
  category: string;
  name: string;
  stem: string;
  path: string; // path of the JSON sidecar
  yaml_path?: string;
  title: string;
  description?: string;
  size: number;
  modified_at: string;
  schema?: FormSchema;
  schema_error?: string;
}

export interface FormTemplatesResponse {
  root: string;
  page: number;
  page_size: number;
  total: number;
  category_totals: Record<string, number>;
  groups: Record<string, FormTemplateListItem[]>;
  items: FormTemplateListItem[];
}

export interface YamlTemplateItem {
  category: string;
  name: string;
  stem: string;
  path: string; // path to YAML
  size: number;
  modified_at: string;
  content?: string;
  content_error?: string;
}

export interface YamlTemplatesResponse {
  root: string;
  page: number;
  page_size: number;
  total: number;
  category_totals: Record<string, number>;
  items: YamlTemplateItem[];
}
