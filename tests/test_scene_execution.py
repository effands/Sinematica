import re

from backend.scene_execution import build_physical_execution_guard, character_sheet_description
from backend.scene_pacing import rewrite_dense_prompt_with_ai
from backend.cinematic_pacing import calculate_pacing_tier, build_story_part_rules


def test_door_guard_keeps_authored_geometry_without_adding_a_door_to_other_scenes():
    scene = {
        'action_summary': 'Sari menutup pintu mobil',
        'start_state': 'Sari outside the rear-left door, right hand on the outer panel',
        'end_state': 'Door latched, Sari outside, both hands free',
        'interaction_plan': {'mechanism': 'hinge at front edge, outward swing', 'active_hand': 'right'},
    }
    guard = build_physical_execution_guard(scene)
    assert scene['start_state'] in guard and scene['end_state'] in guard
    assert 'hinge at front edge, outward swing' in guard
    assert 'clear\nbody, feet and clothing' in guard
    assert 'inner pull or outer panel' in guard
    assert 'one continuous shot' in guard
    assert 'DOOR / VEHICLE' not in build_physical_execution_guard({'action_summary': 'Sari reads a letter'})


def test_ai_rewrite_receives_current_hand_and_mechanism_facts_and_fallback_preserves_them():
    calls = []
    scene = {'start_state': 'left hand on the inner pull', 'end_state': 'door latched, both feet inside',
             'interaction_plan': {'mechanism': 'right hinge, inward swing'}}
    def generator(request, **kwargs):
        calls.append(request)
        raise RuntimeError('offline test')
    output, provider = rewrite_dense_prompt_with_ai('Close the door.', scene, 10, generator=generator)
    assert provider == 'local-guard'
    for text in (calls[0], output):
        assert 'left hand on the inner pull' in text
        assert 'right hinge, inward swing' in text
        assert 'door latched, both feet inside' in text
        assert 'two linked physical actions in every beat' not in text


def test_character_sheet_carries_role_motivation_and_reference_identity_without_mutation():
    character = {'description': 'Sari, oval face, beige pleated dress', 'role': 'protagonis',
                 'motivation': 'protect her daughter', 'body_language': 'upright but hesitant',
                 'expression_range': 'listening, resolve, relief', 'visual_signature': 'low bun'}
    text = character_sheet_description(character)
    assert 'Narrative role: protagonis' in text
    assert 'protect her daughter' in text and 'upright but hesitant' in text
    assert 'listening, resolve, relief' in text and 'low bun' in text
    assert 'reference images take priority' in text
    assert character['description'] == 'Sari, oval face, beige pleated dress'
    antagonist = character_sheet_description({'role': 'antagonis', 'description': 'Bagas, navy batik'})
    assert 'Narrative role: antagonis' in antagonist
    assert 'not permanent scowling' in antagonist


def test_complete_story_can_reach_climax_and_ending_for_short_and_long_counts():
    for count in (1, 2, 3, 4, 6, 10, 25):
        rules = build_story_part_rules(0, count, count)
        assert 'CERITA LENGKAP' in rules
        assert 'happy/sad' in rules
        assert 'DILARANG menyelesaikan konflik utama' not in rules
        assert 'Part bukan film mandiri' not in rules


def test_short_stories_assign_each_scene_once_and_start_at_core_event():
    for count in range(1, 5):
        guide = calculate_pacing_tier(count)['structure_guide']
        assert re.findall(r'- Scene (\d+):', guide) == [str(i) for i in range(1, count + 1)]
        assert 'Langsung' in guide


def test_long_structure_has_no_reversed_overlapping_or_missing_ranges():
    for count in (9, 10, 12, 16, 25, 90, 2000):
        guide = calculate_pacing_tier(count)['structure_guide']
        covered = []
        for start, end in re.findall(r'Scene (\d+)–(\d+):', guide):
            assert int(start) <= int(end)
            covered.extend(range(int(start), int(end) + 1))
        assert covered == list(range(1, count + 1))


def test_last_part_allows_climax_even_when_its_midpoint_precedes_the_climax():
    rules = build_story_part_rules(15, 15, 30, part_number=2)
    assert 'Klimaks utama diizinkan' in rules
    assert 'DILARANG menyelesaikan konflik utama' not in rules
    first = build_story_part_rules(0, 15, 90)
    assert 'DILARANG menyelesaikan konflik utama' in first


def test_vehicle_motion_guard_prevents_unintended_backward_motorcycle_motion():
    scene = {
        'action_summary': 'Aris mengendarai motor melaju meninggalkan rumah',
        'start_state': 'Motor menghadap ke kanan frame, roda depan di kanan, Aris duduk menghadap kanan',
        'end_state': 'Motor bergerak maju ke kanan frame menjauh dari rumah',
    }
    guard = build_physical_execution_guard(scene)
    assert 'VEHICLE MOTION DIRECTION LOCK' in guard
    assert 'Never make a motorcycle or car slide\nbackward' in guard
    assert 'all travel is forward' in guard
    assert 'background parallax moves opposite' in guard


def test_character_sheet_description_forbids_cross_character_wardrobe_swaps():
    text = character_sheet_description({'description': 'Maya memakai blouse hijau dan rok beige'})
    assert 'WARDROBE OWNERSHIP' in text
    assert "Never swap this outfit with another actor" in text
    assert "never dress a male actor in the female character's authored clothing" in text
