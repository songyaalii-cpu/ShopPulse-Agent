import type { RunEvent } from "../types";
export type StreamState = { events: RunEvent[]; status: string; error?: string };
export function reduceEvent(state: StreamState, event: RunEvent): StreamState {
  if (state.events.some(x=>x.event_id===event.event_id)) return state;
  const status = event.event_type.startsWith("run.") ? event.event_type.slice(4) : state.status;
  return {events:[...state.events,event].sort((a,b)=>a.sequence-b.sequence), status,
    error:event.event_type==="run.failed" ? String(event.payload.message || "分析失败") : state.error};
}
