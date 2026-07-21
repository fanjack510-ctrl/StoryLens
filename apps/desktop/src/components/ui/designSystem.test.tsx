import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { Input } from "./Input";
import { UiBadge } from "./Badge";
import { Dialog } from "./Dialog";
import { StateView } from "./StateView";
import { Checkbox } from "./Checkbox";

const stylesDir = resolve(__dirname, "../../styles");
const tokensCss = readFileSync(resolve(stylesDir, "tokens.css"), "utf8");
const baseCss = readFileSync(resolve(stylesDir, "base.css"), "utf8");

afterEach(cleanup);

describe("design system Button", () => {
  it("applies variant class for primary/secondary/ghost/danger", () => {
    const { rerender } = render(<Button variant="primary">确定</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("data-variant", "primary");
    expect(screen.getByRole("button").className).toMatch(/sl-btn--primary/);
    expect(screen.getByRole("button").className).toMatch(/\bprimary\b/);

    rerender(<Button variant="secondary">取消</Button>);
    expect(screen.getByRole("button").className).toMatch(/sl-btn--secondary/);

    rerender(<Button variant="ghost">更多</Button>);
    expect(screen.getByRole("button").className).toMatch(/sl-btn--ghost/);

    rerender(<Button variant="danger">删除</Button>);
    expect(screen.getByRole("button").className).toMatch(/sl-btn--danger/);
  });

  it("disables interaction when disabled", () => {
    const onClick = vi.fn();
    render(
      <Button variant="primary" disabled onClick={onClick}>
        保存
      </Button>,
    );
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("design system Input", () => {
  it("marks error state for invalid fields", () => {
    render(<Input error aria-label="API Key" defaultValue="" />);
    const input = screen.getByLabelText("API Key");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.className).toMatch(/sl-input--error/);
  });
});

describe("design system Badge", () => {
  it("exposes semantic tone variants", () => {
    render(
      <>
        <UiBadge tone="success">成功</UiBadge>
        <UiBadge tone="warning">警告</UiBadge>
        <UiBadge tone="danger">失败</UiBadge>
        <UiBadge tone="neutral" mono>
          aliyun_qwen_plus
        </UiBadge>
      </>,
    );
    expect(screen.getByText("成功")).toHaveAttribute("data-tone", "success");
    expect(screen.getByText("警告")).toHaveAttribute("data-tone", "warning");
    expect(screen.getByText("失败")).toHaveAttribute("data-tone", "danger");
    expect(screen.getByText("aliyun_qwen_plus").className).toMatch(/mono/);
  });
});

describe("design system Dialog", () => {
  it("renders dialog role and aria-modal", () => {
    render(
      <Dialog title="确认" onClose={() => undefined} data-testid="sample-dialog">
        <p>内容</p>
      </Dialog>,
    );
    const dialog = screen.getByTestId("sample-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("dialog")).toBe(dialog);
  });
});

describe("design system focus and theme tokens", () => {
  it("defines focus-visible rules with accessible fallback", () => {
    expect(baseCss).toMatch(/:focus-visible/);
    expect(baseCss).toMatch(/:focus:not\(:focus-visible\)/);
    expect(baseCss).toMatch(/outline:\s*2px\s+solid\s+var\(--color-brand\)/);
  });

  it("defines dark theme color tokens", () => {
    expect(tokensCss).toMatch(/\[data-theme="dark"\]/);
    expect(tokensCss).toMatch(/--color-bg-app:\s*#111713/);
    expect(tokensCss).toMatch(/--color-bg-surface:\s*#18211d/);
    expect(tokensCss).toMatch(/--color-brand:\s*#69a98e/);
    expect(tokensCss).toMatch(/--font-ui:/);
    expect(tokensCss).toMatch(/--font-reading:/);
  });

  it("keeps reading font on prose and does not force UI font onto novel body", () => {
    expect(baseCss).toMatch(/\.prose[\s\S]*?font-family:\s*var\(--font-reading\)/);
    expect(baseCss).toMatch(/body\s*\{[\s\S]*?font-family:\s*var\(--font-ui\)/);
    const proseBlock = baseCss.match(/\.prose,\s*\n\.reader \.prose[\s\S]*?\{[^}]+\}/);
    expect(proseBlock?.[0] || "").not.toMatch(/--font-ui/);
  });
});

describe("design system StateView", () => {
  it("fires original action callbacks", () => {
    const primary = vi.fn();
    const secondary = vi.fn();
    render(
      <StateView
        kind="error"
        title="无法读取"
        description="网络错误"
        primaryAction={{ label: "重试", onClick: primary, testId: "sv-retry" }}
        secondaryAction={{ label: "返回", onClick: secondary, testId: "sv-back" }}
      />,
    );
    fireEvent.click(screen.getByTestId("sv-retry"));
    fireEvent.click(screen.getByTestId("sv-back"));
    expect(primary).toHaveBeenCalledTimes(1);
    expect(secondary).toHaveBeenCalledTimes(1);
  });
});

describe("design system consent checkbox", () => {
  it("toggles checked state when label is clicked", () => {
    const onChange = vi.fn();
    render(
      <Checkbox
        label="我同意将章节文本发送至云端模型"
        checked={false}
        onChange={onChange}
        data-testid="consent-box"
      />,
    );
    fireEvent.click(screen.getByText("我同意将章节文本发送至云端模型"));
    expect(onChange).toHaveBeenCalled();
  });
});
