import { Badge } from "../components/common/States";
const cases = [
  ["人物动作描写", "用动作与细节呈现人物决断。"],
  ["环境氛围描写", "空间、感官与情绪的协同。"],
  ["章尾钩子", "悬念与未闭合信息。"],
  ["目标变化", "事件触发人物目标转向。"],
  ["反转", "预期与事实之间的结构落差。"],
  ["信息差", "角色与读者掌握信息的差异。"],
];
export function CasesPage() {
  return (
    <section className="page">
      <div className="page-title">
        <div>
          <p className="eyebrow">写作案例</p>
          <h1>
            案例库 <Badge tone="demo">演示数据</Badge>
          </h1>
          <p>Phase 1C 尚未实现；以下内容只展示未来界面，不写入正式数据库。</p>
        </div>
      </div>
      <div className="case-grid">
        {cases.map(([name, text], i) => (
          <article className="panel" key={name}>
            <span className="case-index">0{i + 1}</span>
            <h2>{name}</h2>
            <p>{text}</p>
            <div className="fake-evidence">
              B0001-C0001-P000{i + 1} <Badge tone="demo">演示</Badge>
            </div>
            <button disabled>检索相似案例（规划中）</button>
          </article>
        ))}
      </div>
    </section>
  );
}
