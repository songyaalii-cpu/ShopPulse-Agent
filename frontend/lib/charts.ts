import type { ChartContract } from "../types";

const METRIC_LABELS: Record<string,string> = {
  gmv: "商品交易总额",
  order_count: "订单量",
  average_order_value: "客单价",
  refund_rate: "退款率",
  paid_amount: "实付金额",
  net_sales: "净销售额",
  refund_amount: "退款金额",
  gross_profit: "毛利",
  gross_margin: "毛利率",
  payment_conversion_rate: "支付转化率",
  customer_count: "客户数",
  revenue: "销售收入",
  view: "浏览",
  click: "点击",
  add_to_cart: "加购",
  checkout: "提交订单",
  purchase: "支付",
};

export const metricLabel = (name: string) => METRIC_LABELS[name.toLowerCase()] || name;

const axisValue = (unit:string) => (value:number) => unit === "percent"
  ? `${(value * 100).toFixed(1)}%`
  : new Intl.NumberFormat("zh-CN", {notation:"compact", maximumFractionDigits:1}).format(value);
const tooltipValue = (unit:string) => (value:unknown) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value ?? "-");
  if (unit === "percent") return new Intl.NumberFormat("zh-CN", {style:"percent", maximumFractionDigits:2}).format(numeric);
  if (unit === "currency") return new Intl.NumberFormat("zh-CN", {style:"currency", currency:"CNY", maximumFractionDigits:2}).format(numeric);
  return numeric.toLocaleString("zh-CN");
};

export function splitMetricChart(chart: ChartContract): ChartContract[] {
  if (chart.chart_type !== "line" || (chart.series?.length || 0) <= 1) return [chart];
  return (chart.series || []).map(series=>({...chart,
    chart_id:`${chart.chart_id}-${series.name}`, title:metricLabel(series.name), series:[series],
  }));
}

export function toEChartsOption(chart: ChartContract) {
  const base = { title:{text:chart.title}, tooltip:{trigger:"axis"}, legend:{}, aria:{enabled:true, description:chart.title} };
  if (chart.chart_type === "line" || chart.chart_type === "bar") {
    const sourceSeries = chart.series || [];
    const primaryUnit = sourceSeries[0]?.unit || "number";
    return {...base,
      xAxis:{type:"category", data:chart.x_axis || chart.categories || []},
      yAxis:{type:"value",scale:true,axisLabel:{formatter:axisValue(primaryUnit)}},
      series:sourceSeries.map(series=>({name:metricLabel(series.name),type:chart.chart_type,
        data:series.data,connectNulls:false,tooltip:{valueFormatter:tooltipValue(series.unit)}}))};
  }
  if (chart.chart_type === "funnel") return {...base, series:[{type:"funnel", data:(chart.series?.[0]?.data || []).map(item=>{
    if (item && typeof item === "object" && "name" in item) return {...item, name:metricLabel(String(item.name))};
    return item;
  })}]};
  if (chart.chart_type === "heatmap") {
    const rows = chart.rows || []; const data: [number,number,number|null][] = [];
    rows.forEach((row,y)=>(chart.x_axis || []).forEach((key,x)=>data.push([x,y,row[key] == null ? null : Number(row[key])])));
    return {...base, xAxis:{type:"category",data:chart.x_axis}, yAxis:{type:"category",data:rows.map(r=>String(r.cohort || ""))},
      visualMap:{min:0,max:1}, series:[{type:"heatmap",data}]};
  }
  return base;
}
