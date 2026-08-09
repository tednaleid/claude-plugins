# ABOUTME: real-browser regression specs for the review page's JS (keyboard nav, fold,
# ABOUTME: click-to-edit, save-status, CSS glyphs, read-only mode) - run via `just test-ui`

import review_tool
from playwright.sync_api import expect


def active_fid(page):
    return page.locator(".finding.active").get_attribute("data-fid")


def test_fresh_load_post_checkboxes_unchecked_by_default(review_page):
    checks = review_page.locator(".post-chk")
    assert checks.count() >= 1
    for i in range(checks.count()):
        assert not checks.nth(i).is_checked()


def test_css_glyphs_render_actual_characters_not_escape_text(review_page):
    # The bug class this guards against: "\25cf"/"\25be" get eaten as an
    # octal escape in the Python source and ship as the literal text "cf"/"be".
    save_before = review_page.eval_on_selector(
        "#save-status", "el => getComputedStyle(el, '::before').content"
    )
    assert save_before.strip('"') == "●"

    fold_before = review_page.eval_on_selector(
        ".fold-toggle", "el => getComputedStyle(el, '::before').content"
    )
    assert fold_before.strip('"') == "▾"


def test_j_k_and_arrow_keys_move_active_card(review_page):
    page = review_page
    assert active_fid(page) == "f1"
    page.keyboard.press("j")
    assert active_fid(page) == "f2"
    page.keyboard.press("ArrowDown")
    assert active_fid(page) == "f3"
    page.keyboard.press("k")
    assert active_fid(page) == "f2"
    page.keyboard.press("ArrowUp")
    assert active_fid(page) == "f1"


def test_space_toggles_active_post_checkbox_and_persists(review_page, live_server):
    page = review_page
    _, url, _ = live_server
    chk = page.locator('.finding[data-fid="f1"] .post-chk')
    assert not chk.is_checked()
    page.keyboard.press(" ")
    assert chk.is_checked()
    page.wait_for_function(
        "() => document.getElementById('save-status').textContent === 'All changes saved'",
        timeout=5000,
    )
    state = page.request.get(url + "api/state").json()
    assert state["findings"]["f1"]["disposition"] == "post"


def test_enter_folds_active_card_and_advances(review_page):
    page = review_page
    f1 = page.locator('.finding[data-fid="f1"]')
    assert "collapsed" not in f1.get_attribute("class")
    page.keyboard.press("Enter")
    assert "collapsed" in f1.get_attribute("class")
    assert active_fid(page) == "f2"


def test_z_folds_active_card_in_place(review_page):
    page = review_page
    f1 = page.locator('.finding[data-fid="f1"]')
    page.keyboard.press("z")
    assert "collapsed" in f1.get_attribute("class")
    assert active_fid(page) == "f1"


def test_escape_from_open_editor_returns_to_nav_on_same_card(review_page):
    page = review_page
    view = page.locator('.finding[data-fid="f1"] .comment-view')
    textarea = page.locator('.finding[data-fid="f1"] textarea.comment')
    view.click()
    expect(textarea).not_to_be_hidden()
    page.keyboard.press("Escape")
    expect(textarea).to_be_hidden()
    assert active_fid(page) == "f1"


def test_n_focuses_active_notes_textarea_and_auto_expands_collapsed_card(review_page):
    page = review_page
    f1 = page.locator('.finding[data-fid="f1"]')
    page.keyboard.press("z")
    assert "collapsed" in f1.get_attribute("class")
    page.keyboard.press("n")
    assert "collapsed" not in f1.get_attribute("class")
    note = page.locator('.finding[data-fid="f1"] textarea.note')
    expect(note).to_be_focused()


def test_question_mark_opens_and_escape_closes_help_overlay(review_page):
    page = review_page
    help_panel = page.locator("#kbd-help")
    expect(help_panel).to_be_hidden()
    page.keyboard.press("?")
    expect(help_panel).to_be_visible()
    page.keyboard.press("Escape")
    expect(help_panel).to_be_hidden()


def test_nav_key_pressed_in_textarea_types_instead_of_navigating(review_page):
    page = review_page
    note = page.locator('.finding[data-fid="f1"] textarea.note')
    note.click()
    page.keyboard.type("j")
    assert note.input_value() == "j"
    assert active_fid(page) == "f1"


def test_click_to_edit_updates_view_in_place_without_reload(review_page):
    page = review_page
    view = page.locator('.finding[data-fid="f1"] .comment-view')
    textarea = page.locator('.finding[data-fid="f1"] textarea.comment')
    view.click()
    textarea.fill("Now with `code` in it.")
    page.evaluate("window.__marker = 'still-here'")
    page.locator("h1").click()
    page.wait_for_function(
        """() => document.querySelector('.finding[data-fid="f1"] .comment-view')
                 .innerHTML.includes('<code>code</code>')""",
        timeout=5000,
    )
    assert page.evaluate("window.__marker") == "still-here"


def test_save_status_transitions_saving_then_saved_on_edit(review_page):
    page = review_page
    status = page.locator("#save-status")
    note = page.locator('.finding[data-fid="f1"] textarea.note')
    note.click()
    note.type("adjust this")
    expect(status).to_have_text("Saving...")
    expect(status).to_have_text("All changes saved", timeout=5000)


def test_save_status_shows_error_and_banner_when_server_down(review_page, live_server):
    page = review_page
    srv, _, _ = live_server
    srv.shutdown()
    srv.server_close()  # close the listening socket so requests fail fast (connection refused)
    note = page.locator('.finding[data-fid="f1"] textarea.note')
    note.click()
    note.type("adjust while down")
    status = page.locator("#save-status")
    expect(status).to_have_text("Save failed - retrying", timeout=5000)
    banner = page.locator("#banner")
    expect(banner).to_be_visible()
    assert "show" in (banner.get_attribute("class") or "")


def test_read_only_static_page_disables_inputs_but_keeps_nav_and_fold(review_env, page):
    out_path = review_tool.cmd_render(review_env)
    page.goto(f"file://{out_path}")

    chk = page.locator('.finding[data-fid="f1"] .post-chk')
    note = page.locator('.finding[data-fid="f1"] textarea.note')
    expect(chk).to_be_disabled()
    expect(note).to_be_disabled()

    assert not chk.is_checked()
    page.keyboard.press(" ")
    assert not chk.is_checked()

    assert active_fid(page) == "f1"
    page.keyboard.press("j")
    assert active_fid(page) == "f2"

    f2 = page.locator('.finding[data-fid="f2"]')
    assert "collapsed" not in f2.get_attribute("class")
    page.keyboard.press("z")
    assert "collapsed" in f2.get_attribute("class")
