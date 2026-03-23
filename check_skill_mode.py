from __future__ import annotations

import os

from skill_runtime import load_local_env


def main() -> int:
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL")

    print(f"OPENAI_API_KEY={'set' if api_key else 'missing'}")
    print(f"OPENAI_BASE_URL={base_url or 'missing'}")
    print(f"OPENAI_MODEL={model or 'missing'}")

    if api_key and base_url and model:
        print("skill_mode_ready=true")
        return 0

    print("skill_mode_ready=false")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
