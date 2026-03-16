from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from agentic_workers.providers.readme_analyst import (
    CONTROLLED_REPOSITORY_CATEGORIES,
    LLMReadmeBusinessAnalysis,
    MonetizationPotential,
    NormalizedReadme,
    contains_any_signals,
)
from agentic_workers.storage.backend_models import RepositoryIntake


_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "workflow": ("workflow", "approval", "automation", "orchestrat", "business process"),
    "analytics": ("analytics", "dashboard", "insight", "reporting", "metric", "bi "),
    "devops": ("ci/cd", "deploy", "kubernetes", "infra as code", "devops", "pipeline"),
    "infrastructure": ("gateway", "proxy", "database", "storage", "infrastructure", "cluster"),
    "devtools": ("developer", "sdk", "cli", "tooling", "framework", "plugin"),
    "crm": ("crm", "customer relationship", "sales", "lead", "pipeline", "account"),
    "communication": ("chat", "message", "email", "notification", "communication", "slack"),
    "support": ("ticket", "helpdesk", "support", "knowledge base", "incident response"),
    "observability": ("observability", "monitoring", "tracing", "logging", "metrics"),
    "low_code": ("no-code", "no code", "low-code", "low code", "builder", "form builder"),
    "security": ("security", "authentication", "authorization", "sso", "compliance"),
    "ai_ml": ("machine learning", "ml", "llm", "ai ", "embedding", "model"),
    "data": ("etl", "warehouse", "data pipeline", "data sync", "schema", "lineage"),
    "productivity": ("productivity", "project management", "task management", "notes"),
}

_AGENT_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "workflow": ("workflow", "approval", "orchestrat"),
    "automation": ("automation", "automate"),
    "analytics": ("analytics", "dashboard", "reporting", "insight"),
    "crm": ("crm", "sales", "lead"),
    "b2b": ("enterprise", "team", "b2b", "customer"),
    "devops": ("devops", "ci/cd", "deploy", "infrastructure"),
    "support": ("support", "ticket", "helpdesk"),
    "communication": ("message", "email", "chat", "notification"),
    "monitoring": ("monitoring", "observability", "tracing", "logging"),
    "api": ("api", "rest", "graphql", "webhook"),
    "data": ("etl", "warehouse", "lineage", "schema"),
    "database": ("database", "postgres", "mysql", "sqlite"),
    "low-code": ("low-code", "low code", "no-code", "no code"),
    "docker": ("docker", "container", "docker-compose", "kubernetes"),
    "react": ("react", "next.js", "nextjs"),
    "python": ("python", "fastapi", "django", "flask"),
}

_HIGH_MONETIZATION_SIGNALS = (
    "pricing",
    "subscription",
    "enterprise",
    "customers",
    "billing",
    "revenue",
    "paid",
    "b2b",
    "saas",
)
_MEDIUM_MONETIZATION_SIGNALS = (
    "team",
    "teams",
    "workflow",
    "automation",
    "dashboard",
    "analytics",
    "platform",
    "api",
)


@dataclass(frozen=True, slots=True)
class RepositoryAnalysisEvidence:
    evidence_version: str
    signals: dict[str, object]
    score_breakdown: dict[str, int]
    evidence_summary: str
    analysis_summary_short: str
    analysis_summary_long: str
    supporting_signals: list[str]
    red_flags: list[str]
    contradictions: list[str]
    missing_information: list[str]
    insufficient_evidence_reason: str | None

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "evidence_version": self.evidence_version,
            "evidence_summary": self.evidence_summary,
            "signals": self.signals,
            "score_breakdown": self.score_breakdown,
            "analysis_summary_short": self.analysis_summary_short,
            "analysis_summary_long": self.analysis_summary_long,
            "supporting_signals": self.supporting_signals,
            "red_flags": self.red_flags,
            "contradictions": self.contradictions,
            "missing_information": self.missing_information,
            "insufficient_evidence_reason": self.insufficient_evidence_reason,
        }


def extract_repository_analysis_evidence(
    *,
    repository: RepositoryIntake,
    normalized_readme: NormalizedReadme | None,
    observed_at: datetime,
    repository_intelligence: dict[str, object] | None = None,
    readme_missing_reason: str | None = None,
) -> RepositoryAnalysisEvidence:
    intelligence = repository_intelligence or {}
    readme_text = normalized_readme.normalized_text if normalized_readme is not None else ""
    description = repository.repository_description or ""
    corpus = f"{repository.full_name}\n{description}\n{readme_text}".lower()
    tree_paths = _get_str_list(intelligence, "tree_paths")
    selected_files = _get_dict(intelligence, "selected_files")
    file_corpus = "\n".join(
        f"{path}\n{content}" for path, content in selected_files.items() if isinstance(content, str)
    ).lower()
    combined_corpus = f"{corpus}\n{file_corpus}"
    metadata = _get_dict(intelligence, "metadata")
    contributors = _get_list(intelligence, "contributors")
    releases = _get_list(intelligence, "releases")
    commits = _get_list(intelligence, "recent_commits")
    pull_requests = _get_list(intelligence, "recent_pull_requests")
    issues = _get_list(intelligence, "recent_issues")

    pushed_at = repository.pushed_at
    days_since_last_push: int | None = None
    if pushed_at is not None:
        days_since_last_push = max((observed_at - pushed_at).days, 0)

    recent_commit_count_30d = _count_recent_timestamped_items(commits, observed_at, 30, "committed_at")
    recent_commit_count_90d = _count_recent_timestamped_items(commits, observed_at, 90, "committed_at")
    release_count = len(releases)
    last_release_at = _latest_timestamp(releases, "published_at")
    issue_count = len(issues)
    contributors_count = len(contributors)
    top_contributor_share = _calculate_top_contributor_share(contributors)

    signals: dict[str, object] = {
        "has_readme": normalized_readme is not None,
        "readme_length": len(readme_text),
        "readme_mentions_hosted": _has_any(combined_corpus, ("hosted", "cloud", "managed service")),
        "readme_mentions_cloud": _has_any(combined_corpus, ("cloud", "aws", "gcp", "azure")),
        "readme_mentions_enterprise": _has_any(combined_corpus, ("enterprise", "sso", "compliance")),
        "readme_mentions_pricing": _has_any(combined_corpus, ("pricing", "subscription", "billing", "paid")),
        "readme_mentions_auth": _has_any(combined_corpus, ("auth", "oauth", "sso", "login")),
        "readme_mentions_api": _has_any(combined_corpus, (" api", "graphql", "rest", "webhook")),
        "readme_mentions_plugin": _has_any(combined_corpus, ("plugin", "extension", "integration")),
        "readme_mentions_team": _has_any(combined_corpus, ("team", "teams", "organization", "workspace")),
        "stars": repository.stargazers_count,
        "forks": repository.forks_count,
        "github_created_at": repository.github_created_at.isoformat() if repository.github_created_at else None,
        "pushed_at": pushed_at.isoformat() if pushed_at else None,
        "days_since_last_push": days_since_last_push,
        "has_tests": _has_any(combined_corpus, ("test", "pytest", "jest", "vitest", "cypress"))
        or any(path.startswith("tests") or path.endswith("_test.py") for path in tree_paths),
        "has_ci": _has_any(combined_corpus, ("github actions", "ci/cd", "pipeline", "continuous integration"))
        or any(path.startswith(".github/workflows/") for path in tree_paths),
        "has_releases_config": any("release" in path.lower() for path in tree_paths),
        "has_license": _has_any(combined_corpus, ("license", "mit", "apache 2.0", "gpl"))
        or bool(_get_optional_str(metadata, "license_name"))
        or any(path.lower().startswith("license") for path in tree_paths),
        "has_docs_dir": any(path.startswith("docs/") for path in tree_paths)
        or _has_any(combined_corpus, ("docs", "documentation", "handbook")),
        "has_examples_dir": any(path.startswith("examples/") for path in tree_paths)
        or _has_any(combined_corpus, ("example", "examples", "demo")),
        "has_dockerfile": any(path.lower() == "dockerfile" for path in tree_paths)
        or _has_any(combined_corpus, ("dockerfile", "docker compose", "docker-compose")),
        "has_containerization": any("docker" in path.lower() or "k8s" in path.lower() for path in tree_paths)
        or _has_any(combined_corpus, ("docker", "container", "kubernetes")),
        "has_deploy_config": any(
            path.lower().startswith(("helm", "terraform", "deploy", ".github/workflows"))
            for path in tree_paths
        ) or _has_any(combined_corpus, ("deploy", "deployment", "helm", "terraform")),
        "has_backend_surface": _has_any(combined_corpus, ("api", "server", "backend", "fastapi", "django", "flask"))
        or any(path.startswith(("api/", "server/", "backend/")) for path in tree_paths),
        "has_frontend_surface": _has_any(combined_corpus, ("frontend", "react", "next.js", "ui", "dashboard"))
        or any(path.startswith(("app/", "web/", "frontend/")) for path in tree_paths),
        "has_admin_surface": _has_any(combined_corpus, ("admin", "backoffice", "control panel"))
        or any("admin" in path.lower() for path in tree_paths),
        "has_auth_signals": _has_any(combined_corpus, ("oauth", "sso", "rbac", "auth", "login")),
        "has_api_surface": _has_any(combined_corpus, ("api", "graphql", "rest", "webhook")),
        "primary_languages": _detect_primary_languages(combined_corpus),
        "package_managers": _detect_package_managers(combined_corpus),
        "framework_signals": _detect_framework_signals(combined_corpus),
        "repository_description_present": bool(description.strip()),
        "topics": _get_str_list(metadata, "topics"),
        "contributors_count": contributors_count,
        "recent_commit_count_30d": recent_commit_count_30d,
        "recent_commit_count_90d": recent_commit_count_90d,
        "open_issues": issue_count,
        "release_count": release_count,
        "last_release_at": last_release_at,
        "pr_merge_rate_recent": _estimate_pr_merge_rate(pull_requests),
        "issue_response_time_estimate": None,
        "maintainer_concentration_risk": (
            "high" if top_contributor_share >= 0.75 and contributors_count > 0 else "medium" if top_contributor_share >= 0.5 else "low"
        ),
        "tree_paths": tree_paths[:80],
        "selected_files": selected_files,
    }

    supporting_signals = _build_supporting_signals(repository=repository, signals=signals)
    red_flags = _build_red_flags(signals=signals, readme_missing_reason=readme_missing_reason)
    contradictions = _build_contradictions(signals=signals)
    missing_information = _build_missing_information(signals=signals)
    score_breakdown = _build_score_breakdown(
        repository=repository,
        signals=signals,
        contradictions=contradictions,
        red_flags=red_flags,
    )
    insufficient_evidence_reason = _build_insufficient_reason(
        signals=signals,
        readme_missing_reason=readme_missing_reason,
    )

    summary = _build_evidence_summary(
        repository=repository,
        signals=signals,
        supporting_signals=supporting_signals,
        red_flags=red_flags,
    )
    analysis_summary_short = _build_analysis_summary_short(
        repository=repository,
        score_breakdown=score_breakdown,
        insufficient_evidence_reason=insufficient_evidence_reason,
    )
    analysis_summary_long = _build_analysis_summary_long(
        evidence_summary=summary,
        score_breakdown=score_breakdown,
        supporting_signals=supporting_signals,
        contradictions=contradictions,
        missing_information=missing_information,
    )

    return RepositoryAnalysisEvidence(
        evidence_version="fast-evidence-v1",
        signals=signals,
        score_breakdown=score_breakdown,
        evidence_summary=summary,
        analysis_summary_short=analysis_summary_short,
        analysis_summary_long=analysis_summary_long,
        supporting_signals=supporting_signals,
        red_flags=red_flags,
        contradictions=contradictions,
        missing_information=missing_information,
        insufficient_evidence_reason=insufficient_evidence_reason,
    )


def build_insufficient_evidence_analysis(
    *,
    repository: RepositoryIntake,
    evidence: RepositoryAnalysisEvidence,
) -> LLMReadmeBusinessAnalysis:
    inferred_category = _infer_category(repository.full_name, repository.repository_description or "")
    inferred_tags = _infer_agent_tags(repository.full_name, repository.repository_description or "")
    monetization = _infer_monetization(repository.repository_description or "")

    return LLMReadmeBusinessAnalysis(
        target_audience="Unknown",
        technical_stack=None,
        open_problems=evidence.evidence_summary,
        competitors=None,
        problem_statement=repository.repository_description,
        target_customer="Unclear from available evidence",
        product_type="Open-source repository",
        business_model_guess="Unknown",
        category=inferred_category,
        category_confidence_score=25 if inferred_category else 0,
        agent_tags=_augment_agent_tags_from_evidence(
            inferred_tags,
            evidence=evidence,
        ),
        suggested_new_categories=[],
        suggested_new_tags=[],
        monetization_potential=monetization,
        pros=evidence.supporting_signals[:4],
        cons=evidence.red_flags[:4],
        missing_feature_signals=[evidence.insufficient_evidence_reason or "Need richer repository evidence."],
        confidence_score=25,
        recommended_action="Gather more repository evidence before shortlisting.",
    )


def determine_analysis_outcome(
    *,
    analysis: LLMReadmeBusinessAnalysis,
    evidence: RepositoryAnalysisEvidence,
) -> str:
    if evidence.insufficient_evidence_reason:
        return "insufficient_evidence"
    if analysis.confidence_score < 60 or analysis.category_confidence_score < 50 or evidence.contradictions:
        return "completed_low_confidence"
    return "completed"


def _build_score_breakdown(
    *,
    repository: RepositoryIntake,
    signals: dict[str, object],
    contradictions: list[str],
    red_flags: list[str],
) -> dict[str, int]:
    technical_maturity = 0
    if signals["has_tests"]:
        technical_maturity += 15
    if signals["has_ci"]:
        technical_maturity += 12
    if signals["has_license"]:
        technical_maturity += 10
    if signals["has_docs_dir"]:
        technical_maturity += 8
    if signals["has_examples_dir"]:
        technical_maturity += 5
    if signals["has_containerization"]:
        technical_maturity += 10
    if signals["has_deploy_config"]:
        technical_maturity += 10
    if signals["has_backend_surface"]:
        technical_maturity += 10
    if signals["has_frontend_surface"]:
        technical_maturity += 8
    if int(signals.get("recent_commit_count_90d", 0) or 0) >= 10:
        technical_maturity += 12
    elif int(signals.get("recent_commit_count_90d", 0) or 0) >= 1:
        technical_maturity += 6

    commercial_readiness = 0
    if signals["readme_mentions_pricing"]:
        commercial_readiness += 18
    if signals["readme_mentions_enterprise"]:
        commercial_readiness += 12
    if signals["readme_mentions_team"]:
        commercial_readiness += 10
    if signals["has_auth_signals"]:
        commercial_readiness += 10
    if signals["has_api_surface"]:
        commercial_readiness += 12
    if signals["has_admin_surface"]:
        commercial_readiness += 8
    if signals["has_frontend_surface"]:
        commercial_readiness += 8
    if signals["has_backend_surface"]:
        commercial_readiness += 8
    if signals["readme_mentions_plugin"]:
        commercial_readiness += 6
    if int(signals.get("release_count", 0) or 0) >= 1:
        commercial_readiness += 8

    hosted_gap = 0
    if signals["has_api_surface"] or signals["has_backend_surface"]:
        hosted_gap += 20
    if signals["has_frontend_surface"]:
        hosted_gap += 10
    if signals["has_containerization"] or signals["has_deploy_config"]:
        hosted_gap += 20
    if signals["has_auth_signals"]:
        hosted_gap += 10
    if repository.stargazers_count >= 50:
        hosted_gap += 10
    if signals["has_tests"] and signals["has_license"]:
        hosted_gap += 10
    if int(signals.get("release_count", 0) or 0) >= 1:
        hosted_gap += 10
    if signals["readme_mentions_hosted"] or signals["readme_mentions_cloud"]:
        hosted_gap -= 20
    if signals["readme_mentions_pricing"]:
        hosted_gap -= 10

    market_timing = 0
    if repository.stargazers_count >= 500:
        market_timing += 30
    elif repository.stargazers_count >= 100:
        market_timing += 20
    elif repository.stargazers_count >= 25:
        market_timing += 12
    if int(signals.get("recent_commit_count_90d", 0) or 0) >= 20:
        market_timing += 20
    elif int(signals.get("recent_commit_count_90d", 0) or 0) >= 5:
        market_timing += 12
    if int(signals.get("contributors_count", 0) or 0) >= 3:
        market_timing += 12
    elif int(signals.get("contributors_count", 0) or 0) >= 2:
        market_timing += 8
    if int(signals.get("release_count", 0) or 0) >= 3:
        market_timing += 15
    elif int(signals.get("release_count", 0) or 0) >= 1:
        market_timing += 10
    pr_merge_rate = signals.get("pr_merge_rate_recent")
    if isinstance(pr_merge_rate, float):
        market_timing += int(round(pr_merge_rate * 15))
    if signals["readme_mentions_enterprise"] or signals["readme_mentions_team"]:
        market_timing += 8

    trust_risk = 0
    if not signals["has_license"]:
        trust_risk += 25
    if not signals["has_tests"]:
        trust_risk += 15
    if not signals["has_ci"]:
        trust_risk += 10
    if signals.get("maintainer_concentration_risk") == "high":
        trust_risk += 20
    elif signals.get("maintainer_concentration_risk") == "medium":
        trust_risk += 10
    if isinstance(signals.get("days_since_last_push"), int) and int(signals["days_since_last_push"]) > 180:
        trust_risk += 20
    if not signals["readme_mentions_pricing"]:
        trust_risk += 5
    trust_risk += min(len(contradictions) * 8, 16)
    trust_risk += min(len(red_flags) * 3, 12)

    return {
        "technical_maturity_score": min(technical_maturity, 100),
        "commercial_readiness_score": min(commercial_readiness, 100),
        "hosted_gap_score": max(0, min(hosted_gap, 100)),
        "market_timing_score": min(market_timing, 100),
        "trust_risk_score": min(trust_risk, 100),
    }


def _build_analysis_summary_short(
    *,
    repository: RepositoryIntake,
    score_breakdown: dict[str, int],
    insufficient_evidence_reason: str | None,
) -> str:
    if insufficient_evidence_reason:
        return insufficient_evidence_reason
    return (
        f"{repository.full_name} shows technical maturity "
        f"{score_breakdown['technical_maturity_score']}/100 and commercial readiness "
        f"{score_breakdown['commercial_readiness_score']}/100, with hosted-gap opportunity "
        f"{score_breakdown['hosted_gap_score']}/100."
    )


def _build_analysis_summary_long(
    *,
    evidence_summary: str,
    score_breakdown: dict[str, int],
    supporting_signals: list[str],
    contradictions: list[str],
    missing_information: list[str],
) -> str:
    pieces = [
        evidence_summary,
        (
            "Score breakdown: "
            f"technical maturity {score_breakdown['technical_maturity_score']}/100, "
            f"commercial readiness {score_breakdown['commercial_readiness_score']}/100, "
            f"hosted gap {score_breakdown['hosted_gap_score']}/100, "
            f"market timing {score_breakdown['market_timing_score']}/100, "
            f"trust risk {score_breakdown['trust_risk_score']}/100."
        ),
    ]
    if supporting_signals:
        pieces.append(f"Supporting signals: {' '.join(supporting_signals[:3])}")
    if contradictions:
        pieces.append(f"Contradictions: {' '.join(contradictions[:2])}")
    if missing_information:
        pieces.append(f"Missing information: {' '.join(missing_information[:3])}")
    return " ".join(piece for piece in pieces if piece)


def _augment_agent_tags_from_evidence(
    tags: list[str],
    *,
    evidence: RepositoryAnalysisEvidence,
) -> list[str]:
    enriched = list(tags)
    score_breakdown = evidence.score_breakdown
    if score_breakdown.get("hosted_gap_score", 0) >= 60:
        enriched.append("hosted-gap")
    if score_breakdown.get("commercial_readiness_score", 0) >= 60:
        enriched.append("commercial-ready")
    if evidence.contradictions or evidence.insufficient_evidence_reason:
        enriched.append("low-confidence")
    if evidence.signals.get("maintainer_concentration_risk") == "high":
        enriched.append("maintainer-risk")
    if score_breakdown.get("market_timing_score", 0) >= 60:
        enriched.append("needs-deep-analysis")
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in enriched:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:8]


def _has_any(corpus: str, patterns: tuple[str, ...]) -> bool:
    return contains_any_signals(corpus, patterns)


def _detect_primary_languages(corpus: str) -> list[str]:
    candidates = [
        ("python", ("python", "fastapi", "django", "flask", "pyproject.toml")),
        ("typescript", ("typescript", "tsconfig", "next.js", "react", "node")),
        ("javascript", ("javascript", "node.js", "node ", "npm")),
        ("go", (" golang", " go ", "go.mod")),
    ]
    return [label for label, patterns in candidates if _has_any(corpus, patterns)]


def _detect_package_managers(corpus: str) -> list[str]:
    candidates = [
        ("npm", ("npm", "package.json", "package-lock.json")),
        ("pnpm", ("pnpm", "pnpm-lock.yaml")),
        ("yarn", ("yarn", "yarn.lock")),
        ("uv", ("uv ", "uv.lock")),
        ("pip", ("requirements.txt", "pip install", "pip ")),
        ("poetry", ("poetry", "poetry.lock")),
    ]
    return [label for label, patterns in candidates if _has_any(corpus, patterns)]


def _detect_framework_signals(corpus: str) -> list[str]:
    candidates = [
        ("fastapi", ("fastapi",)),
        ("django", ("django",)),
        ("flask", ("flask",)),
        ("react", ("react",)),
        ("nextjs", ("next.js", "nextjs")),
        ("postgres", ("postgres", "postgresql")),
        ("docker", ("docker", "dockerfile", "docker compose")),
    ]
    return [label for label, patterns in candidates if _has_any(corpus, patterns)]


def _build_supporting_signals(
    *,
    repository: RepositoryIntake,
    signals: dict[str, object],
) -> list[str]:
    support: list[str] = []
    if repository.stargazers_count >= 100:
        support.append(f"Repository already has {repository.stargazers_count} GitHub stars.")
    if signals["has_api_surface"]:
        support.append("Evidence suggests the project exposes an API or webhook surface.")
    if signals["has_frontend_surface"] and signals["has_backend_surface"]:
        support.append("Signals indicate both frontend and backend product surfaces.")
    if signals["has_containerization"]:
        support.append("Containerization signals suggest deployment readiness work exists.")
    if signals["has_tests"]:
        support.append("Testing-related keywords suggest at least some engineering maturity.")
    if isinstance(signals.get("recent_commit_count_90d"), int) and signals["recent_commit_count_90d"] >= 10:
        support.append("Repository shows meaningful commit activity in the last 90 days.")
    if isinstance(signals.get("release_count"), int) and signals["release_count"] >= 1:
        support.append("Release history suggests maintainers ship packaged milestones.")
    return support


def _build_red_flags(
    *,
    signals: dict[str, object],
    readme_missing_reason: str | None,
) -> list[str]:
    red_flags: list[str] = []
    if readme_missing_reason:
        red_flags.append(readme_missing_reason)
    if not signals["has_license"]:
        red_flags.append("No explicit license signal was found in available evidence.")
    days_since_last_push = signals.get("days_since_last_push")
    if isinstance(days_since_last_push, int) and days_since_last_push > 180:
        red_flags.append(f"Repository has not been pushed in {days_since_last_push} days.")
    if not signals["readme_mentions_pricing"]:
        red_flags.append("Commercial packaging and pricing evidence is still weak.")
    if signals.get("maintainer_concentration_risk") == "high":
        red_flags.append("A single maintainer appears to dominate visible contribution activity.")
    return red_flags


def _build_insufficient_reason(
    *,
    signals: dict[str, object],
    readme_missing_reason: str | None,
) -> str | None:
    if readme_missing_reason:
        return "README evidence is unavailable, so this result is based on limited repository metadata."
    if int(signals.get("readme_length", 0) or 0) < 40:
        return "README evidence is too thin for a confident business assessment."
    return None


def _build_evidence_summary(
    *,
    repository: RepositoryIntake,
    signals: dict[str, object],
    supporting_signals: list[str],
    red_flags: list[str],
) -> str:
    status_bits = [
        f"{repository.stargazers_count} stars",
        f"{repository.forks_count} forks",
    ]
    if isinstance(signals.get("days_since_last_push"), int):
        status_bits.append(f"last push {signals['days_since_last_push']} days ago")

    product_bits: list[str] = []
    if signals["has_api_surface"]:
        product_bits.append("API surface")
    if signals["has_frontend_surface"]:
        product_bits.append("frontend surface")
    if signals["has_backend_surface"]:
        product_bits.append("backend surface")
    if signals["has_containerization"]:
        product_bits.append("containerization")

    pieces = [
        f"Deterministic evidence currently covers {', '.join(status_bits)}.",
        (
            f"Observed product signals: {', '.join(product_bits)}."
            if product_bits
            else "Observed product signals are still sparse."
        ),
    ]
    if supporting_signals:
        pieces.append(f"Supporting signals: {' '.join(supporting_signals[:2])}")
    if red_flags:
        pieces.append(f"Red flags: {' '.join(red_flags[:2])}")
    return " ".join(piece for piece in pieces if piece)


def _build_contradictions(*, signals: dict[str, object]) -> list[str]:
    contradictions: list[str] = []
    if signals["readme_mentions_hosted"] and not signals["has_deploy_config"]:
        contradictions.append("README mentions hosted/cloud positioning without matching deployment evidence.")
    if signals["readme_mentions_enterprise"] and not signals["has_auth_signals"]:
        contradictions.append("Enterprise positioning is present, but auth/compliance signals are thin.")
    if signals["has_frontend_surface"] and not signals["has_backend_surface"] and signals["readme_mentions_api"]:
        contradictions.append("API claims appear stronger than the detected backend surface.")
    return contradictions


def _build_missing_information(*, signals: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if not signals["readme_mentions_pricing"]:
        missing.append("Pricing or packaging details are missing.")
    if not signals["has_license"]:
        missing.append("License details are missing from the evidence pack.")
    if not signals["has_tests"]:
        missing.append("Test coverage signals are missing.")
    return missing


def _infer_category(repository_full_name: str, text: str) -> str | None:
    lower_text = f"{repository_full_name}\n{text}".lower()
    for category in CONTROLLED_REPOSITORY_CATEGORIES:
        keywords = _CATEGORY_KEYWORDS.get(category, ())
        if any(keyword in lower_text for keyword in keywords):
            return category
    return None


def _infer_agent_tags(repository_full_name: str, text: str) -> list[str]:
    lower_text = f"{repository_full_name}\n{text}".lower()
    tags: list[str] = []
    for tag, keywords in _AGENT_TAG_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            tags.append(tag)
    return tags[:8]


def _infer_monetization(text: str) -> MonetizationPotential:
    lower_text = text.lower()
    high_count = sum(signal in lower_text for signal in _HIGH_MONETIZATION_SIGNALS)
    medium_count = sum(signal in lower_text for signal in _MEDIUM_MONETIZATION_SIGNALS)
    if high_count >= 2:
        return MonetizationPotential.HIGH
    if high_count >= 1 or medium_count >= 2:
        return MonetizationPotential.MEDIUM
    return MonetizationPotential.LOW


def _get_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _get_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _get_str_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _get_optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _count_recent_timestamped_items(
    items: list[object],
    observed_at: datetime,
    days: int,
    key: str,
) -> int:
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get(key)
        if not isinstance(raw, str):
            continue
        parsed = _parse_iso_datetime(raw)
        if parsed is None:
            continue
        if observed_at - parsed <= timedelta(days=days):
            count += 1
    return count


def _latest_timestamp(items: list[object], key: str) -> str | None:
    latest: datetime | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get(key)
        if not isinstance(raw, str):
            continue
        parsed = _parse_iso_datetime(raw)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest is not None else None


def _estimate_pr_merge_rate(items: list[object]) -> float | None:
    if not items:
        return None
    relevant = [item for item in items if isinstance(item, dict)]
    if not relevant:
        return None
    merged = sum(1 for item in relevant if item.get("merged_at"))
    return round(merged / len(relevant), 2)


def _calculate_top_contributor_share(items: list[object]) -> float:
    contributions: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get("contributions")
        if isinstance(raw, int) and raw >= 0:
            contributions.append(raw)
    if not contributions:
        return 0.0
    total = sum(contributions)
    if total == 0:
        return 0.0
    return max(contributions) / total


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
