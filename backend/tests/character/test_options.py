"""AC1, AC4 -- sprint 009-01 WI3."""

import inspect

from app.modules.character import service


def test_ac1_option_counts_match_the_srd_level_1_set():
    assert len(service.races()) == 9
    assert len(service.classes()) == 12
    assert len(service.skills()) == 18
    assert len(service.alignments()) == 9


def test_ac4_every_list_reader_takes_no_argument_and_returns_a_non_empty_list():
    readers = [
        service.races,
        service.classes,
        service.skills,
        service.alignments,
        service.armours,
        service.weapons,
        service.gear,
    ]
    for reader in readers:
        assert inspect.signature(reader).parameters == {}
        assert len(reader()) > 0
