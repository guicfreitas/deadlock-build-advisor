from deadlock_advisor import steam

LIBRARIES = r'''
"libraryfolders"
{
	"0"
	{
		"path"		"C:\Program Files (x86)\Steam"
		"apps"		{ "228980"		"1" }
	}
	"1"
	{
		"path"		"D:\SteamLibrary"
		"apps"		{ "1422450"		"2" }
	}
}
'''


def _steam(tmp_path, launch="-condebug -novid"):
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    lib = tmp_path / "Lib"
    (lib / "steamapps" / "common" / "Deadlock" / "game" / "citadel").mkdir(parents=True)
    (lib / "steamapps" / "appmanifest_1422450.acf").write_text(
        '"AppState"\n{\n\t"appid"\t"1422450"\n\t"installdir"\t"Deadlock"\n}\n', encoding="utf-8")
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0" { "path" "%s" }\n "1" { "path" "%s" }\n}\n'
        % (str(root).replace("\\", "\\\\"), str(lib).replace("\\", "\\\\")), encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "loginusers.vdf").write_text(
        '"users"\n{\n "76561197960265729" { "MostRecent" "0" "Timestamp" "9" }\n'
        ' "76561198117938023" { "MostRecent" "1" "Timestamp" "5" }\n}\n', encoding="utf-8")
    cfg = root / "userdata" / "157672295" / "config"
    cfg.mkdir(parents=True)
    (cfg / "localconfig.vdf").write_text(
        '"UserLocalConfigStore"\n{\n "Software"\n {\n  "valve"\n  {\n   "Steam"\n   {\n'
        '    "apps"\n    {\n     "1422450"\n     {\n      "LaunchOptions" "%s"\n     }\n'
        '    }\n   }\n  }\n }\n}\n' % launch, encoding="utf-8")
    return root, lib


def test_parse_vdf():
    d = steam.parse_vdf(LIBRARIES)
    assert d["libraryfolders"]["1"]["path"] == r"D:\SteamLibrary"
    assert d["libraryfolders"]["1"]["apps"] == {"1422450": "2"}


def test_find_game_and_account(tmp_path):
    root, lib = _steam(tmp_path)
    assert steam.find_game_dir(root) == lib / "steamapps" / "common" / "Deadlock"
    assert steam.most_recent_account(root) == 157672295  # MostRecent wins over a newer timestamp
    assert steam.launch_options(157672295, root) == "-condebug -novid"


def test_check_setup_flags_missing_condebug(tmp_path):
    root, lib = _steam(tmp_path, launch="+citadel_unit_status_use_new true")
    game = steam.find_game_dir(root)
    check = steam.check_setup(game, 157672295, root)
    assert check.condebug is False and not check.ok
    (game / "game" / "citadel" / "console.log").write_text("", encoding="utf-8")
    root2, _ = _steam(tmp_path / "b")
    assert steam.check_setup(game, 157672295, root2).ok
