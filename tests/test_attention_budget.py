from src.core.attention_budget import MAX_BUDGET, SPEND_PER_COMMENT, AttentionBudget


class TestCanSpeak:
    def test_starts_empty_cannot_speak_immediately(self):
        budget = AttentionBudget(now=1000.0)
        assert budget.can_speak(now=1000.0) is False

    def test_regenerates_enough_over_time_in_normal_mode(self):
        budget = AttentionBudget(now=1000.0)
        # normal regen: 1 point / 75s
        assert budget.can_speak(now=1000.0 + 75.0) is True

    def test_not_yet_enough_regenerated(self):
        budget = AttentionBudget(now=1000.0)
        assert budget.can_speak(now=1000.0 + 10.0) is False

    def test_nerd_mode_regenerates_faster(self):
        budget = AttentionBudget(now=1000.0)
        assert budget.can_speak(nerd_mode=True, now=1000.0 + 40.0) is True

    def test_nerd_mode_not_ready_at_normal_mode_pace(self):
        budget = AttentionBudget(now=1000.0)
        # Enough for normal mode (75s) but nerd needs less anyway, so this
        # just confirms nerd doesn't need the full normal-mode duration —
        # tested properly via the faster-regen case above. Here: barely
        # under the nerd threshold should still be false.
        assert budget.can_speak(nerd_mode=True, now=1000.0 + 39.0) is False

    def test_gaming_slows_regen(self):
        budget = AttentionBudget(now=1000.0)
        # Would be enough (75s) in normal context but not while gaming
        # (needs 75s / 0.4 = 187.5s).
        assert budget.can_speak(is_game=True, now=1000.0 + 75.0) is False
        assert budget.can_speak(is_game=True, now=1000.0 + 188.0) is True

    def test_idle_speeds_up_regen(self):
        # 75s / 1.6 ≈ 46.9s
        assert AttentionBudget(now=1000.0).can_speak(is_idle=True, now=1000.0 + 47.0) is True
        assert AttentionBudget(now=1000.0).can_speak(is_idle=True, now=1000.0 + 30.0) is False

    def test_budget_is_capped(self):
        budget = AttentionBudget(now=1000.0)
        # A huge time gap must not bank an unbounded budget.
        budget.can_speak(now=1000.0 + 1_000_000.0)
        assert budget._budget == MAX_BUDGET

    def test_can_speak_does_not_spend(self):
        budget = AttentionBudget(now=1000.0)
        budget.can_speak(now=1000.0 + 75.0)
        assert budget.can_speak(now=1000.0 + 75.0) is True  # still affordable, nothing spent


class TestSpend:
    def test_spend_reduces_the_budget(self):
        budget = AttentionBudget(now=1000.0)
        budget.can_speak(now=1000.0 + 75.0)  # regenerate to 1.0
        budget.spend()
        assert budget._budget < SPEND_PER_COMMENT

    def test_spend_never_goes_negative(self):
        budget = AttentionBudget(now=1000.0)
        budget.spend()
        budget.spend()
        assert budget._budget == 0.0

    def test_spend_then_can_speak_is_false_immediately_after(self):
        budget = AttentionBudget(now=1000.0)
        budget.can_speak(now=1000.0 + 75.0)
        budget.spend(now=1000.0 + 75.0)
        assert budget.can_speak(now=1000.0 + 75.0) is False


class TestReset:
    def test_reset_empties_the_budget(self):
        budget = AttentionBudget(now=1000.0)
        budget.can_speak(now=1000.0 + 75.0)
        budget.reset(now=1000.0 + 75.0)
        assert budget.can_speak(now=1000.0 + 75.0) is False
