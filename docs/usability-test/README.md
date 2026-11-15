# Usability Test Kit — README

This folder contains everything needed to run five moderated usability sessions for the **IntelliRoads Dashboard**.

---

## Files

| File | Purpose |
|---|---|
| `task-script.md` | Facilitator script: greeting, consent reminder, think-aloud instructions, and 8 tasks written in plain language |
| `results-template.md` | Recording sheet — one row per task per participant, plus a per-task summary table |
| `post-test-questionnaire.md` | 5 short follow-up questions and an adapted System Usability Scale (SUS) with scoring formula |
| `problem-fix-log.md` | Running log of problems found, fixes made, and re-test status |
| `consent-and-notes.md` | One-page consent form (voluntary, anonymous, can stop at any time) and free-form facilitator notes sheet |

---

## How to Run the Five Sessions

### Before the first session

1. **Print** `consent-and-notes.md` — one copy per participant (double-sided).
2. **Print** `task-script.md` — one copy for the facilitator to hold.
3. Set up a computer with the dashboard open and logged in with the shared test account.
4. If screen-recording: open OBS / QuickTime / Loom and test it. Confirm recording before each session.

### Session sequence (≈ 30 min per participant)

| Step | Duration | Action |
|---|---|---|
| Welcome and consent | 3 min | Greet participant; they read and sign `consent-and-notes.md` |
| Think-aloud warm-up | 2 min | Ask them to narrate as they open a plain website (e.g. a news site) to get used to thinking aloud |
| Tasks 1 – 8 | 20 min | Work through `task-script.md`; record in `results-template.md` |
| Post-test questionnaire | 4 min | Participant fills `post-test-questionnaire.md` |
| Debrief | 2 min | Open-ended "anything else?" question; fill notes section in `consent-and-notes.md` |

### After all five sessions

1. Total completions per task across all participants.
2. Calculate overall task completion rate (see formula below).
3. Average the five SUS scores.
4. List every distinct problem in `problem-fix-log.md` with severity.
5. Prioritise High-severity problems for fixes before the next sprint.

---

## Success Target

> **90 % of tasks must be completed without facilitator help.**

### Calculation

```
Completion rate (%) = tasks_completed_without_help
                      ÷ (participants × tasks_per_participant)
                      × 100

Example: 36 ÷ (5 × 8) × 100 = 90%
```

Anything below 90 % triggers a review of the failing tasks before the next iteration.

---

## Participant Recruitment Notes

- Aim for participants who are **not** members of the development team.
- A mix of traffic operations familiarity levels (some domain knowledge, some none) is ideal.
- Minimum: 5 participants. Diminishing returns after 8 (Nielsen, 1993).
- Compensate participants if possible (e.g. small gift card) to reduce drop-out.
