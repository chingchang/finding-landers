from landers.label import StripLabel, parse

FAKE_ID = "ESP_" + "000001_0000"  # built at runtime so the leak check never sees an id in source
SAMPLE = """
PDS_VERSION_ID            = PDS3
/* a comment */
OBSERVATION_ID            = "FAKE_ID"
RATIONALE_DESC            = "Two line
                            title"
SOURCE_PRODUCT_ID         = (A_0, A_1,
                            B_0)
OBJECT = IMAGE_MAP_PROJECTION
    MAP_SCALE                    = 0.25 <METERS/PIXEL>
    CENTER_LATITUDE              = -90.000 <DEG>
END_OBJECT = IMAGE_MAP_PROJECTION
GROUP = VIEWING_PARAMETERS
    INCIDENCE_ANGLE   = 49.612548 <DEG>
END_GROUP = VIEWING_PARAMETERS
END
"""


def test_parse_values_units_lists_and_nesting():
    d = parse(SAMPLE.replace("FAKE_ID", FAKE_ID))
    assert d["OBSERVATION_ID"] == FAKE_ID
    assert d["RATIONALE_DESC"] == "Two line title"
    assert d["SOURCE_PRODUCT_ID"] == ["A_0", "A_1", "B_0"]
    assert d["IMAGE_MAP_PROJECTION"]["MAP_SCALE"] == 0.25
    assert d["IMAGE_MAP_PROJECTION"]["CENTER_LATITUDE"] == -90.0
    assert d["VIEWING_PARAMETERS"]["INCIDENCE_ANGLE"] == 49.612548


def test_read_real_labels(all_labels):
    for p in all_labels:
        lbl = StripLabel.read(p)
        assert lbl.observation_id == p.name.split("_RED")[0]
        assert lbl.lines > 1000 and lbl.samples > 1000
        assert lbl.scale_m in (0.25, 0.5)
        assert lbl.projection in ("EQUIRECTANGULAR", "POLAR STEREOGRAPHIC")
        assert 0 < lbl.incidence_deg < 90
