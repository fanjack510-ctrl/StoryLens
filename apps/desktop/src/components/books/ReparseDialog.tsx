import { useRef, useState } from "react";
import { booksApi } from "../../services/booksApi";
import { ErrorState, Loading } from "../common/States";

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
  const apply = async (strategy: string) => {
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
      <div className="modal">
        <header>
          <h2>重新识别章节</h2>
          <button onClick={onClose}>×</button>
        </header>
        <input
          ref={input}
          hidden
          type="file"
          accept=".txt,.docx,.epub"
          data-testid="reparse-file-input"
          onChange={(event) => choose(event.target.files?.[0])}
        />
        <button onClick={() => input.current?.click()} data-testid="reparse-choose-file">
          选择原文件
        </button>
        {busy && <Loading />}
      {failure && <ErrorState error={failure as Error} />}
        {preview && (
          <div className="import-preview" data-testid="reparse-preview">
            <p className={preview.hash_match ? "success" : "notice"}>
              {preview.hash_match
                ? "文件Hash一致"
                : "文件Hash不同：建议创建修订版"}
            </p>
            <p>
              原结构：{preview.old_chapter_count}项 /{" "}
              {preview.old_paragraph_count}段
            </p>
            <p>
              新结构：{preview.formal_chapter_count}个正式章节 /{" "}
              {preview.front_matter_count}个前置内容 /{" "}
              {preview.new_paragraph_count}段
            </p>
            <h3>前20项</h3>
            <ol>
              {preview.chapter_titles.map((title: string) => (
                <li key={title}>{title}</li>
              ))}
            </ol>
            <h3>中部抽样</h3>
            <p>{preview.middle_sample_titles.join(" · ")}</p>
            <h3>末尾抽样</h3>
            <p>{preview.ending_sample_titles.join(" · ")}</p>
            <footer>
              <button onClick={onClose}>取消</button>
              <button
                disabled={preview.has_succeeded_runs}
                data-testid="reparse-replace-in-place"
                onClick={() => apply("replace_in_place")}
              >
                替换当前结构
              </button>
              <button
                className="primary"
                data-testid="reparse-create-revision"
                onClick={() => apply("create_revision")}
              >
                创建修订版
              </button>
            </footer>
          </div>
        )}
      </div>
    </div>
  );
}
