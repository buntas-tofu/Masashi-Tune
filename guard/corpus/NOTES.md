# Synthetic corpus, authored for this repository

Every file under this directory is SYNTHETIC. Each sample was written for this
repository during the public build, clearly synthetic, and contains no real
payloads, no workplace strings, no agency wording, and no personal or
deployment identifiers. Nothing here is drawn from any real corpus, estate,
incident, or operation.

The corpus exists so the guard can be measured in both directions without
shipping anything real:

- `attacks/`  18 clearly synthetic prompt-injection style samples. Each is a
  short payload of the shape real operators screen against: direct overrides,
  overrides embedded in a document, schema rewrites, roleplay and persona
  adoption, zero-width character attacks, bidirectional overrides, multilingual
  and late-document payloads. The file name is the case name and the body is
  the payload.
- `benign/`  10 plain administrative prose documents that legitimately contain
  words like override, instruction, disregard and system. These are the hard
  negatives: a screen must tell a policy document about overriding a procedure
  apart from an instruction to override its own.
- `template/`  one synthetic review cover sheet, the allowlist template family.
  It reads structurally like instruction override because it is a form full of
  imperative instructions to a human reviewer.

The allowlist markers in promptguard_service.py were re-authored to match this
template family (synthetic generic markers, no agency strings). The template
file is the control document for the allowlist adversarial controls in
guard_eval.py.

Nothing in this corpus is quoted from or derived from any other source.

One housekeeping note: four samples carry report-shaped names by design (the
review cover sheet template and three administrative documents under
benign/). The repository linter therefore reports four status-line warnings
against them. That is expected. The samples exist to be screened, not to
satisfy document conventions, and those four warnings are stable and known.
