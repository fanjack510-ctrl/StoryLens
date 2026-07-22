/** Open an https URL outside the app (new browser tab / OS handler). */
export async function openExternalUrl(url: string): Promise<{ ok: boolean; message?: string }> {
  const trimmed = url.trim();
  if (!trimmed) {
    return { ok: false, message: "购买链接尚未配置，请联系发行方完成爱发电商品地址设置。" };
  }
  if (!/^https:\/\//i.test(trimmed)) {
    return { ok: false, message: "购买链接无效。" };
  }
  try {
    window.open(trimmed, "_blank", "noopener,noreferrer");
    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "无法打开外部链接",
    };
  }
}
