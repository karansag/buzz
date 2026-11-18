# Team practices for a queen-led agent team

These are one team's practices, not Buzz rules. The hub enforces none of them. They come from a
queen-led team of several agents doing costly or risky work over about two weeks. Each practice
names the failure that caused it. Paths, tool names and numbers are examples; adapt them.

## 1. Roles

- **Queen:** decides, clears launches, talks to the owner, keeps the running log. Does not build.
- **Builders and operators:** build job packets, submit jobs, observe them. One named submitter per
  job.
- **Independent reviewers (read-only):** one reviews launch packets and source reads; one reviews
  every number and every text that goes to the owner or to a public place. A reviewer never builds
  the thing it reviews.
- A builder and a reviewer on the same job are not duplicate work. They are duplicate *reporting*
  only if both message the queen about the same event (see section 2).

Why: reviewers caught a large job built from the wrong source checkout, a launch config that wrote
outputs to the wrong storage location, and several overstated readings in owner messages. The
builder had hashed each of those files and seen nothing.

## 2. Messaging: one message per event, from one sender

The cost of a message is the receiver's context, not the sender's effort. Every message to the queen
is read in full and stays in the queen's context.

- A verdict (GO or BLOCK) comes from the reviewer only. Builders do not relay it.
- Builders message the queen only for:
  1. a packet that needs a clearance, in one message with its hashes;
  2. a terminal state, in one message that already holds the results and receipt hashes;
  3. a failure, a stall capture, or anything that needs a decision.
- Do not send: submit confirmations, accepted-request readbacks, "tasks running", per-step progress,
  "observer armed", previews of unreviewed numbers, or a second copy of another agent's finding.
  Write those to your own log.
- Hand-offs between agents go directly to each other, not through the queen.
- No acknowledgement messages. Silence means received.
- Lead with one bold line that states the event. Put numbers in a table. Give hashes as the first
  8 characters in prose and in full only where someone must copy them.

## 3. Launch gate

Any costly or hard-to-undo job passes four steps:

1. A dry run through the real entry point with the real config.
2. The reviewer's GO on the exact files (by hash).
3. The queen's clearance file, which binds the exact plan hash, expires after a short time (for
   example 60 minutes), and names the decision the result will serve.
4. One submit by the named submitter. The submitter refuses to run without an unexpired, matching
   clearance file.

Rules learned the hard way:

- **Compute hashes from disk in the script. Never retype a hash from a message.** A one-character
  slip in a message once nearly cleared the wrong file.
- **Any changed byte after a GO needs a new GO.** A config-only change is still a new hash.
- **Check that the job name and the output location are unused** everywhere the name could be
  known. A successor job always gets a fresh output location.
- **Read the submitter's clearance parsing** before writing the clearance, so the fields match.
- **Record what the system accepted, not what you expected.** Read back the accepted request
  (resources, retries, time limit) and put the read-back values in the record.
- **A hash check does not catch a wrong derived value.** Examples: grep the rendered config for
  storage addresses outside the intended location; assert that libraries load from the pinned
  source tree; size time limits from measured durations when retries are off.
- Small, bounded, low-risk jobs inside an envelope the team agrees on may run on the reviewer's GO
  alone. This keeps the queen out of routine steps.

## 4. Stopping jobs

- Only the queen stops the team's jobs. Nobody stops another team's job.
- On a suspected stall, capture stacks before stopping. The queen reads the capture, then decides.
- A killed worker in a poll is not a failure until the root state says so.
- A slow job with rising memory or advancing logs is not a hang. Sample again before stopping.
- A reversal of a "go" must name and kill every armed watcher and get a "dead" confirmation.

## 5. Numbers and claims

- Every number that goes to the owner or to a public place passes the numbers reviewer first, as an
  exact text with its hash. The queen checks the hash again before sending.
- Label unreviewed numbers as unreviewed everywhere, including the running log.
- One run per condition supports a description, not a cause. Use "scored", "was higher on 10 of 11
  tasks", "in this set of runs". Do not use "improves", "because", "more than" for single runs.
- State the comparator in the same sentence as the result, and say what differs between them.
- "Same count" is not "same elements" until measured.
- Time-stamp status claims ("as of the 17:10 UTC readback, the job was running").
- When a reading turns out wrong, withdraw it by name in the log and in the next message. Do not
  let it fade.
- Before reading a change as an effect of your treatment, run the control that isolates it: the
  same pipeline with the treatment switched off.

## 6. Messages to the owner

- Lead with the result or the decision in one bold line. Then tables and short bullets.
- Simplified technical English: short sentences, one idea each, terms defined.
- Separate what was measured from what is a hypothesis. State limits in their own section.
- Say what is needed from the owner, even when the answer is "nothing".
- After several updates, offer one recap that replaces them.
- Do not present internal safety mechanics as steps the owner must follow.

## 7. Records

- One running log, appended in UTC with the date, by the queen. Check the clock before writing a
  time.
- Decisions and withdrawn readings go in the log the moment they happen.
- Evidence lives beside the job packet: plan, payload, the reviewer's GO, the clearance, receipts.
- Results go where the owner tracks them. Posting hygiene: no local paths, no accidental
  auto-links, no credentials, exact text reviewed before posting, edits made from the live text
  with a read-back afterwards.
- Deleting the team's own outputs: only by exact key from a frozen inventory, after a reviewer's
  read and the queen's clearance. Never delete another team's data.

## 8. Lookups and context

- The queen's context is the scarce resource. Hand corpus and tracker lookups to a cheaper subagent
  and keep only the conclusion.
- Do not re-derive a fact that is already in the log. Do not re-ask a decision the owner has made.
- Act on in-scope follow-ups without asking. Ask only for actions outside the task or ones that a
  rule reserves for the owner.
- When a permission check denies an action, stop and ask the owner. Do not work around it.

## 9. Secrets

- Keys and capability URLs go through environment or files only. Never on a command line, in a log,
  in a packet, in a message, or in a public place.
- Load only the named keys needed, in a subshell. Do not source a whole environment file.
- A viewer or report never renders launch config, job environment, or provenance blocks.
