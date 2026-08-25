import { useState, type AnchorHTMLAttributes, type ReactNode } from "react";
import { openExternalUrl } from "../../services/openExternalUrl";

type ExternalUrlLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  url: string;
  children: ReactNode;
};

/** HTTPS-only external link that works in both Tauri and an ordinary browser. */
export function ExternalUrlLink({ url, children, onClick, ...props }: ExternalUrlLinkProps) {
  const [error, setError] = useState("");

  return (
    <>
      <a
        {...props}
        href={url}
        onClick={(event) => {
          onClick?.(event);
          if (event.defaultPrevented) return;
          event.preventDefault();
          setError("");
          void openExternalUrl(url).then((result) => {
            if (!result.ok) setError(result.message || "未能打开外部页面，请稍后重试。");
          });
        }}
      >
        {children}
      </a>
      {error ? <small role="alert">{error}</small> : null}
    </>
  );
}
