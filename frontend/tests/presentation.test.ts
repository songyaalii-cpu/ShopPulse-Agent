import {describe,expect,it} from "vitest";
import {intentLabel,statusLabel} from "../lib/presentation";

describe("Chinese presentation labels",()=>{
  it("translates run statuses",()=>{
    expect(statusLabel("completed")).toBe("已完成");
    expect(statusLabel("running")).toBe("分析中");
  });

  it("translates analysis intents and preserves unknown values",()=>{
    expect(intentLabel("funnel")).toBe("转化漏斗");
    expect(intentLabel("custom")).toBe("custom");
  });
});
