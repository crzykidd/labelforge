export interface LabelEntry {
  id: string;
  display_name: string;
  brother_part: string | null;
  description: string | null;
  category: string | null;
  color_capable: boolean;
  common_use: string[];
  preview_image: string | null;
  dots_printable: [number, number];
  tape_size: [number, number];
  // 1=die-cut, 2=continuous, 3=round, 4=ptouch-continuous
  form_factor: number;
  // models this media is restricted to ([] = works on all)
  restricted_to_models: string[];
  // 1 = two-color media, 0 = mono
  color: number;
  // whether the configured printer can print this media
  supported: boolean;
  // human-readable reason when supported is false
  incompatible_reason: string | null;
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

export interface HistoryItem {
  id: number;
  template_id: string | null;
  is_quick_print: boolean;
  field_values: Record<string, string> | null;
  label_media: string;
  pinned: boolean;
  created_at: string;
  reprint_of: number | null;
  batch_id: string | null;
  preview_url: string | null;
}

export interface HistoryDetail extends HistoryItem {
  payload_json: Record<string, unknown>;
}

export interface ReprintResponse {
  job_id: number;
  status: string;
  reprint_of: number;
}
