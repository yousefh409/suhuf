"""Model-free unit tests for the RoutedEnsemble logic (consonant channel,
agreement rule, single-model fallback). Does not load any model."""
import ensemble as E


def test_consonant_alternatives():
    # emphatic/plain + sibilant confusions are generated; identity is excluded
    alts = E.consonant_alternatives("صابر")  # ص has {س,ص...} -> سابر etc.
    vals = set(alts.values())
    assert "سابر" in vals, vals
    assert "صابر" not in vals
    # a word with no confusable consonants yields nothing
    assert E.consonant_alternatives("و") == {}
    print("consonant_alternatives OK:", sorted(vals)[:4])


def test_agrees():
    route = {"members": ["a", "b", "c"], "k": 2, "thresholds": {"a": 0.0, "b": 0.0, "c": 0.0}}
    # 2 of 3 above threshold -> agree
    assert E.agrees({"a": 0.1, "b": 0.2, "c": -0.1}, route) is True
    # only 1 above -> no
    assert E.agrees({"a": 0.1, "b": -0.5, "c": -0.1}, route) is False
    # missing margins count as not-fired
    assert E.agrees({"a": 0.1, "b": None}, route) is False
    # per-member thresholds respected
    route2 = {"members": ["a", "b"], "k": 1, "thresholds": {"a": 0.5, "b": 0.0}}
    assert E.agrees({"a": 0.3, "b": 0.1}, route2) is True   # b fires
    assert E.agrees({"a": 0.3, "b": -0.1}, route2) is False  # neither
    # no route -> None (single-model)
    assert E.agrees({"a": 1.0}, None) is None
    print("agrees OK")


def test_margins():
    # i3rab/tashkeel margin extraction respects skip flags and -999 sentinels
    a = {"skip_i3rab": False, "best_alt_score": 0.2, "effective_score": -0.1,
         "skip_tashkeel": False, "best_tashkeel_score": 0.0, "best_addvowel_score": -999.0}
    assert abs(E._i3rab_margin(a) - 0.3) < 1e-9
    assert abs(E._tashkeel_margin(a) - 0.1) < 1e-9
    assert E._i3rab_margin({"skip_i3rab": True, "best_alt_score": 1.0, "effective_score": 0}) is None
    assert E._tashkeel_margin({"skip_tashkeel": True}) is None
    print("margins OK")


def test_single_model_fallback():
    # no config file -> returns whatever the factory makes (no ensemble)
    sentinel = object()
    got = E.load_ensemble_or_engine(lambda p: sentinel, "models/base", config_path="___nope___.json")
    assert got is sentinel
    print("single-model fallback OK")


if __name__ == "__main__":
    test_consonant_alternatives()
    test_agrees()
    test_margins()
    test_single_model_fallback()
    print("\nALL ENSEMBLE LOGIC TESTS PASSED")
