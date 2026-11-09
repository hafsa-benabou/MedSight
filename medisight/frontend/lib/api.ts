export type SourceRef = { code: string; name: string; url: string | null; license: string | null } | null;
export type Presentation = { id: number; label: string; ppv: number | null; ph: number | null; price_status: string;
  price_as_of: string | null; ean13: string | null; data_status: string; source: SourceRef };
export type MedicineCard = { id: number; brand: string; dosage: string | null; form: string | null; form_canonical: string | null;
  laboratory: string | null; ingredients: { name: string; strength: string | null }[]; princeps_status: string | null;
  marketing_status: string | null; is_marketed: boolean | null; data_status: string; source: SourceRef;
  min_ppv: number | null; presentations: Presentation[] };
export type SearchResult = { items: MedicineCard[]; total: number; page: number; size: number;
  meta: { query_normalized: string; dosage_requested: string | null; dosage_found: boolean | null;
    available_dosages: string[]; did_you_mean?: string } };
export type ClinicalSection = { code: string; title: string; content: string; source: SourceRef; source_url: string | null;
  document_date: string | null; data_status: string };
export type Reimbursement = { presentation_id: number | null; base: number | null; rate: number | null; valid_as_of: string | null;
  ppv_reference: number | null; data_status: string; source: SourceRef };
export type MedicineDetail = MedicineCard & { amm_status: string | null; atc_code: string | null; rcp_url: string | null;
  therapeutic_class: string | null; reimbursements: Reimbursement[]; clinical_sections: ClinicalSection[] };
export type GenericMember = { type: string; label: string; laboratory: string | null; ean13: string | null;
  medicine_id: number | null; is_current: boolean };
export type Generics = { medicine: MedicineCard; note: string; pharmacological: (MedicineCard & { same_form: boolean })[];
  regulatory: { group: string; route: string | null; edition: string | null; data_status: string; source: SourceRef; members: GenericMember[] }[] };
export type DataSourceInfo = { code: string; name: string; publisher: string | null; url: string | null; license: string | null;
  is_official: boolean; default_data_status: string; notes: string | null;
  last_import: { finished_at: string | null; method: string; version_date: string | null; rows: number } | null };
export type Pharmacy = { id: number; name: string; address: string | null; city: string | null; district: string | null;
  latitude: number | null; longitude: number | null; phone: string | null; opening_hours: string | null;
  in_ammps_registry: boolean | null; data_status: string; source: SourceRef; distance_km?: number | null;
  availability?: { kind: "verified" | "simulated" | "unverified"; status?: string; label?: string; observed_at?: string } };
export type PharmacySearch = { city: string | null; items: Pharmacy[]; total: number; stock_notice: string };
export type DutyShift = { pharmacy_name: string; city: string; district: string | null; address: string | null; phone: string | null;
  shift_type: string; starts_at: string; ends_at: string; data_status: string; source: SourceRef; source_url: string | null };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const DOWN = "L'API MEDISIGHT ne répond pas. Vérifiez que le backend est lancé (uvicorn sur le port 8000), puis réessayez.";

export async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, DOWN);
  }
  if (!res.ok) {
    let message = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      message = body?.error?.message ?? body?.detail ?? message;
    } catch {
      if (res.status >= 500) message = DOWN;
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: { Accept: "application/json", ...(init.headers ?? {}) } });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, DOWN);
  }
  if (!res.ok) {
    let message = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      message = body?.error?.message ?? (typeof body?.detail === "string" ? body.detail : message);
    } catch {
      if (res.status >= 500) message = DOWN;
    }
    if (res.status === 429) message = "Trop de requêtes : patientez une minute avant de réessayer.";
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return send<T>(path, { method: "POST", body: JSON.stringify(body), signal, headers: { "Content-Type": "application/json" } });
}

export function postFile<T>(path: string, file: Blob, name: string, signal?: AbortSignal): Promise<T> {
  const form = new FormData();
  form.append("file", file, name);
  return send<T>(path, { method: "POST", body: form, signal });
}

// --- Pill Identifier (POST /api/pills/identify) ---
export type IdentifyStatus = "identified" | "ambiguous" | "contradictory" | "not_found" | "unreadable" | "ocr_unavailable";
export type Evidence = { barcode: string; brand_similarity: number; dosage: string; substance: string; form: string; pack: string;
  laboratory?: string };
/** Lecture prudente calculée par le backend d'après la nature des indices (pas d'après le seul score). */
export type IdentifyVerdict = "confirmed" | "partial" | "failed";
export type PillCandidate = { rank: number; score: number; medicine_id: number; presentation_id: number; brand: string;
  dosage: string | null; form: string | null; presentation: string; ean13: string | null; ppv: number | null;
  price_as_of: string | null; ingredients: { name: string; strength: string | null }[]; laboratory: string | null;
  data_status: string; source: SourceRef; medicine_source: SourceRef; evidence: Evidence; found_by: string[]; explanation: string[] };
export type IdentifyResponse = { identification_id: string | null; status: IdentifyStatus; verdict?: IdentifyVerdict; message: string; reliability: string;
  identified_level: string | null; score_note: string; reasons: string[]; warnings: string[];
  barcodes: { code: string | null; format: string; status: string; reader: string; in_catalog: boolean; expiry?: string; lot?: string }[];
  extracted: { brand_segments: string[]; dosage_text: string | null; doses: { text: string }[]; substances: { name: string }[];
    form: string | null; form_text?: string | null; pack_text: string | null; pack_quantity?: number | null; laboratory: string | null };
  candidates: PillCandidate[]; available_dosages: string[];
  ocr: { engine: string | null; available: boolean; languages: string | null; version: string | null; variant: string | null;
    rotation: number; mean_confidence: number | null; lines: { text: string; confidence: number }[] };
  quality: { usable: boolean; issues: string[]; [k: string]: unknown }; timings_ms: Record<string, number>; disclaimer: string };

// --- Chatbot (POST /api/chat) ---
export type ChatSource = { code: string; name: string; url: string | null; license: string | null; data_status: string };
export type ChatResponse = { conversation_id: string; message: string;
  language: { code: string; script: string; reply_language: "fr" | "ar" | "darija"; confidence: number };
  intent: { name: string; resolved: string; confidence: number; matched: string[] };
  entities: { medicines: { text: string; brand: string; score: number; method: string }[];
    ingredients: { text: string; name: string }[]; dose: { text: string; value: number; unit: string | null } | null; city: string | null };
  understanding: string; medicines: MedicineCard[]; pharmacies: Pharmacy[]; sources: ChatSource[]; warnings: string[];
  context_medicine: MedicineCard | null; suggestions: string[]; contains_simulated_data: boolean; generation: string; disclaimer: string };
