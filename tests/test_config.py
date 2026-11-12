import json

from deadlock_advisor import config


def _cfg(tmp_path, data=None):
    path = tmp_path / "config.json"
    if data is not None:
        path.write_text(json.dumps(data), encoding="utf-8")
    return config.load_config(path), path


def test_only_user_choices_are_saved(tmp_path):
    cfg, path = _cfg(tmp_path)
    res = config.update_settings(cfg, {"api_key": "  abc  ", "engine.filters.min_average_badge": "81",
                                       "port": 8787})          # 8787 is the default: not written
    assert res["errors"] == {} and res["restart"] == ["port"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"api_key": "abc", "engine": {"filters": {"min_average_badge": 81}}}
    assert cfg.api_key == "abc" and cfg.engine["filters"]["min_average_badge"] == 81


def test_empty_value_goes_back_to_auto(tmp_path):
    cfg, path = _cfg(tmp_path, {"account_id": 5, "engine": {"filters": {"min_average_badge": 81}}})
    config.update_settings(cfg, {"account_id": "", "engine.filters.min_average_badge": None})
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "account_id" not in saved and saved["engine"]["filters"] == {}


def test_invalid_values_save_nothing(tmp_path):
    cfg, path = _cfg(tmp_path)
    res = config.update_settings(cfg, {"port": "80", "api_key": "x", "nope": 1,
                                       "game_dir": str(tmp_path)})
    assert set(res["errors"]) == {"port", "nope", "game_dir"}
    assert not path.exists()


def test_broken_file_does_not_crash(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ not json", encoding="utf-8")
    cfg = config.load_config(path)
    assert cfg.port == 8787
    view = config.settings_view(cfg)
    assert view["effective"]["port"] == 8787 and view["user"]["port"] is None
