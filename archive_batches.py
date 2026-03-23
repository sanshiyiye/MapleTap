from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ArchiveResult:
    """Result of one archive run."""

    moved_inputs: list[Path]
    moved_outputs: list[Path]
    archive_dir: Path | None
    kept_batch_stem: str | None
    kept_analysis_stem: str | None
    kept_skill_stem: str | None


def _newest_stem(glob_pattern: str, directory: Path) -> str | None:
    paths = [p for p in directory.glob(glob_pattern) if p.is_file()]
    if not paths:
        return None
    best = max(paths, key=lambda p: p.stat().st_mtime)
    return best.stem


def resolve_keep_stems(
    inputs_dir: Path,
    outputs_dir: Path,
    *,
    explicit_batch_stem: str | None,
) -> tuple[str | None, str | None, str | None]:
    """
    Returns (batch_stem, analysis_stem, skill_stem) to keep in working dirs.

    explicit_batch_stem: e.g. 2026-03-24-010714-rss-batch (no extension).
    """
    if explicit_batch_stem:
        batch_stem = explicit_batch_stem.removesuffix(".md").removesuffix(".json")
        analysis_stem = batch_stem.replace("-rss-batch", "-rss-analysis")
        skill_stem = batch_stem.replace("-rss-batch", "-skill-analysis")
        return batch_stem, analysis_stem, skill_stem

    batch_stem = _newest_stem("*-rss-batch.md", inputs_dir)
    if batch_stem:
        analysis_stem = batch_stem.replace("-rss-batch", "-rss-analysis")
        skill_stem = batch_stem.replace("-rss-batch", "-skill-analysis")
        return batch_stem, analysis_stem, skill_stem

    analysis_stem = _newest_stem("*-rss-analysis.md", outputs_dir)
    if analysis_stem:
        prefix = analysis_stem.replace("-rss-analysis", "")
        skill_stem = f"{prefix}-skill-analysis"
        return None, analysis_stem, skill_stem

    skill_only = _newest_stem("*-skill-analysis.md", outputs_dir)
    if skill_only:
        return None, None, skill_only

    return None, None, None


def run_archive(
    *,
    inputs_dir: Path,
    outputs_dir: Path,
    archive_root: Path,
    keep_batch_stem: str | None = None,
    dry_run: bool = False,
) -> ArchiveResult:
    """
    Move old batch inputs and analysis outputs into archive/<timestamp>/{inputs,outputs}.

    Leaves README.md and feed_scores_report.md in place.
    Keeps newest *-rss-batch (and paired *-rss-analysis / *-skill-analysis) unless
    keep_batch_stem overrides the batch stem to keep.
    """
    inputs_dir = inputs_dir.resolve()
    outputs_dir = outputs_dir.resolve()
    archive_root = archive_root.resolve()
    archive_root.mkdir(parents=True, exist_ok=True)

    keep_batch, keep_analysis, keep_skill = resolve_keep_stems(
        inputs_dir, outputs_dir, explicit_batch_stem=keep_batch_stem
    )

    moved_in: list[Path] = []
    moved_out: list[Path] = []

    keep_output_stems = {s for s in (keep_analysis, keep_skill) if s}

    for path in sorted(inputs_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == "README.md":
            continue
        if path.stem.endswith("-rss-batch") and path.suffix.lower() in {".md", ".json"}:
            if keep_batch and path.stem == keep_batch:
                continue
            moved_in.append(path)

    protected_names = {"README.md", "feed_scores_report.md"}
    for path in sorted(outputs_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name in protected_names:
            continue
        stem = path.stem
        if not (stem.endswith("-rss-analysis") or stem.endswith("-skill-analysis")):
            continue
        if stem in keep_output_stems:
            continue
        moved_out.append(path)

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    archive_dir: Path | None = (archive_root / stamp) if (moved_in or moved_out) else None
    dest_inputs = (archive_root / stamp / "inputs") if archive_dir else None
    dest_outputs = (archive_root / stamp / "outputs") if archive_dir else None

    def do_move(src: Path, dest_dir: Path) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if dry_run:
            return
        dest = dest_dir / src.name
        shutil.move(str(src), str(dest))

    if archive_dir and dest_inputs and dest_outputs:
        for path in moved_in:
            do_move(path, dest_inputs)
        for path in moved_out:
            do_move(path, dest_outputs)

    return ArchiveResult(
        moved_inputs=moved_in,
        moved_outputs=moved_out,
        archive_dir=archive_dir,
        kept_batch_stem=keep_batch,
        kept_analysis_stem=keep_analysis,
        kept_skill_stem=keep_skill,
    )
