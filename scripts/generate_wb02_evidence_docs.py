"""Generate WB-0.2 evidence markdown docs from contract package."""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

PUB = Path(r"D:\Dstorylens-wt-whole-book-v120-integration")
EV = PUB / "release" / "evidence" / "whole-book" / "WB-0.2"
sys.path.insert(0, str(PUB / "apps" / "api"))

from app.narrative_core.contracts.whole_book_contract_v1 import models as models_mod
from app.narrative_core.contracts.whole_book_contract_v1.constants import (
    PUBLIC_ONLY_MODEL_NAMES_V1,
    WHOLE_BOOK_CONTRACT_VERSION,
    WIRE_MODEL_NAMES_V1,
)
from app.narrative_core.contracts.whole_book_contract_v1.enums import ENUM_NAMES_V1


def main() -> None:
    EV.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PUB / "docs" / "whole-book" / "contracts" / "V1_PERSISTENCE_MAPPING.md",
        EV / "V1_PERSISTENCE_MAPPING.md",
    )

    enums_mod = importlib.import_module(
        "app.narrative_core.contracts.whole_book_contract_v1.enums"
    )
    lines = [f"# Whole-Book Contract V1 Enums\n\nContract: `{WHOLE_BOOK_CONTRACT_VERSION}`\n"]
    for name in ENUM_NAMES_V1:
        cls = getattr(enums_mod, name)
        lines.append(f"## {name}\n")
        for member in cls:
            lines.append(f"- `{member.value}`")
        lines.append("")
    (EV / "ENUMS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    wire = set(WIRE_MODEL_NAMES_V1)
    all_names = list(WIRE_MODEL_NAMES_V1) + list(PUBLIC_ONLY_MODEL_NAMES_V1)
    obj_lines = [
        "# Whole-Book Contract V1 Objects\n",
        f"Contract: `{WHOLE_BOOK_CONTRACT_VERSION}`\n",
        "Migration needs summarized from `V1_PERSISTENCE_MAPPING.md`.\n",
    ]
    for name in all_names:
        cls = getattr(models_mod, name)
        schema = cls.model_json_schema()
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        scope = (
            "Public+Private Wire"
            if name in wire
            else "Public-only (not in wire identity hash)"
        )
        obj_lines.append(f"## {name}\n")
        obj_lines.append("- Function: Wire/persistence DTO for whole-book analysis V1")
        obj_lines.append(f"- Public / Private: {scope}")
        obj_lines.append("- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md")
        obj_lines.append(
            "- Lifecycle: contract-validated object; no DB write in WB-0.2"
        )
        obj_lines.append("- Fields:")
        for fname, fschema in props.items():
            typ = fschema.get("type") or fschema.get("$ref") or fschema.get("anyOf") or "complex"
            nullable = fname not in required
            obj_lines.append(f"  - `{fname}`: type={typ}; nullable={nullable}")
        obj_lines.append("- Validation: pydantic `extra=forbid` + model validators")
        obj_lines.append("")
    (EV / "CONTRACT_OBJECTS.md").write_text("\n".join(obj_lines) + "\n", encoding="utf-8")
    print("ok", EV)


if __name__ == "__main__":
    main()
