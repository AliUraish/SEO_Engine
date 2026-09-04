from app.audit.rules import run_page_rules
from app.audit.site import run_site_rules, score_page
from app.audit.types import PageRuleContext
from app.crawler.parse import count_syllables, flesch_reading_ease
from tests.conftest import BAD_HTML, GOOD_HTML, snap


def test_parse_extracts_core_fields():
    s = snap("https://example.com/shoes/flat-feet", GOOD_HTML)
    assert s.title.startswith("Best Running Shoes")
    assert s.meta_description and "flat feet" in s.meta_description
    assert s.h1 == ["Best Running Shoes for Flat Feet"]
    assert s.h2 == ["How we tested"]
    assert s.canonical == "https://example.com/shoes/flat-feet"
    assert s.lang == "en" and s.viewport
    assert s.json_ld_types == ["Article"]
    assert s.open_graph["title"] and s.open_graph["image"]
    assert s.word_count > 300
    internal = [link for link in s.links if link.internal]
    external = [link for link in s.links if not link.internal]
    assert internal[0].href == "https://example.com/shoes/overpronation" and len(external) == 1
    assert s.images[0].alt == "Runner wearing stability shoes"


def test_good_page_scores_high_and_bad_page_low():
    good = run_page_rules(PageRuleContext(snap("https://example.com/shoes/flat-feet", GOOD_HTML), "running shoes for flat feet"))
    assert {f.rule_code for f in good} == set(), [f.rule_code for f in good]
    assert score_page(good) == 100

    bad = run_page_rules(PageRuleContext(snap("http://example.com/Bad_Page", BAD_HTML), "red car"))
    codes = {f.rule_code for f in bad}
    for expected in ("NOT_HTTPS", "TITLE_MISSING", "META_DESC_MISSING", "H1_MULTIPLE", "THIN_CONTENT", "IMG_ALT_MISSING", "VIEWPORT_MISSING", "LANG_MISSING", "GENERIC_ANCHORS", "URL_UNFRIENDLY", "CANONICAL_MISSING"):
        assert expected in codes, expected
    assert score_page(bad) < 30


def test_dead_page_only_reports_transport_rules():
    findings = run_page_rules(PageRuleContext(snap("https://example.com/gone", "", status=404)))
    assert [f.rule_code for f in findings] == ["HTTP_ERROR"]
    assert findings[0].severity == "high"


def test_keyword_rules_fire_when_keyword_absent():
    codes = {f.rule_code for f in run_page_rules(PageRuleContext(snap("https://example.com/shoes/flat-feet", GOOD_HTML), "trail gaiters"))}
    assert {"TITLE_NO_KEYWORD", "META_DESC_NO_KEYWORD", "H1_NO_KEYWORD", "KEYWORD_NOT_IN_INTRO", "KEYWORD_DENSITY"} <= codes


def test_site_rules_duplicates_orphans_broken_links():
    a = snap("https://example.com/", GOOD_HTML.replace("/shoes/overpronation", "/b"))
    b = snap("https://example.com/b", GOOD_HTML.replace("/shoes/overpronation", "/dead"))
    dead = snap("https://example.com/dead", "", status=404)
    orphan = snap("https://example.com/orphan", GOOD_HTML.replace("Best Running Shoes for Flat Feet 2026", "Unique"))
    out = run_site_rules([a, b, dead, orphan])
    assert any(f.rule_code == "TITLE_DUPLICATE" for f in out["https://example.com/"])
    assert any(f.rule_code == "BROKEN_INTERNAL_LINK" for f in out["https://example.com/b"])
    assert any(f.rule_code == "ORPHAN_PAGE" for f in out["https://example.com/orphan"])
    assert "https://example.com/" not in {u for u, fs in out.items() if any(f.rule_code == "ORPHAN_PAGE" for f in fs)}


def test_readability_helpers():
    assert count_syllables("running") == 2
    assert count_syllables("the") == 1
    assert flesch_reading_ease(10, 1, 12) is None
    assert 0 <= flesch_reading_ease(200, 12, 280) <= 100
