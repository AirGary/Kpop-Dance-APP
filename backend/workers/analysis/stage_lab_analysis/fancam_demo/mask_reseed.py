"""Segment propagation using caller-validated identity recovery prompts only."""


def propagate_with_reseeds(model, state, prompts, frame_count):
    indices = sorted(prompts)
    if (frame_count < 1 or not indices or indices[0] != 0
            or any(not isinstance(i, int) or i < 0 or i >= frame_count for i in indices)):
        raise ValueError('prompt schedule must start at zero and stay inside video')
    for position, start in enumerate(indices):
        end = indices[position+1] if position+1 < len(indices) else frame_count
        if position:
            # A recovered identity must not inherit the occluder's mask memory.
            model.reset_state(state)
        model.add_new_points_or_box(state, frame_idx=start, obj_id=1, box=prompts[start])
        yield from model.propagate_in_video(
            state, start_frame_idx=start, max_frame_num_to_track=end-start-1)
