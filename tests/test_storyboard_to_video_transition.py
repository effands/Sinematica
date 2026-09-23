import pytest
from backend.jobs_executor import build_video_reference_ids

def test_build_video_reference_ids_places_storyboard_at_priority_index():
    character_ids = ["char_media_1", "char_media_2"]
    storyboard_id = "sb_media_1"
    
    refs = build_video_reference_ids(
        character_ids=character_ids,
        storyboard_media_id=storyboard_id,
        continuity_media_id=None,
        limit=7
    )
    
    # Storyboard must be in refs
    assert storyboard_id in refs
    # Storyboard is placed at index 0 when no continuity frame
    assert refs[0] == storyboard_id
    assert refs[1] == "char_media_1"
    assert refs[2] == "char_media_2"

def test_build_video_reference_ids_with_continuity_frame():
    character_ids = ["char_media_1"]
    storyboard_id = "sb_media_1"
    continuity_id = "cont_media_0"
    
    refs = build_video_reference_ids(
        character_ids=character_ids,
        storyboard_media_id=storyboard_id,
        continuity_media_id=continuity_id,
        limit=7
    )
    
    assert refs[0] == continuity_id
    assert refs[1] == storyboard_id
    assert refs[2] == "char_media_1"

def test_build_video_reference_ids_respects_max_limit():
    character_ids = [f"char_media_{i}" for i in range(10)]
    storyboard_id = "sb_media_1"
    
    refs = build_video_reference_ids(
        character_ids=character_ids,
        storyboard_media_id=storyboard_id,
        limit=7
    )
    
    assert len(refs) == 7
    assert refs[0] == storyboard_id
