const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const requestBase = () => typeof window === "undefined" ? (process.env.INTERNAL_API_URL || API) : API;
export const CLIENT_ID = process.env.NEXT_PUBLIC_CLIENT_ID || "local-demo";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${requestBase()}${path}`, { cache: "no-store", ...init, headers: {"Content-Type":"application/json", "X-Client-ID":CLIENT_ID, ...(init?.headers || {})} });
  } catch {
    throw new Error("无法连接分析服务，请检查后端是否启动以及前后端端口配置");
  }
  if (!response.ok) { const body = await response.json().catch(()=>({message:"请求失败"})); throw new Error(body.message || `HTTP ${response.status}`); }
  return response.json();
}
export const eventUrl = (runId:string) => `${API}/api/v1/runs/${runId}/events?client_id=${encodeURIComponent(CLIENT_ID)}`;
