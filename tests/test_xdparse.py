import datetime

from crossworder.xdparse import is_hard, parse_xd

SAMPLE = """Title: New York Times, Saturday, January 3, 2015
Author: Sam Ezersky
Editor: Will Shortz
Date: 2015-01-03


BOT#H
RHO#A
AIN#I
IFY#S
NOD#T


A1. Bollix ~ BOT
A4. Letter ~ H
D1. Down one ~ BRAIN
"""


def test_parses_date_and_author():
    p = parse_xd(SAMPLE)
    assert p is not None
    assert p.date == datetime.date(2015, 1, 3)
    assert p.author == "Sam Ezersky"


def test_parses_grid_rows():
    p = parse_xd(SAMPLE)
    assert p.width == 5
    assert p.height == 5
    assert p.rows[0] == "BOT#H"


def test_parses_clues():
    p = parse_xd(SAMPLE)
    assert len(p.clues) == 3
    first = p.clues[0]
    assert first.direction == "A"
    assert first.number == 1
    assert first.text == "Bollix"
    assert first.answer == "BOT"


def test_rejects_non_square_grid():
    bad = SAMPLE.replace("NOD#T\n", "")
    assert parse_xd(bad) is None


CIRCLE_SAMPLE = """Title: New York Times, Wednesday, May 12, 2004
Author: Jane Doe
Editor: Will Shortz
Special: circle
Date: 2004-05-12


WEDDI
nGBAN
D#MOP
ARTSY
#EDIT


A1. Nuptials, briefly ~ WEDDI
D1. Marriage jewelry ~ WEDDINGBAND
A6. Cleaning tool ~ MOP
"""


def test_parses_lowercase_circled_squares_as_uppercase():
    p = parse_xd(CIRCLE_SAMPLE)
    assert p is not None
    assert p.rows[1] == "NGBAN"
    for row in p.rows:
        assert row == row.upper()


def test_header_line_never_parsed_as_grid_row():
    p = parse_xd(CIRCLE_SAMPLE)
    assert p is not None
    assert "Author: Jane Doe" not in p.rows
    assert "Special: circle" not in p.rows
    assert not any(":" in row for row in p.rows)


def test_is_hard_only_for_shortz_era_fri_sat():
    p = parse_xd(SAMPLE)
    assert is_hard(p) is True  # 2015-01-03 was a Saturday

    monday = parse_xd(SAMPLE.replace("2015-01-03", "2015-01-05"))
    assert is_hard(monday) is False

    old_sat = parse_xd(SAMPLE.replace("2015-01-03", "1960-01-02"))
    assert is_hard(old_sat) is False
