"use client";
import {useEffect,useReducer,useState} from "react"; import {api,eventUrl} from "../lib/api"; import {reduceEvent} from "../lib/events"; import type {Run,RunEvent} from "../types"; import AnswerView from "./AnswerView";

const terminal = ["completed","failed","cancelled"];
const statusLabel:Record<string,string> = {queued:"排队中",running:"分析中",completed:"已完成",failed:"失败",cancelled:"已取消"};

export default function RunView({initial}:{initial:Run}) {
  const [run,setRun]=useState(initial);
  const [stream,dispatch]=useReducer(reduceEvent,{events:[],status:initial.status});
  useEffect(()=>{
    if(terminal.includes(run.status)) return;
    const source=new EventSource(eventUrl(run.run_id));
    const handler=(raw:MessageEvent)=>{
      const event=JSON.parse(raw.data) as RunEvent;
      dispatch(event);
      if(["run.completed","run.failed","run.cancelled"].includes(event.event_type)) {
        source.close();
        api<Run>(`/api/v1/runs/${run.run_id}`).then(setRun).catch(error=>dispatch({event_id:"refresh-error",run_id:run.run_id,sequence:Number.MAX_SAFE_INTEGER,event_type:"run.failed",timestamp:new Date().toISOString(),payload:{message:String(error)}}));
      }
    };
    ["run.queued","run.started","graph.node.started","graph.node.completed","tool.started","tool.completed","analysis.partial","chart.ready","run.completed","run.failed","run.cancelled"].forEach(type=>source.addEventListener(type,handler));
    return()=>source.close();
  },[run.run_id,run.status]);
  const status=run.status === initial.status ? stream.status : run.status;
  const answer=run.result?.answer;
  return <main>
    <div className={`status status-${status}`}>状态：{statusLabel[status] || status}</div>
    <h2>{run.query}</h2>
    {(stream.error||run.error_message)&&<p className="error">{stream.error||run.error_message}</p>}
    {!answer && !terminal.includes(status) && <section className="loading-panel"><h3>正在分析经营数据…</h3><p>完成后会在这里展示结论、指标、建议和图表。</p></section>}
    {answer ? <AnswerView answer={answer} charts={run.result?.charts || []}/> : terminal.includes(status) && <section className="error-panel"><h3>没有生成可展示的分析结果</h3><p>请查看错误信息后重新提交。</p></section>}
    {stream.events.length > 0 && <details className="execution-details"><summary>执行详情（{stream.events.length} 条事件）</summary><div className="timeline">{stream.events.map(e=><div key={e.event_id}>{e.sequence}. {e.event_type} {e.node_name}</div>)}</div></details>}
  </main>;
}
