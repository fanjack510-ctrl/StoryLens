type Props = {
  currentVersion: string;
  latestVersion: string;
  body: string;
  onLater: () => void;
  onUpdate: () => void | Promise<void>;
};

export function UpdateAvailableDialog({
  currentVersion,
  latestVersion,
  body,
  onLater,
  onUpdate,
}: Props) {
  return (
    <div className="update-dialog-backdrop" data-testid="update-available-dialog" role="dialog">
      <div className="update-dialog">
        <h2>发现新版本</h2>
        <p>
          当前版本：<strong>{currentVersion}</strong>
          <br />
          最新版本：<strong>{latestVersion}</strong>
        </p>
        <div className="update-dialog-body">
          <h3>更新说明</h3>
          <pre>{body}</pre>
        </div>
        <div className="update-dialog-actions">
          <button type="button" onClick={onLater}>
            稍后提醒
          </button>
          <button type="button" className="primary" onClick={() => void onUpdate()}>
            立即更新
          </button>
        </div>
      </div>
    </div>
  );
}
