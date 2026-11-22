"""Write the API's OpenAPI schema to web/openapi.json (the web app's types are generated from it).

uv run python -m getpaid.export_openapi
"""

import json
from pathlib import Path

from getpaid.agent.drafter import TemplateDrafter
from getpaid.data.source import FixtureSource
from getpaid.db import make_engine
from getpaid.domain import Policy
from getpaid.main import create_app

OUT = Path(__file__).resolve().parents[3] / "web" / "openapi.json"


def schema() -> dict[str, object]:
    app = create_app(
        engine=make_engine("sqlite://"),
        source=FixtureSource(),
        drafter=TemplateDrafter(),
        policy=Policy(),
    )
    return app.openapi()


def main() -> None:  # pragma: no cover - CLI
    OUT.write_text(json.dumps(schema(), indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":  # pragma: no cover
    main()
