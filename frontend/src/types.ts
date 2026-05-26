export interface LabelEntry {
  id: string;
  display_name: string;
  brother_part: string | null;
  description: string | null;
  category: string | null;
  color_capable: boolean;
  printer_requirements: string[];
  common_use: string[];
  preview_image: string | null;
  dots_printable: [number, number];
  tape_size: [number, number];
  // 1=die-cut, 2=continuous, 3=round, 4=ptouch-continuous
  form_factor: number;
}

export interface FontInfo {
  name: string;
  path: string;
  family: string;
  style: string;
}

export interface QuickPrintRequest {
  text: string;
  font: string;
  font_size: number;
  alignment: 'left' | 'center' | 'right';
  orientation: 'standard' | 'rotated';
  label_media: string;
  bold: boolean;
  italic: boolean;
}

export interface PrintJobResponse {
  job_id: number;
  status: string;
  preview_url: string | null;
}

export interface BatchJobResult {
  job_id: number;
  status: string;
}

export interface BatchPrintResponse {
  batch_id: string;
  jobs: BatchJobResult[];
  succeeded: number;
  failed: number;
}

export interface FieldSpec {
  name: string;
  type: 'text' | 'number' | 'date' | 'enum';
  required: boolean;
  default: string | null;
  increment: boolean;
  enum_values: string[];
}

export interface Template {
  name: string;
  display_name: string;
  label_media: string;
  canvas_json: Record<string, unknown>;
  field_schema: FieldSpec[];
  created_at?: string;
  updated_at?: string;
}

export interface TemplateCreate {
  name: string;
  display_name?: string;
  label_media: string;
  canvas_json: Record<string, unknown>;
}
