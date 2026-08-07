from pathlib import Path


def test_glama_dockerfile_contains_package_readme_and_current_tool_count():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.glama"
    contents = dockerfile.read_text(encoding="utf-8")

    assert "COPY README.md /app/README.md" in contents
    assert contents.index("COPY README.md") < contents.index("pip install")
    assert "36 tools" in contents
    assert "35 tools" not in contents
