import {api} from "../../../lib/api";import RunView from "../../../components/RunView";
export default async function RunPage({params}:{params:Promise<{runId:string}>}){const {runId}=await params;const run:any=await api(`/api/v1/runs/${runId}`);return <RunView initial={run}/>}
