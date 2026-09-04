from app.changes.generate import heuristic_fix, humanize_filename, sentence_clip
from app.keywords.analyze import RankRow, aggregate_queries, choose_focus_keywords, opportunity_score, position_delta
from app.migration.planner import build_plan
from tests.conftest import BAD_HTML, GOOD_HTML, snap


def test_opportunity_peaks_in_striking_distance():
    assert opportunity_score(7, 5000) > opportunity_score(2, 5000) > opportunity_score(45, 5000)
    assert opportunity_score(7, 0) == 0


def test_aggregate_and_focus_keywords():
    rows = [
        RankRow("running shoes flat feet", "https://example.com/shoes/flat-feet", 8.0, 30, 900),
        RankRow("Running Shoes Flat Feet", "https://example.com/shoes/flat-feet", 6.0, 20, 600),
        RankRow("gaiters", "https://example.com/gaiters", 2.0, 100, 400),
        RankRow("rare term", "https://example.com/x", 40.0, 0, 3),
    ]
    stats = aggregate_queries(rows)
    top = stats[0]
    assert top.query == "running shoes flat feet" and top.impressions == 1500 and 6 < top.position < 8
    assert top.bucket == "striking_distance"
    assert next(s for s in stats if s.query == "gaiters").bucket == "defend"
    assert next(s for s in stats if s.query == "rare term").bucket == "long_tail"
    focus = choose_focus_keywords(stats, {"/gaiters": "kept"}, lambda u: u.replace("https://example.com", ""))
    assert focus["/shoes/flat-feet"] == "running shoes flat feet" and focus["/gaiters"] == "kept"
    assert "/x" not in focus  # too few impressions


def test_position_delta_detects_drop():
    daily = [(f"2026-08-{d:02d}", 5.0, 50) for d in range(1, 22)] + [(f"2026-08-{d:02d}", 11.0, 50) for d in range(22, 29)]
    d = position_delta(daily)
    assert d and d.delta == 6.0
    assert position_delta(daily[:3]) is None


def test_heuristic_fixes():
    s = snap("https://example.com/shoes/flat-feet", BAD_HTML.replace("<h1>One</h1><h1>Two</h1>", "<h1>Stability Shoes Guide</h1>"))
    title = heuristic_fix("TITLE_MISSING", {}, s, "flat feet", "ShoeLab")
    assert title and title.kind == "title" and "flat feet" in title.after.lower() and len(title.after) <= 60
    meta = heuristic_fix("META_DESC_MISSING", {}, snap("https://example.com/a", GOOD_HTML), None, "ShoeLab")
    assert meta and 60 <= len(meta.after) <= 155
    alt = heuristic_fix("IMG_ALT_MISSING", {"missing": ["/a/b/red-car-01.png", "/x.png"]}, s, None, "ShoeLab")
    assert alt and alt.after == "Red car" and "1 more" in alt.rationale
    assert heuristic_fix("ORPHAN_PAGE", {}, s, None, "ShoeLab") is None
    assert humanize_filename("hero_shoes-2024.webp") == "Hero shoes"
    assert sentence_clip("One sentence here. Another one that is long enough to be cut off somewhere.", 30) == "One sentence here."
    assert sentence_clip("No sentence boundary anywhere in this long run of words at all", 30).endswith("…")


def test_migration_plan_maps_and_flags():
    old = [
        snap("https://old.example.com/", GOOD_HTML),
        snap("https://old.example.com/shoes/flat-feet.html", GOOD_HTML),
        snap("https://old.example.com/blog/gaiters-review", GOOD_HTML.replace("Best Running Shoes for Flat Feet", "Trail Gaiters Review")),
        snap("https://old.example.com/only-on-old", GOOD_HTML.replace("Best Running Shoes for Flat Feet", "Something Entirely Different Here")),
    ]
    new = [
        snap("https://new.example.com/", GOOD_HTML),
        snap("https://new.example.com/shoes/flat-feet", GOOD_HTML.replace("<head>", '<head><meta name="robots" content="noindex">')),
        snap("https://new.example.com/reviews/gaiters-review", GOOD_HTML.replace("Best Running Shoes for Flat Feet", "Trail Gaiters Review")),
    ]
    plan = build_plan(old, new, old_clicks={"/only-on-old": 120, "/shoes/flat-feet.html": 800}, old_origin="https://old.example.com", new_origin="https://new.example.com")
    by_old = {m.old_path: m for m in plan.url_map}
    assert by_old["/"].method == "exact"
    assert by_old["/shoes/flat-feet.html"].new_path == "/shoes/flat-feet" and by_old["/shoes/flat-feet.html"].method == "exact"
    assert by_old["/blog/gaiters-review"].new_path == "/reviews/gaiters-review" and by_old["/blog/gaiters-review"].method == "slug"
    assert by_old["/only-on-old"].new_path is None
    assert {r["from"] for r in plan.redirects} == {"/shoes/flat-feet.html", "/blog/gaiters-review"}
    kinds = {(g.path, g.kind) for g in plan.gaps}
    assert ("/only-on-old", "missing_page") in kinds
    assert ("/shoes/flat-feet", "noindex") in kinds
    assert plan.strategy == "staged_subdomain" and plan.risk_score > 0
    assert plan.stats["old_traffic_covered"] == round(800 / 920, 3)
    assert [s.phase for s in plan.steps][:3] == ["prepare"] * 3 and plan.steps[-1].phase == "monitor"
