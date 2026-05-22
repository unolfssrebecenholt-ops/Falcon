import { DEFAULT_PHONE, MASKED_DEFAULT_PHONE, maskPhone } from "./text_cleaner.mjs";

export const LOGIN_STATUS = Object.freeze({
  LOGGED_IN: "logged_in",
  NEEDS_CODE: "needs_code",
  FAILED: "failed",
});

export function loginConfig({ phone = DEFAULT_PHONE, maxRetries = 2 } = {}) {
  return {
    phone,
    maskedPhone: maskPhone(phone),
    maxRetries,
    codeMustRemainTransient: true,
  };
}

export function verificationCodeInstruction({ maskedPhone = MASKED_DEFAULT_PHONE } = {}) {
  return [
    `已触发手机号 ${maskedPhone} 的验证码登录。`,
    "请在当前 Codex 对话里发送验证码；验证码只用于本次浏览器输入，不会写入 CSV、summary、steps 或日志。",
  ].join("\n");
}

export function assertCodeIsTransient(code) {
  const text = String(code ?? "").trim();
  if (!/^\d{4,8}$/.test(text)) {
    throw new Error("Verification code must be 4-8 digits and must not be persisted.");
  }
  return text;
}
