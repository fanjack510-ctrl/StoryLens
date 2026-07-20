import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";

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
    <Dialog
      title="发现新版本"
      data-testid="update-available-dialog"
      onClose={onLater}
      className="update-dialog"
      footer={
        <>
          <Button variant="secondary" onClick={onLater}>
            稍后提醒
          </Button>
          <Button variant="primary" onClick={() => void onUpdate()}>
            立即更新
          </Button>
        </>
      }
    >
      <p>
        当前版本：<strong>{currentVersion}</strong>
        <br />
        最新版本：<strong>{latestVersion}</strong>
      </p>
      <div className="update-dialog-body">
        <h3>更新说明</h3>
        <pre>{body}</pre>
      </div>
    </Dialog>
  );
}
