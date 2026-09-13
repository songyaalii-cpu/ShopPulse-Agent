"use client";
import * as echarts from "echarts"; import {useEffect,useRef} from "react"; import {splitMetricChart,toEChartsOption} from "../lib/charts"; import type {ChartContract} from "../types";

function ChartCanvas({chart,compact=false}:{chart:ChartContract;compact?:boolean}) { const ref=useRef<HTMLDivElement>(null); useEffect(()=>{if(!ref.current)return; const instance=echarts.init(ref.current); instance.setOption(toEChartsOption(chart)); const resize=()=>instance.resize(); addEventListener("resize",resize); return()=>{removeEventListener("resize",resize);instance.dispose()};},[chart]); return <div ref={ref} role="img" aria-label={chart.title} style={{height:compact?280:360}}/>; }

export default function Chart({chart}:{chart:ChartContract}) {
  if(chart.chart_type==="table") return <section><h3>{chart.title}</h3><pre>{JSON.stringify(chart.rows,null,2)}</pre></section>;
  const panels=splitMetricChart(chart);
  if(panels.length>1) return <div><h3>{chart.title}</h3><div className="metric-chart-grid">{panels.map(panel=><div className="metric-chart" key={panel.chart_id}><ChartCanvas chart={panel} compact/></div>)}</div></div>;
  return <ChartCanvas chart={chart}/>;
}
