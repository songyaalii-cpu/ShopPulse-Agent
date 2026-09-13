import type {ChartContract} from "../types";
import Chart from "./Chart";

type Answer = Record<string, unknown>;

const asList = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const asObject = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const number = (value: unknown): number | undefined => typeof value === "number" && Number.isFinite(value) ? value : undefined;
const money = (value: number) => new Intl.NumberFormat("zh-CN", {style:"currency", currency:"CNY", maximumFractionDigits:0}).format(value);
const percent = (value: number) => new Intl.NumberFormat("zh-CN", {style:"percent", maximumFractionDigits:1}).format(value);

function warningText(value: unknown) {
  const text = String(value);
  if (text.includes("AuthenticationError")) return "DeepSeek 身份认证失败，本次已回退到规则分析。请检查 API Key 是否有效、账户是否可用。";
  if (text.includes("model parser unavailable")) return "大模型未能解析问题，本次使用规则识别。";
  if (text.includes("model writer unavailable")) return "大模型未能生成经营解读，本次展示确定性分析结果。";
  return text;
}

function latestKpis(answer: Answer) {
  const trend = asList(answer.trend).map(asObject);
  const latest = trend.at(-1);
  const previous = trend.at(-2);
  if (!latest) return [];
  const specs = [
    ["GMV", "gmv", "money"], ["订单量", "order_count", "number"],
    ["客单价", "average_order_value", "money"], ["退款率", "refund_rate", "percent"],
  ] as const;
  return specs.flatMap(([label,key,kind]) => {
    const value = number(latest[key]);
    if (value === undefined) return [];
    const prior = previous ? number(previous[key]) : undefined;
    const change = prior && prior !== 0 ? (value - prior) / Math.abs(prior) : undefined;
    const formatted = kind === "money" ? money(value) : kind === "percent" ? percent(value) : value.toLocaleString("zh-CN");
    return [{label, value:formatted, change}];
  });
}

function InsightList({title,items}:{title:string;items:unknown[]}) {
  if (!items.length) return null;
  return <section><h3>{title}</h3><ul className="insight-list">{items.map((item,index)=><li key={index}>{typeof item === "string" ? item : JSON.stringify(item, null, 2)}</li>)}</ul></section>;
}

export default function AnswerView({answer,charts}:{answer:Answer;charts:ChartContract[]}) {
  const summary = String(answer.summary || "分析已完成，但没有生成文字结论。");
  const period = asObject(answer.period);
  const kpis = latestKpis(answer);
  const warnings = [...new Set(asList(answer.warnings).map(warningText))];
  return <>
    {warnings.length > 0 && <section className="warning-panel"><h3>本次分析提示</h3>{warnings.map((item,index)=><p key={index}>{item}</p>)}</section>}
    <section className="answer-panel">
      <div className="answer-heading"><h3>分析结论</h3>{Boolean(period.start && period.end) && <span>{String(period.start)} 至 {String(period.end)}</span>}</div>
      <p className="answer-summary">{summary}</p>
    </section>
    {kpis.length > 0 && <section><h3>最新一期关键指标</h3><div className="kpi-grid">{kpis.map(item=><div className="kpi-card" key={item.label}><span>{item.label}</span><strong>{item.value}</strong>{item.change !== undefined && <small className={item.change >= 0 ? "up" : "down"}>较上期 {item.change >= 0 ? "+" : ""}{percent(item.change)}</small>}</div>)}</div></section>}
    {charts.map(chart=><section className="chart-panel" key={chart.chart_id}><Chart chart={chart}/></section>)}
    <InsightList title="经营建议" items={asList(answer.recommendations)}/>
    <InsightList title="分析证据" items={asList(answer.evidence)}/>
    <InsightList title="分析局限" items={asList(answer.limitations)}/>
  </>;
}
