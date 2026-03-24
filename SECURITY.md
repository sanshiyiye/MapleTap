# Security notes

## Credentials

- Put real keys only in **`.env.local`** (or your process environment). This file is **gitignored**.
- **`.env.example`** is a template with placeholders only — safe to commit.
- Also ignore generic **`.env`** if you use that name locally.

## What was verified (this repo)

- `git check-ignore -v .env.local` → ignored by `.gitignore`.
- `.env.local` is **not** in the index (`git ls-files` empty).
- `git grep` on `HEAD` found no committed strings matching live `sk-…` API key patterns; only code that prints `OPENAI_API_KEY={'set'|'missing'}`.

If you ever **force-added** secrets or pushed before adding ignore rules, rotate the exposed keys at your provider and consider `git filter-repo` / support-assisted history rewrite on the remote.

## 中文说明

- 真实密钥只放在 **`.env.local`** 或环境变量中；该文件已列入 **`.gitignore`**，不应提交。
- **`.env.example`** 仅为占位模板，可安全提交。
- 若曾误提交密钥：立即在服务商控制台**作废并轮换**密钥，必要时清理 Git 历史并强制同步远程（需团队配合）。
