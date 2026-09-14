# What a pull request sees

The gate reports in three places. All three come from one evaluation, so they never disagree.

## The comment

One comment per pull request, updated in place on every push, label change, comment and CI
completion. Nothing is collapsed; the order is fixed.

<p align="center"><img src="../../assets/pr-comment.png" alt="The mergeproof comment" width="800"></p>

1. **The scorecard.** One pill per rule, coloured by its worst requirement: green when satisfied,
   amber when something is pending or a warning is open, red when something is missing. The first
   pill is the total.
2. **One sentence.** *4 of 5 requirements satisfied for `40395ea`. To merge:*
3. **Needed / What to do.** Only the requirements that block the merge, each with its status pill
   and the concrete fix. Pending items nobody can act on, such as CI still running, are not listed
   here.
4. **Evidence template.** When a requirement wants something in the PR description, the block to
   paste, with placeholders.
5. **Everything else.** Warnings and satisfied requirements in one table, so the receipt is visible
   too. When all requirements are satisfied this table is the whole comment.

When no rule applies to a change, no comment is posted.

## The commit status

A status named `mergeproof` in the merge box: `4 of 5 requirements satisfied, 1 missing`. This is
the context to require in branch protection. It is `pending` while evidence is outstanding,
`failure` when something is missing, `success` otherwise, and it links to the comment.

Statuses are used rather than check runs on purpose: GitHub evaluates required check runs against
the newest check suite on a commit, and a check run created through the API stays attached to the
first suite, so re-runs and bot-authored PRs could leave the merge box waiting for a check that had
passed. Statuses have no such affinity.

## Review comments on files

What is still needed is also posted where the reader is looking. A missing test lands on the
source file it is missing for. A requirement that applies to the whole change, such as
before/after traces, lands on the first file that made its rule apply, once per rule. Each comment
names the requirement, the rule, whether it blocks, the fix, and the rule's instructions.

Comments are keyed and kept in sync: created when a requirement opens, updated when its text
changes, deleted when it is satisfied. Nothing stale is left behind.

## Job annotations

Inside GitHub Actions, file-level findings are also emitted as workflow commands, so they appear as
annotations on the job and in the diff view, with no extra permissions.

## Locally

`mergeproof explain` prints the same requirements for the working tree, with the evidence template
at the end. `mergeproof template` prints only the template. Exit codes make `mergeproof check`
scriptable: 0 pass, 1 fail, 2 pending, 3 usage error.
