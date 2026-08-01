from pathlib import Path


def test_v103_final_layer_is_loaded_last_and_synced():
    html = Path("index.html").read_text(encoding="utf-8")
    static_html = Path("static/index.html").read_text(encoding="utf-8")
    assert "./static/v103-conversation.css?v=103.0" in html
    assert html.rfind("v103-conversation.css") > html.rfind("v102.css")
    assert html == static_html


def test_v103_composer_uses_grid_instead_of_screen_coordinates():
    css = Path("static/v103-conversation.css").read_text(encoding="utf-8")
    block = css.split("/* Composer: grid item, never offset or fixed", 1)[1].split("/* Secondary surfaces", 1)[0]
    assert "grid-row: 3 !important" in block
    assert "justify-self: center !important" in block
    assert "left: auto !important" in block
    assert "right: auto !important" in block
    assert "transform: none !important" in block
    assert "position: fixed" not in block
    assert "calc(50%" not in block


def test_v103_responsive_accessibility_and_reactor_contract():
    css = Path("static/v103-conversation.css").read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 680px)" in css
    assert "@media (max-width: 390px)" in css
    assert "prefers-reduced-motion" in css
    assert "v103-orbit" in css and "v103-orbit-reverse" in css
    assert "v103-core-breathe" in css


def test_v103_cache_and_manifest_are_current():
    worker = Path("service-worker.js").read_text(encoding="utf-8")
    manifest = Path("static/manifest.webmanifest").read_text(encoding="utf-8")
    app = Path("static/app.js").read_text(encoding="utf-8")
    assert "jarvis-conversation-ui-v103-1" in worker
    assert "./static/v103-conversation.css?v=103.0" in worker
    assert "Adaptive Intelligence Workspace v104" in manifest
    assert "service-worker.js?v=104.0" in app


