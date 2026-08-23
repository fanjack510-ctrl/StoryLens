import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": hooks },
    rules: {
      ...hooks.configs.recommended.rules,
      "@typescript-eslint/no-explicit-any": "off",
      // 全角空格（U+3000）在中文界面文案里是正常排版，不是「异常空白」。
      // 默认规则把它算成错误，于是 127 个 error 里有 74 个是它——门永远红，
      // 就等于没有门：真正的问题（未使用变量、hooks 规则违规）淹在里面没人看。
      //
      // 只在字符串和模板里允许；代码本身出现全角空格仍然报错，那确实是打错了。
      "no-irregular-whitespace": [
        "error",
        { skipStrings: true, skipTemplates: true, skipJSXText: true, skipComments: true },
      ],
      // 下划线开头＝有意不用（保留签名、解构丢弃）。不加这条，
      // 「我知道它没用到」和「我忘了用」在报错里长得一模一样。
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
        },
      ],
    },
  },
);
