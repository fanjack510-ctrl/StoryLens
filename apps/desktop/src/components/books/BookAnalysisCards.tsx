import { Link } from "react-router-dom";

/** 当前阅读页的分析决策区。
 *
 * 小说导入后的顺序是：先确认作品画像，再选择分析范围。单章分析和全书分析是两种平级
 * 范围；评测/拆文仍然只在全书分析页内选择，不与单章分析混成三个功能。
 */
export type ChapterAction = {
  label: string;
  disabled: boolean;
  hint?: string;
  testId?: string;
  onClick: () => void;
};

export function BookAnalysisCards({
  bookId,
  isReference,
  isShortForm,
  chapterAction,
  profileUnconfirmed,
  profilePending,
  profileHref,
  chapterTitle,
  chapterCount,
}: {
  bookId: number;
  isReference: boolean;
  isShortForm: boolean;
  chapterAction: ChapterAction | null;
  profileUnconfirmed: boolean;
  profilePending?: boolean;
  profileHref: string;
  chapterTitle?: string;
  chapterCount?: number;
}) {
  if (isReference) {
    return (
      <section className="book-analysis book-analysis--whole-only" data-testid="book-analysis-cards">
        <div className="book-analysis-primary">
          <div>
            <span className="book-analysis-kicker">整本工具书</span>
            <h2>读懂这本书</h2>
            <p>逐节整理主张、依据、术语和可以照做的动作。</p>
          </div>
          <Link
            className="primary"
            to={`/books/${bookId}/whole-book?mode=comprehend`}
            data-testid="ba-go-comprehend"
          >
            开始读懂 →
          </Link>
        </div>
      </section>
    );
  }

  if (isShortForm) {
    return (
      <section className="book-analysis book-analysis--whole-only" data-testid="book-analysis-cards">
        <div className="book-analysis-primary">
          <div>
            <span className="book-analysis-kicker">完整短篇</span>
            <h2>精读全文</h2>
            <p>一次读完整篇，查看故事结构、人物、主题和写法。</p>
          </div>
          <Link className="primary" to={`/books/${bookId}/short-form`} data-testid="ba-go-short_form">
            开始精读 →
          </Link>
        </div>
      </section>
    );
  }

  if (profilePending) {
    return (
      <section
        className="book-analysis book-analysis--decision"
        data-testid="book-analysis-cards"
        aria-busy="true"
      >
        <div className="ba-decision-loading" data-testid="book-analysis-profile-loading">
          正在确认作品画像状态…
        </div>
      </section>
    );
  }

  if (profileUnconfirmed) {
    return (
      <section className="book-analysis book-analysis--decision" data-testid="book-analysis-cards">
        <div className="ba-steps" aria-label="分析步骤">
          <div className="ba-step is-current">
            <span>1</span>
            <div>
              <b>确认作品画像</b>
              <small>当前步骤</small>
            </div>
          </div>
          <div className="ba-step">
            <span>2</span>
            <div>
              <b>选择分析范围</b>
              <small>尚未开始</small>
            </div>
          </div>
          <div className="ba-step">
            <span>3</span>
            <div>
              <b>开始分析</b>
              <small>尚未开始</small>
            </div>
          </div>
        </div>
        <div className="ba-gate" data-testid="book-analysis-profile-gate">
          <div>
            <span className="book-analysis-kicker">第一步</span>
            <h2>先确认这本书该按什么标准分析</h2>
            <p>确认作品类型、目标读者、人称和篇幅；确认后再选择分析本章或分析全书。</p>
          </div>
          <Link className="primary" to={profileHref} data-testid="book-analysis-go-profile">
            确认作品画像 →
          </Link>
        </div>
      </section>
    );
  }

  // 进行中、待确认场景和结果页都有自己的唯一主动作，不再常驻新的范围选择。
  if (!chapterAction) return null;

  return (
    <section className="book-analysis book-analysis--decision" data-testid="book-analysis-cards">
      <div className="ba-steps" aria-label="分析步骤">
        <div className="ba-step is-complete">
          <span>✓</span>
          <div>
            <b>作品画像已确认</b>
            <small>可从上方修改</small>
          </div>
        </div>
        <div className="ba-step is-current">
          <span>2</span>
          <div>
            <b>选择分析范围</b>
            <small>当前步骤</small>
          </div>
        </div>
        <div className="ba-step">
          <span>3</span>
          <div>
            <b>开始分析</b>
            <small>等待选择</small>
          </div>
        </div>
      </div>

      <div className="ba-decision-head">
        <div>
          <span className="book-analysis-kicker">第二步</span>
          <h2>这次想分析哪里？</h2>
          <p>两个入口分析范围不同；进入任务后，页面只保留当前流程。</p>
        </div>
      </div>

      <div className="ba-scope-grid" data-testid="book-analysis-scope-choice">
        <article className="ba-scope-card" data-testid="ba-card-chapter">
          <div>
            <span className="book-analysis-kicker">当前章节</span>
            <h3>单章精析</h3>
            <p className="ba-scope-target">{chapterTitle || "当前章节"}</p>
            <p>识别场景并由你调整边界，随后分析剧情、人物、冲突和阅读节奏。</p>
            <div className="ba-scope-tags" aria-label="单章分析内容">
              <span>场景划分</span>
              <span>人物冲突</span>
              <span>阅读节奏</span>
            </div>
          </div>
          <button
            type="button"
            className="ba-scope-action"
            disabled={chapterAction.disabled}
            title={chapterAction.hint}
            data-testid={chapterAction.testId || "ba-go-chapter"}
            onClick={chapterAction.onClick}
          >
            {chapterAction.label}
          </button>
        </article>

        <article className="ba-scope-card" data-testid="book-analysis-whole-entry">
          <div>
            <span className="book-analysis-kicker">
              整本小说{chapterCount ? ` · ${chapterCount} 章` : ""}
            </span>
            <h3>全书分析</h3>
            <p className="ba-scope-target">从完整原文出发</p>
            <p>分析全书结构、人物线和整体节奏；进入后再选择“评测”或“拆文”。</p>
            <div className="ba-scope-tags" aria-label="全书分析内容">
              <span>全书结构</span>
              <span>人物线</span>
              <span>评测 / 拆文</span>
            </div>
          </div>
          <Link
            className="ba-scope-action"
            to={`/books/${bookId}/whole-book`}
            data-testid="ba-go-whole-book"
          >
            进入全书分析
          </Link>
        </article>
      </div>
    </section>
  );
}
