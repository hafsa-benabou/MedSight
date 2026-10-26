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
