/**
 * Legacy overview panels retained for non-primary reuse / tests.
 * Phase 1C-C.2.6 removed top-level 曲线总览｜问题簇｜章节诊断 tabs;
 * question-cluster and diagnosis data remain in Context Inspector + summary.
 */
import type { ReactNode } from "react";
import type {
  JourneyQuestionChain,
  JourneyQuestionCluster,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { lifecycleLabelZh } from "./journeyUiLabels";

const LIFECYCLE_BRIEF: Record<string, string> = {
  created: "创建",
  carried: "承接",
  partially_answered: "部分回答",
  transformed: "转化",
  answered: "回答",
  dropped: "丢弃",
  open: "开放",
  deferred: "延后",
  created_here: "创建",
  carried_from_previous: "承接",
};

function lifecycleBrief(chain: JourneyQuestionChain): string {
  return chain.lifecycle
    .slice(0, 6)
    .map(
      (entry) =>
        `S${entry.scene_ordinal}${LIFECYCLE_BRIEF[entry.status] ?? lifecycleLabelZh(entry.status)}`,
    )
    .join(" → ");
}

type QuestionsProps = {
  visualization: ReaderJourneyVisualization;
  nodes: JourneySceneNode[];
  expandedClusterId: string | null;
  expandedSecondary: boolean;
  onToggleCluster: (clusterId: string) => void;
  onToggleSecondary: () => void;
  onSelectScene: (node: JourneySceneNode) => void;
};

/** Not mounted as a top-level overview; data remains available via Inspector. */
export function JourneyQuestionsOverview({
  visualization,
  nodes,
  expandedClusterId,
  expandedSecondary,
  onToggleCluster,
  onToggleSecondary,
  onSelectScene,
}: QuestionsProps) {
  const clusters = visualization.visible_question_clusters?.length
    ? visualization.visible_question_clusters
    : null;
  const primary = clusters?.[0];
  const phaseClusters = (clusters ?? []).slice(1, 5);

  return (
    <div className="journey-overview-questions" data-testid="journey-overview-questions">
      <section className="journey-question-chains" data-testid="journey-question-chains">
        {clusters ? (
          <>
            {primary && (
              <ClusterCard
                cluster={primary}
                primary
                expanded={expandedClusterId === primary.cluster_id}
                nodes={nodes}
                onToggle={() => onToggleCluster(primary.cluster_id)}
                onSelectScene={onSelectScene}
              />
            )}
            {phaseClusters.map((cluster) => (
              <ClusterCard
                key={cluster.cluster_id}
                cluster={cluster}
                expanded={expandedClusterId === cluster.cluster_id}
                nodes={nodes}
                onToggle={() => onToggleCluster(cluster.cluster_id)}
                onSelectScene={onSelectScene}
              />
            ))}
          </>
        ) : (
          <>
            {visualization.primary_question_chain && (
              <article className="journey-chain-card primary">
                <b>主问题链</b>
                <p>{visualization.primary_question_chain.canonical_question}</p>
                <small>{lifecycleBrief(visualization.primary_question_chain)}</small>
              </article>
            )}
            {visualization.phase_question_chains.slice(0, 4).map((chain) => (
              <article key={chain.canonical_id} className="journey-chain-card">
                <b>阶段链 · S{chain.created_scene}</b>
                <p>{chain.canonical_question}</p>
                <small>{lifecycleBrief(chain)}</small>
              </article>
            ))}
          </>
        )}
        {!!visualization.secondary_question_chains.length && (
          <button
            type="button"
            data-testid="journey-expand-secondary-chains"
            className="journey-inline-button"
            onClick={onToggleSecondary}
          >
            {expandedSecondary
              ? "收起次要问题簇"
              : `展开次要问题簇（${visualization.secondary_question_chains.length}）`}
          </button>
        )}
        {expandedSecondary &&
          visualization.secondary_question_chains.map((chain) => (
            <article key={chain.canonical_id} className="journey-chain-card secondary">
              <b>次要链 · S{chain.created_scene}</b>
              <p>{chain.canonical_question}</p>
              <small>{lifecycleBrief(chain)}</small>
            </article>
          ))}
      </section>
    </div>
  );
}

function ClusterCard({
  cluster,
  primary,
  expanded,
  nodes,
  onToggle,
  onSelectScene,
}: {
  cluster: JourneyQuestionCluster;
  primary?: boolean;
  expanded: boolean;
  nodes: JourneySceneNode[];
  onToggle: () => void;
  onSelectScene: (node: JourneySceneNode) => void;
}) {
  return (
    <article
      className={`journey-cluster-card ${primary ? "primary" : ""}`}
      data-testid={`journey-cluster-${cluster.cluster_id}`}
    >
      <button
        type="button"
        className="journey-cluster-header"
        data-testid={`journey-cluster-toggle-${cluster.cluster_id}`}
        onClick={onToggle}
      >
        <b>{primary ? "主问题簇" : "阶段问题簇"}</b>
        <p>{cluster.cluster_title}</p>
        <small>
          {cluster.cluster_type} · {cluster.members.length} 链 · S{cluster.created_scene}
        </small>
      </button>
      {expanded && (
        <ul
          className="journey-cluster-members"
          data-testid={`journey-cluster-members-${cluster.cluster_id}`}
        >
          {cluster.members.map((member) => {
            const memberNode = nodes.find((node) => node.scene_ordinal === member.created_scene);
            return (
              <li key={member.chain_id}>
                <button
                  type="button"
                  className="journey-inline-button"
                  data-testid={`journey-lifecycle-scene-${member.created_scene}-${member.chain_id}`}
                  onClick={() => {
                    if (memberNode) onSelectScene(memberNode);
                  }}
                >
                  <span>{lifecycleLabelZh(member.relationship) || member.relationship}</span>
                  {" · "}S{member.created_scene} · {member.question}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}

type DiagnosisProps = {
  summary: ReaderJourneyVisualization["chapter_summary"];
  weakInterval: string;
  children?: ReactNode;
};

/** Not mounted as a top-level overview; summary cards remain on journey analysis. */
export function JourneyDiagnosisOverview({ summary, weakInterval }: DiagnosisProps) {
  return (
    <div className="journey-overview-diagnosis" data-testid="journey-overview-diagnosis">
      <div className="journey-summary-cards" data-testid="journey-summary-cards">
        <article className="journey-summary-card" data-testid="summary-card-traction">
          <span>核心牵引</span>
          <b>{summary.primary_cluster_title ?? summary.primary_traction}</b>
        </article>
        <article className="journey-summary-card" data-testid="summary-card-peak">
          <span>峰值 Scene</span>
          <b>
            Scene {summary.peaks.engagement_peak.scene_ordinal} ·{" "}
            {summary.peaks.engagement_peak.value}
          </b>
        </article>
        <article className="journey-summary-card" data-testid="summary-card-weak">
          <span>最大薄弱区间</span>
          <b>{weakInterval}</b>
        </article>
        <article className="journey-summary-card" data-testid="summary-card-hook">
          <span>章尾钩子</span>
          <b>
            {summary.strongest_hook
              ? summary.strongest_hook.summary || `Scene ${summary.strongest_hook.scene_ordinal}`
              : "—"}
          </b>
        </article>
      </div>

      <dl className="journey-diagnosis-stats" data-testid="journey-diagnosis-stats">
        <div>
          <dt>节奏诊断</dt>
          <dd>{summary.diagnosis}</dd>
        </div>
        <div>
          <dt>回报分布</dt>
          <dd>
            强回报 {summary.stage_payoff_count ?? "—"} · 峰值 S
            {summary.strongest_payoff?.scene_ordinal ?? "—"}
          </dd>
        </div>
        <div>
          <dt>Hook 分布</dt>
          <dd>
            强钩子 {summary.strong_hook_count ?? "—"} · 章尾 S
            {summary.strongest_hook?.scene_ordinal ?? "—"}
          </dd>
        </div>
        <div>
          <dt>风险区间</dt>
          <dd>{weakInterval}</dd>
        </div>
        <div>
          <dt>Scene / Phase</dt>
          <dd>
            {summary.counts.scene_count} / {summary.counts.phase_count}
          </dd>
        </div>
        <div>
          <dt>阅读牵引峰 / 谷</dt>
          <dd>
            S{summary.peaks.engagement_peak.scene_ordinal}(
            {summary.peaks.engagement_peak.value}) / S
            {summary.peaks.engagement_valley.scene_ordinal}(
            {summary.peaks.engagement_valley.value})
          </dd>
        </div>
      </dl>

      <div className="journey-expanded-diagnosis" data-testid="journey-expanded-diagnosis">
        <p className="journey-diagnosis-text">{summary.diagnosis}</p>
        {!!summary.expanded_diagnosis.chapter_strengths?.length && (
          <div>
            <b>章节优势</b>
            <ul>
              {summary.expanded_diagnosis.chapter_strengths.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {!!summary.expanded_diagnosis.chapter_risks?.length && (
          <div>
            <b>章节风险</b>
            <ul>
              {summary.expanded_diagnosis.chapter_risks.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
