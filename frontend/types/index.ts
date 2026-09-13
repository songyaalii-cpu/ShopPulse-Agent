export type Series = { name: string; unit: string; data: unknown[] };
export type ChartContract = { chart_id: string; chart_type: "line"|"bar"|"heatmap"|"funnel"|"table"|"graph"; title: string; x_axis?: string[]; categories?: string[]; series?: Series[]; rows?: Record<string, unknown>[]; metadata: Record<string, unknown> };
export type RunEvent = { event_id: string; run_id: string; sequence: number; event_type: string; timestamp: string; node_name?: string; payload: Record<string, unknown> };
export type Run = { run_id:string; session_id:string; status:string; query:string; result?: {answer?: Record<string,unknown>; charts?: ChartContract[]}|null; error_message?:string; events_url:string };
