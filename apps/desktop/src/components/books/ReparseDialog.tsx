import { useEffect, useRef, useState } from "react";
import { booksApi } from "../../services/booksApi";
import { ErrorState, Loading } from "../common/States";
import { Button } from "../ui/Button";

type Strategy = "replace_in_place" | "create_revision";

export function ReparseDialog({
  bookId,
  onClose,
  onDone,
}: {
  bookId: number;
  onClose: () => void;
  onDone: (id: number) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const [strategy, setStrategy] = useState<Strategy>("replace_in_place");

  useEffect(() => {
    if (preview?.has_succeeded_runs && strategy === "replace_in_place") {
      setStrategy("create_revision");
    }
  }, [preview, strategy]);

  const choose = async (selected?: File) => {
    if (!selected) return;
    setFile(selected);
    setBusy(true);
    setFailure(undefined);
    try {
      setPreview(await booksApi.reparseWithFilePreview(bookId, selected));
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!file || !preview) return;
    if (
      strategy === "replace_in_place" &&
      !confirm("将替换当前章节和段落结构。此操作需要二次确认，是否继续？")
    )
      return;
    setBusy(true);
    try {
      const result = await booksApi.reparseWithFile(
        bookId,
        file,
        strategy,
        !preview.hash_match,
      );
      onDone(result.book_id);
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" data-testid="reparse-dialog">
      <div className="modal reparse-dialog-modal" role="dialog" aria-modal="true">
        <header>
          <h2>重新识别章节</h2>
          <button type="button" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>
        <p className="reparse-dialog-lead">
          StoryLens 将根据当前原文重新识别章节标题和范围。
        </p>
        <input
          ref={input}
          hidden
          type="file"
          accept=".txt,.docx,.epub"
          data-testid="reparse-file-input"
          onChange={(event) => choose(event.target.files?.[0])}
        />
        <Button variant="secondary" onClick={() => input.current?.click()} data-testid="reparse-choose-file">
          选择原文件
        </Button>
        {busy && <Loading />}
        {failure && <ErrorState error={failure as Error} />}
        {preview && (
          <div className="import-preview reparse-preview" data-testid="reparse-preview">
            <div className="reparse-mode-cards" role="radiogroup" aria-label="识别模式">
              <label
                className={`reparse-mode-card ${strategy === "replace_in_place" ? "is-selected" : ""}`}
              >
                <input
                  type="radio"
                  name="reparse-strategy"
                  value="replace_in_place"
                  checked={strategy === "replace_in_place"}
                  disabled={Boolean(preview.has_succeeded_runs)}
                  data-testid="reparse-replace-in-place"
                  onChange={() => setStrategy("replace_in_place")}
                />
                <span>
                  <strong>替换当前章节</strong>
                  <small>保留当前书籍，重新生成章节结构。已有章节识别结果将被替换。</small>
                </span>
              </label>
              <label
                className={`reparse-mode-card ${strategy === "create_revision" ? "is-selected" : ""}`}
              >
                <input
                  type="radio"
                  name="reparse-strategy"
                  value="create_revision"
                  checked={strategy === "create_revision"}
                  data-testid="reparse-create-revision"
                  onChange={() => setStrategy("create_revision")}
                />
                <span>
                  <strong>创建新修订版</strong>
                  <small>保留当前结果，并创建一份新的章节修订版本。</small>
                </span>
              </label>
            </div>

            <div className="reparse-result-grid">
              <section>
                <h3>原始文件</h3>
                <p className={preview.hash_match ? "success" : "notice"}>
                  {preview.hash_match
                    ? "文件Hash一致"
                    : "文件Hash不同：建议创建修订版"}
                </p>
              </section>
              <section>
                <h3>当前章节</h3>
                <p>
                  原结构：{preview.old_chapter_count}项 / {preview.old_paragraph_count}段
                </p>
              </section>
              <section>
                <h3>预计新结构</h3>
                <p>
                  新结构：{preview.formal_chapter_count}个正式章节 /{" "}
                  {preview.front_matter_count}个前置内容 / {preview.new_paragraph_count}段
                </p>
              </section>
              {!preview.hash_match && (
                <section>
                  <h3>识别警告</h3>
                  <p className="notice">源文件与当前书籍 Hash 不一致，请确认后再继续。</p>
                </section>
              )}
            </div>

            <h3>章节预览</h3>
            <ol className="import-chapter-list">
              {preview.chapter_titles.map((title: string, index: number) => (
                <li key={`${index}-${title}`}>
                  <span className="import-chapter-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {title}
                </li>
              ))}
            </ol>
            <h3>中部抽样</h3>
            <p>{preview.middle_sample_titles.join(" · ")}</p>
            <h3>末尾抽样</h3>
            <p>{preview.ending_sample_titles.join(" · ")}</p>

            <footer className="reparse-dialog-footer">
              <Button variant="ghost" onClick={onClose}>
                取消
              </Button>
              <Button
                variant="primary"
                disabled={busy || (strategy === "replace_in_place" && preview.has_succeeded_runs)}
                data-testid="reparse-apply"
                onClick={() => void apply()}
              >
                重新识别章节
              </Button>
            </footer>
          </div>
        )}
      </div>
    </div>
  );
}
