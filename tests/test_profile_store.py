"""
test_profile_store.py — ProfileStore testleri.

Gerçek dosya sistemine (pytest'in tmp_path fixture'ı) karşı çalışır,
hiçbir şey mock'lanmıyor.
"""

from __future__ import annotations

import json

import pytest

from services.profile_store import ProfileStore


@pytest.fixture
def store(tmp_path):
    return ProfileStore(profiles_dir=tmp_path / "profiles")


def test_list_profiles_empty_when_dir_missing(store):
    names, err = store.list_profiles()
    assert err is None
    assert names == []


def test_save_creates_dir_and_file(store):
    ok, err = store.save_profile("Etiyopya Yirgacheffe", {"pisirme_sicakligi": 205, "menseili": "Etiyopya"})
    assert ok is True
    assert err is None
    assert store.profiles_dir.is_dir()
    assert (store.profiles_dir / "Etiyopya Yirgacheffe.json").exists()


def test_save_then_load_roundtrip(store):
    data = {"mense": "Brezilya", "pisirme_sicakligi": 210, "egri": [[0, 180], [8, 215]]}
    ok, err = store.save_profile("brezilya-1", data)
    assert ok is True

    loaded, err = store.load_profile("brezilya-1")
    assert err is None
    assert loaded == data


def test_load_missing_profile_returns_error(store):
    data, err = store.load_profile("hic-olmayan")
    assert data is None
    assert "hic-olmayan" in err


def test_list_profiles_returns_sorted_names(store):
    store.save_profile("Zeta", {})
    store.save_profile("Alfa", {})
    store.save_profile("Mu", {})

    names, err = store.list_profiles()
    assert err is None
    assert names == ["Alfa", "Mu", "Zeta"]


def test_delete_profile(store):
    store.save_profile("silinecek", {"x": 1})
    ok, err = store.delete_profile("silinecek")
    assert ok is True
    assert err is None

    names, _ = store.list_profiles()
    assert "silinecek" not in names


def test_delete_missing_profile_returns_error(store):
    ok, err = store.delete_profile("yok-boyle-bir-sey")
    assert ok is False
    assert "yok-boyle-bir-sey" in err


@pytest.mark.parametrize("bad_name", ["../etc/passwd", "a/b", "a\\b", "", "x" * 81, "..", "a:b"])
def test_rejects_invalid_or_path_traversal_names(store, bad_name):
    ok, err = store.save_profile(bad_name, {"x": 1})
    assert ok is False
    assert err is not None

    data, err = store.load_profile(bad_name)
    assert data is None
    assert err is not None


def test_save_rejects_non_dict_payload(store):
    ok, err = store.save_profile("gecersiz", ["bu", "bir", "liste"])
    assert ok is False
    assert "dict" in err


def test_load_rejects_corrupt_json_file(store):
    store.profiles_dir.mkdir(parents=True)
    (store.profiles_dir / "bozuk.json").write_text("{bu gecerli json degil", encoding="utf-8")

    data, err = store.load_profile("bozuk")
    assert data is None
    assert "JSON" in err


def test_load_rejects_json_that_is_not_an_object(store):
    store.profiles_dir.mkdir(parents=True)
    (store.profiles_dir / "liste.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    data, err = store.load_profile("liste")
    assert data is None
    assert "dict" in err


def test_save_overwrites_existing_profile(store):
    store.save_profile("guncellenecek", {"pisirme_sicakligi": 200})
    store.save_profile("guncellenecek", {"pisirme_sicakligi": 215})

    data, err = store.load_profile("guncellenecek")
    assert err is None
    assert data == {"pisirme_sicakligi": 215}
