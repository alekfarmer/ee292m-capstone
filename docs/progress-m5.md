# Progress log: review round 5 and M5

EE292M capstone, *C to Gates*. This log covers the fixes from review round 5
(lrusso3, PR #13) and milestone M5, user-entered C. Both were built on one
branch, `m5-user-c`, from `main` after PR #13. As before, I worked with
Claude Code as the coding agent, following `AGENTS.md`: plan first, approval
before work, everything through the Makefile.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-11-08 | Plan approved: one branch for round 5 and M5; a committed example that runs every RV32I instruction; a tight limit on program size rather than a build queue. Built, tested, regression-checked and pushed |

## Round 5

- **The C source ran outside its box.** The C list was the only code pane
  not inside a scroll container. It now is, so a long line scrolls sideways
  instead of wrapping, which would break the code's layout. Seen failing
  first: `tests/test_page_layout.py` reported `['c-lines']`.
- **A drawing of the repository's structure.** The README now points to the
  annotated Layout section of ARCHITECTURE.md rather than keeping a copy.
- **Line endings on Windows.** Most likely a checkout from before
  `.gitattributes`; `tests/test_portability.py` already names that cause.

## Decisions

- **Synchronous builds, limited by size.** A live build (compile, Spike,
  gate level, RTL, every check) of a small program takes about 0.8 s, so the
  POST answers when the build is done. A program may be up to 2000 bytes
  and 60 lines and must halt within 500 instructions. There is no job queue
  and no progress state.
- **A program is named after its source.** `u_` plus 16 hex digits of the
  SHA-256 of the source (with LF line endings). The same source is built
  once, a link to it keeps working while the server keeps it, and a name
  can never point at another user's program.
- **Built aside, moved into place.** A user program is built into
  `backend/build/user/.staging/<name>/` and moved to `backend/build/user/` only
  after every check passes, so a rejected or half-built program is never
  served. The 32 most recently used are kept; one build runs at a time (a
  second gets a 503).
- **`tour.c` closes the decoder blind spot.** The decoders have no
  spot-check model, so they are checked only by Spike, and only on the
  instructions a program runs. `tour.c` runs all 37 RV32I instructions the
  core has, with operands where the signed and unsigned answers differ for
  `sltu`, `sltiu` and `sra`. Its result (a0 = 157845) was worked out by hand
  before Spike ran it. GCC at `-Og` reads a volatile `short` or `char` with
  `lhu`/`lbu` plus shifts, so `lh` and `lb` come from plain arrays; `bne` comes
  from a `!=` loop, since GCC turned every `if (a != b)` around.
- **No editor library.** The editor is a `<textarea>`. Syntax highlighting
  was not worth a dependency.

## Security: source that reads another file

The subset check runs gcc's preprocessor on the source first. With user
input, `#include "/work/.env"` would be read, and gcc's error lines quote
what they read. A probe showed `SECRET_TOKEN` and part of its value in the
message. `asm(".incbin ...")` would copy a file's bytes into the program
image. Now `software.check_source_text` refuses, before any tool sees the
source:
- `#` anywhere, comments included, and its other spellings `%:` (digraph)
  and `??=` (trigraph);
- inline assembly (`asm`, `__asm`, `__asm__`, also when split by a
  backslash-newline), outside comments and strings;
- `_Pragma`.

Seen failing first: the seven cases in `test_source_cannot_read_another_file`.
Each now checks that the secret's text is not in the message.

## Tests

- `tests/test_coverage.py`: the committed programs run every RV32I
  instruction. Seen failing first: 28 missing with `sum.c` alone, then
  `bne, lb, lh` with the first `tour.c`.
- `tests/test_user_programs.py`: six accepted programs with results worked out
  by hand (Fibonacci, array maximum, recursion, shift-and-add multiply, bit
  count, `char` + `short`); size, line and character limits; rejected
  programs leave nothing behind; the same source is built once; one build at
  a time; old programs are removed. Seen failing first (no
  `build_user_program`).
- `tests/test_api.py`: POST builds and the GETs serve the result; 422 with
  one plain message; the body is validated (missing, empty, too long, extra
  fields); 503 while another build runs. Seen failing first (405).
- `make smoke` builds a typed program through the API, checks a0 = 10 (4 + 3 +
  2 + 1), and checks that the page at `#program=<name>` shows its source, lights
  its start line and shows no error. Seen failing on the new plant
  `typed_program_not_opened`.

## Regression key

12 plants, all behaving as the key says:
- `sra_as_srl` and `sltu_decoded_as_slt` are now caught at `make artifacts`,
  because `tour.c` runs those instructions. `sltu` was the known blind spot.
- New, so that each stage still has a plant only it catches:
  `sh_upper_half_as_lower` (caught at tests by the LSU model) and
  `sra_wrong_on_small_negatives` (caught only by the spot-check, in a `tour.c`
  cycle that is not a shift).
- New: `typed_program_not_opened` (smoke).
- The new known blind spot is `bgeu_as_bge`. `tour.c`'s one `bgeu` compares
  two positive numbers, so running every instruction is not testing every
  case.

## Known limits

- **A typed program is not spot-checked.** It passes the build's checks
  (gate level = RTL on every signal, every instruction vs Spike, the halt),
  but `make spot-check` runs only over the committed programs.
- **The editor's buttons are not driven by a test.** Headless Chromium here
  can dump the DOM or take a screenshot, but cannot type or click. The smoke
  check covers the API call and the page showing the result, not the form.
  I did not click through it in a real browser.
- **A `#` in a comment is refused.** This is deliberately blunt: no lexer
  stands between the source and the preprocessor.
- **The request body is read whole before it is validated.** FastAPI reads
  the whole body before checking its length; the app listens only on
  127.0.0.1.
