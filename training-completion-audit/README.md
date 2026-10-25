# Training Completion Eligibility Audit

An offline Python 3.10+ tool that reviews **fictional learner records**
against transparent training-completion rules. Uses standard-library
CSV and `decimal.Decimal` only.

## Practical task

Course administrators may need to issue completion certificates only
when a participant meets both an attendance requirement and a quiz
threshold. This demo uses an example policy:

- Attend **at least 80%** of scheduled sessions.
- Achieve **at least 70.00%** on the quiz.
- All counts must be integers; total sessions must be positive.
- Attendance cannot exceed scheduled sessions.
- Scores must be finite, between 0 and 100, to two decimal places.
- Repeated participant IDs (case-insensitive) are flagged.

This is a fictional policy, not a claim about any real education provider.

Input CSV has columns:

```text
participant_id,sessions_attended,sessions_total,quiz_percent
```

The program creates a **completion report** for valid records and a
separate **errors report** for invalid input rows. Not meeting the
policy is a valid outcome, not an input error.

## Run

```sh
python3 audit.py sample_attendance.csv completions.csv errors.csv
python3 -m unittest discover -s tests -v
```

The report contains attendance percent, quiz score, eligibility Boolean,
and explicit reasons for ineligibility. Exit status: 0 all rows valid,
1 malformed/duplicate rows, 2 file or schema error.

## Implementation notes

Attendance eligibility compares `5 * attended >= 4 * total`
using exact integers. This avoids rounding an attendance percentage
across a threshold. Reported percentages use decimal rounding for display.
Average runtime is O(n) with O(n) memory for output and deduplication.

## Limitations and extension

This code does not verify enrollment or training attendance evidence.
Add a configurable policy file, detailed attendance dates and certificate
generation only after business rules and access controls are defined.
