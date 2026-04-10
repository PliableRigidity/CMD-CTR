from backend.modes.decision.schemas import BrainResponse, FinalVote, VoteSummary


def summarize_votes(
    actions: list[str],
    responses: dict[str, BrainResponse],
) -> VoteSummary:
    vote_counts = {action_id: 0 for action_id in actions}
    vote_counts["ABSTAIN"] = 0
    vote_counts["UNDECIDED"] = 0

    final_votes: dict[str, FinalVote] = {}
    for brain_name, response in responses.items():
        selection = response.selected_action if response.valid else "ABSTAIN"
        if selection not in vote_counts:
            vote_counts[selection] = 0
        vote_counts[selection] += 1
        final_votes[brain_name] = FinalVote(
            brain_name=brain_name,
            selected_action=selection,
            confidence=response.confidence,
        )

    total_votes = len(final_votes)
    majority_decision = "UNDECIDED"

    for action_id in actions:
        if vote_counts[action_id] > total_votes / 2:
            majority_decision = action_id
            break

    return VoteSummary(
        majority_decision=majority_decision,
        vote_counts=vote_counts,
        final_votes=final_votes,
    )
