"""The real SAM backend's parsing, without the network: the parser's records mapped to ``SamObject``s and
the async parser driven from a list of events."""

import numpy as np
import pytest

msp = pytest.importorskip("meta_sam_parser")

from landers.models.backend import parse_sam_events, place_mask, sam_result_from_records  # noqa: E402


def box_record(oid, left, top, right, bottom, conf=None, order=0):
    return msp.SegmentationBoxRecord(
        order=order, object_id=str(oid), left=left, top=top, right=right, bottom=bottom, confidence=conf
    )


def mask_record(oid, bounds, w, h, conf=None, order=1):
    return msp.SegmentationMaskRecord(
        order=order,
        object_id=str(oid),
        identity=msp.SegmentationMaskIdentity(media="image", frame_index=None, object_id=str(oid)),
        revision=1,
        mask=msp.SegmentationMask(encoding="one_bit", payload="!stub", width=w, height=h),
        bounds=msp.SegmentationMaskBounds(*bounds),
        confidence=conf,
    )


def test_place_mask_scales_a_box_local_raster_into_the_image():
    small = np.array([[1, 0], [0, 1]], bool)
    full = place_mask(small, msp.SegmentationMaskBounds(left=10, top=20, right=14, bottom=24), 32, 32)
    assert full.shape == (32, 32) and full.sum() == 8
    assert full[20:22, 10:12].all() and full[22:24, 12:14].all() and not full[20:22, 12:14].any()
    clipped = place_mask(small, msp.SegmentationMaskBounds(left=30, top=30, right=40, bottom=40), 32, 32)
    assert clipped[30:32, 30:32].all() and clipped.sum() == 4


def test_records_become_objects_with_half_open_boxes_and_placed_masks():
    def decode(mask):
        assert mask.payload == "!stub"
        return bytes([1, 1, 0, 0] * (mask.height // 2) + [0, 0, 1, 1] * (mask.height // 2))

    recs = [
        box_record(1, 100, 120, 141, 161, conf=0.83),
        mask_record(1, (100, 120, 141, 161), 4, 4, conf=None),
        box_record(2, 0, 0, 256, 256, conf=0.2, order=2),
    ]
    res = sam_result_from_records(recs, 256, 256, decode, raw_text="raw")
    assert res.raw_text == "raw" and [o.object_id for o in res.objects] == [1, 2]
    o1 = res.objects[0]
    assert (o1.box.x1, o1.box.y1, o1.box.x2, o1.box.y2) == (100, 120, 140, 160), "x2 and y2 inclusive"
    assert o1.confidence == 0.83, "the box's confidence is kept when the mask has none"
    assert o1.mask.shape == (256, 256) and o1.mask.any() and not o1.mask[:120].any() and not o1.mask[:, :100].any()
    assert o1.mask[120:161, 100:141].sum() == pytest.approx(41 * 41 / 2, rel=0.1)
    o2 = res.objects[1]
    assert (o2.box.x2, o2.box.y2) == (255, 255) and not o2.mask.any() and o2.confidence == 0.2


def test_mask_confidence_wins_and_text_records_are_ignored():
    recs = [
        msp.SegmentationTextRecord(order=0, text="hello"),
        box_record(3, 1, 1, 3, 3, conf=0.5, order=1),
        mask_record(3, (1, 1, 3, 3), 2, 2, conf=0.9, order=2),
    ]
    res = sam_result_from_records(recs, 8, 8, lambda m: bytes([1, 1, 1, 1]))
    assert len(res.objects) == 1 and res.objects[0].confidence == 0.9 and res.objects[0].mask.sum() == 4


def test_parse_sam_events_runs_the_async_parser_on_a_list():
    lane = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
    events = [
        {"type": "response.created"},
        {"type": "response.output_text.delta", "delta": "", **lane},
        {"type": "response.output_text.done", "text": "", **lane},
        {"type": "response.completed", "response": {"status": "completed"}},
    ]
    result = parse_sam_events(events)
    assert result.records == () and result.outcome.status == "completed", "zero matches is a completed stream"
    again = parse_sam_events(events)
    assert again.outcome.status == "completed", "a fresh loop each call"
