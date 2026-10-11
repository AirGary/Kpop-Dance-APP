import pytest

from stage_lab_analysis.fancam_demo.mask_reseed import propagate_with_reseeds


class Predictor:
    """Exercise orchestration against the predictor's inclusive range contract."""
    def __init__(self):
        self.events = []

    def reset_state(self, state):
        state.clear()
        self.events.append(('reset',))

    def add_new_points_or_box(self, state, *, frame_idx, obj_id, box):
        state['seed'] = frame_idx
        self.events.append(('seed', frame_idx, obj_id, box))

    def propagate_in_video(self, state, *, start_frame_idx, max_frame_num_to_track):
        assert state['seed'] == start_frame_idx
        for i in range(start_frame_idx, start_frame_idx+max_frame_num_to_track+1):
            yield i, [1], 'mask'


def test_reseed_clears_memory_and_covers_each_frame_once():
    model = Predictor()
    result = list(propagate_with_reseeds(model, {}, {0: 'opening', 3: 'B recovered', 6: 'B again'}, 8))
    assert [r[0] for r in result] == list(range(8))
    assert model.events == [('seed', 0, 1, 'opening'), ('reset',),
                            ('seed', 3, 1, 'B recovered'), ('reset',),
                            ('seed', 6, 1, 'B again')]


def test_no_recovery_keeps_original_memory():
    model = Predictor()
    assert len(list(propagate_with_reseeds(model, {}, {0: 'opening'}, 4))) == 4
    assert model.events == [('seed', 0, 1, 'opening')]


@pytest.mark.parametrize('prompts', [{}, {2: 'late'}, {0: 'ok', 4: 'outside'}])
def test_invalid_prompt_schedule_is_rejected_before_model_calls(prompts):
    model = Predictor()
    with pytest.raises(ValueError):
        list(propagate_with_reseeds(model, {}, prompts, 4))
    assert model.events == []
