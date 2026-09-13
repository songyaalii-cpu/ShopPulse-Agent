import "./globals.css"; import Nav from "../components/Nav";
export const metadata={title:"ShopPulse",description:"基于 LangGraph 的电商经营分析与决策 Agent"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body><Nav/>{children}</body></html>}
