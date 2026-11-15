# Usability Test Task Script

**Study title:** IntelliRoads Dashboard Usability Evaluation  
**Version:** 1.0  
**Facilitator:** ___________________  
**Date:** ___________________  
**Participant ID:** P__ (do not record real names)

---

## Facilitator Guide

### Before the session

1. Open the dashboard in a fresh browser window, logged in with the test account.
2. Set the browser to full-screen. Close all other tabs.
3. Have a timer (phone or stopwatch) ready to record per-task duration.
4. Have a copy of the results template open to take notes.
5. Confirm screen-recording software is running (or note that it is not, if consent was not given).

### Greeting (read aloud)

> "Thank you for taking part in this study. We are testing the **traffic dashboard**, not you — there are no right or wrong answers. If anything is confusing, that is information for us to improve it.  
> Please think aloud as you work: tell me what you see, what you are trying to do, and what surprises you. I will not give hints, but I can confirm whether a task is finished.  
> You may stop at any time for any reason. Do you have any questions before we start?"

### Consent check

Ask the participant to sign the consent form (see `consent-and-notes.md`) **before** the session begins. If they prefer not to be recorded, stop the recorder.

### "Think aloud" reminder

Remind the participant at least once during the session if they go quiet for more than 20 seconds:
> "Can you tell me what you are thinking right now?"

### After each task

- Note **completed** (yes/no), **time**, any **errors**, and direct **quotes**.
- Do **not** tell the participant whether they were right or wrong until after all tasks.
- Record severity (Low / Medium / High) based on the impact on the user goal.

### No-hints rule

- Never point at the screen, say "try clicking there," or give directional hints.
- You may read the task again if asked, or confirm "yes, that is what I am looking for."
- If a participant is completely stuck for more than 3 minutes, record a failure and move on.

---

## Tasks

Each task is written as it would be spoken to a non-technical participant. Read each task aloud and hand the participant the printed card if they prefer.

---

### Task 1 — Overall traffic health

> "Look at the main screen. Without clicking anything yet, tell me: **is traffic flowing normally right now, or is there a problem?** How can you tell?"

**Success criterion:** Participant correctly identifies the network status (flowing / congested / degraded) from the status banner or KPI cards on the Home page.

---

### Task 2 — Busiest junction

> "One junction is currently handling the most traffic. **Which junction is it, and roughly how many vehicles are there?**"

**Success criterion:** Participant names the correct junction (e.g. "Junction A — Northwest") using the junction cards or the Traffic Map page.

---

### Task 3 — Traffic light state and reason

> "Pick any junction on the Traffic Map. **Tell me what colour the traffic light is on right now, how many seconds are left, and why the system chose that timing.**"

**Success criterion:** Participant reads the current phase colour, the countdown, and the signal reason (density level or mode) from the map side panel or Signal Status widget.

---

### Task 4 — Switch to Smart AI and back

> "The dashboard has two control modes. **Switch to Smart AI mode**, then switch back to Standard timing. Tell me how you know the change worked."

**Success criterion:** Participant uses the Standard timing / Smart AI toggle, observes the confirmation or badge change, and switches back without an error page.

---

### Task 5 — Past warnings from today

> "Traffic warnings are stored for review. **Go to Past warnings and find at least one warning that happened today.** What junction was it at and what triggered it?"

**Success criterion:** Participant navigates to Alert History, applies or reads the time filter, and reads one alert row (junction name + what happened).

---

### Task 6 — Change a warning limit and cancel

> "Warning limits decide when the system raises an alarm. **Go to Settings, find the warning limit for any junction, change the number to something different, then cancel the change** without saving it."

**Success criterion:** Participant reaches the Settings page, edits a threshold field, clicks Cancel or Revert, and verifies the original value is restored.

---

### Task 7 — Download a report

> "The team needs a copy of today's performance data. **Download a report** in any format the system offers."

**Success criterion:** Participant navigates to the Reports page, selects a time window, and successfully triggers a file download (PDF or CSV).

---

### Task 8 — Glossary look-up

> "There is a built-in glossary of traffic terms. **Find out what the glossary says about 'Smart AI'** (or 'DQN' — they may be listed together)."

**Success criterion:** Participant opens the Glossary (from the Home page button), locates the DQN / Smart AI entry, and reads or summarises its plain-language description.

---

## Closing

After all tasks are done:

1. Administer the **Post-Test Questionnaire** (`post-test-questionnaire.md`).
2. Ask: *"Was there anything you expected to find that you could not?"*
3. Thank the participant.
4. Stop recording.
