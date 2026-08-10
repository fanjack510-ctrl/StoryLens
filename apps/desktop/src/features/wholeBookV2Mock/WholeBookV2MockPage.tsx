import { Link } from "react-router-dom";
import { useState } from "react";
import { buildMockWholeBookAnalysisV2 } from "../wholeBookV2/mockAdapter";
import { WholeBookV2ReportView } from "../wholeBookV2/presentation/WholeBookV2ReportView";
import type { ModuleKey } from "../wholeBookV2/presentation/modules";

export function WholeBookV2MockPage() {
  const [activeModule, setActiveModule] = useState<ModuleKey>("overview");
  const data = buildMockWholeBookAnalysisV2();

  return (
    <div data-testid="whole-book-v2-mock">
      <WholeBookV2ReportView
        data={data}
        activeModule={activeModule}
        onModuleChange={setActiveModule}
        mode="mock"
        headerExtra={
          <Link to="/dev/whole-book-v2-mock/progress">查看分析进度</Link>
        }
      />
    </div>
  );
}
