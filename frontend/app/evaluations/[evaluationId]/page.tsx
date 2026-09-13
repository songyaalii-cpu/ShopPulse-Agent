import {api} from "../../../lib/api";
export default async function Evaluation({params}:{params:Promise<{evaluationId:string}>}){const {evaluationId}=await params;const e:any=await api(`/api/v1/evaluations/${evaluationId}`);return <main><h1>评测 {e.status}</h1><pre>{JSON.stringify(e.report,null,2)}</pre></main>}
