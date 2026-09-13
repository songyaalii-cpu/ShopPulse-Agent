export const STATUS_LABELS:Record<string,string>={queued:"排队中",running:"分析中",completed:"已完成",failed:"失败",cancelled:"已取消"};
export const INTENT_LABELS:Record<string,string>={trend:"趋势分析",rfm:"客户分群",cohort:"留存分析",funnel:"转化漏斗",attribution:"异常归因",weekly_report:"经营周报",inventory:"库存预警",association:"商品关联"};
export const statusLabel=(value:string)=>STATUS_LABELS[value]||value;
export const intentLabel=(value?:string|null)=>value?INTENT_LABELS[value]||value:"待识别";
export const formatDate=(value?:string|null)=>value?new Intl.DateTimeFormat("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value)):"-";
