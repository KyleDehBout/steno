#!/bin/bash
# Clears one meeting's files from the pipeline folders after its /learn cycle.
#
# Usage: cleanup-cycle.sh "<archived filename>" --stem <stem> [--archive <dir>] [--dry-run]
#
#   <archived filename>  Bare filename of the set of notes just moved into the
#                        issued archive, e.g. "Acme - Meeting Notes #15.docx".
#   --stem <stem>        The meeting's transcript filename without its extension. Only
#                        working/runs/<stem>/, the transcript with that stem and the
#                        output draft named in the run folder's run.txt are deleted.
#   --archive <dir>      Issued archive directory. Defaults to <Meeting Notes>/Archive.
#                        Pass the "Issued archive" path from CLAUDE.md if it differs.
#   --dry-run            Print what would be deleted and delete nothing.
#
# Refuses to delete anything unless the named file is already present and
# non-empty in the issued archive. The archive is the only surviving copy of
# each cycle, so it is verified first and never touched by this script.
#
# Project paths are derived from this script's own location — it lives at
# <project>/<Meeting Notes>/skills/pipeline-cleanup/ — so it needs no editing
# per project and works whatever the Meeting Notes folder is called.
#
# Also refuses while intake/ still holds a file (the archive move should have emptied
# it), or when the stem matches no run folder and no transcript. Other meetings' files
# are left alone, so a meeting processed before this one's /learn survives it.
#
# Before deleting, copies the meeting's transcript and the issued .docx into
# <project>/pipeline-tests/<HELD ON date>/ for /test-pipeline, keeping the newest 8 such
# folders it made (see "Keep the pair" below).
#
# Exit codes: 0 = cleared (or dry run), 1 = archive not confirmed, intake not empty or
# stem matches nothing, 2 = bad usage.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
NOTES="$(cd -- "$SCRIPT_DIR/../.." && pwd)"   # skills/pipeline-cleanup -> Meeting Notes
ROOT="$(dirname -- "$NOTES")"                  # project root

ARCHIVE="$NOTES/Archive"
DRY_RUN=0
ARCHIVED=""
STEM=""

while [ $# -gt 0 ]; do
  case "$1" in
    --archive)
      [ $# -ge 2 ] || { echo "ERROR: --archive needs a directory" >&2; exit 2; }
      ARCHIVE="$2"; shift 2 ;;
    --stem)
      [ $# -ge 2 ] || { echo "ERROR: --stem needs the transcript stem" >&2; exit 2; }
      STEM="$2"; shift 2 ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -*)
      echo "ERROR: unknown option '$1'" >&2; exit 2 ;;
    *)
      [ -z "$ARCHIVED" ] || { echo "ERROR: pass exactly one filename" >&2; exit 2; }
      ARCHIVED="$1"; shift ;;
  esac
done

if [ -z "$ARCHIVED" ]; then
  echo "ERROR: pass the archived filename, e.g. 'Acme - Meeting Notes #15.docx'" >&2
  exit 2
fi

if [ -z "$STEM" ]; then
  echo "ERROR: pass --stem <transcript filename without extension>" >&2
  exit 2
fi

# Guard 1: reject anything that tries to escape the archive or the runs folder.
case "$ARCHIVED" in
  */*|..*) echo "ERROR: expected a bare filename, got '$ARCHIVED'" >&2; exit 2 ;;
esac
case "$STEM" in
  */*|.*) echo "ERROR: expected a bare transcript stem, got '$STEM'" >&2; exit 2 ;;
esac

# Guard 2: the archived file must exist and be non-empty before we delete sources.
if [ ! -s "$ARCHIVE/$ARCHIVED" ]; then
  echo "ERROR: '$ARCHIVED' is not present (or is empty) in:" >&2
  echo "       $ARCHIVE" >&2
  echo "       Nothing deleted — the archive move must succeed first." >&2
  exit 1
fi

# Guard 3: the archive name alone is not proof. A stale name from an earlier cycle
# passes Guard 2, so the intake file must also be gone: Step 6 moves it into the archive.
count_files() { find "$1" -maxdepth 1 -type f ! -name '.*' 2>/dev/null | wc -l | tr -d ' '; }
if [ -d "$NOTES/intake" ] && [ "$(count_files "$NOTES/intake")" -gt 0 ]; then
  echo "ERROR: intake/ still holds a file — the issued final has not been moved to the" >&2
  echo "       archive yet. Nothing deleted." >&2
  exit 1
fi

# Guard 4: the stem must name a meeting this project actually has.
RUN="$NOTES/working/runs/$STEM"
TRANSCRIPT=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  name="$(basename "$f")"
  [ "${name%.*}" = "$STEM" ] && TRANSCRIPT="$f"
done < <(find "$NOTES/transcripts" -maxdepth 1 -type f ! -name '.*' -print 2>/dev/null)
if [ ! -d "$RUN" ] && [ -z "$TRANSCRIPT" ]; then
  echo "ERROR: no run folder and no transcript match stem '$STEM'. Nothing deleted." >&2
  exit 1
fi

echo "Project : $ROOT"
echo "Archive confirmed: $ARCHIVED ($(wc -c <"$ARCHIVE/$ARCHIVED" | tr -d ' ') bytes)"
[ "$DRY_RUN" -eq 1 ] && echo "DRY RUN — nothing will be deleted"
echo

deleted=0

remove() {  # remove <path> <label>
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  would delete  $2"
  else
    rm -rf -- "$1"
    echo "  deleted  $2"
  fi
  deleted=$((deleted + 1))
}

# The output draft is named by date, not by stem, so the run folder records it. A run
# that stopped before Stage 6 records none; then a lone draft is this meeting's only
# when no other meeting has a run folder.
OUTPUT=""
if [ -f "$RUN/run.txt" ]; then
  OUTPUT="$(sed -n 's/^output: *//p' "$RUN/run.txt" | head -1)"
  case "$OUTPUT" in */*|.*) OUTPUT="" ;; esac
fi
others=0
if [ -d "$NOTES/working/runs" ]; then
  others="$(find "$NOTES/working/runs" -mindepth 1 -maxdepth 1 ! -name '.*' ! -name "$STEM" | wc -l | tr -d ' ')"
fi
if [ -z "$OUTPUT" ] && [ "$others" -eq 0 ] \
    && [ "$(count_files "$NOTES/output")" -eq 1 ]; then
  OUTPUT="$(basename "$(find "$NOTES/output" -maxdepth 1 -type f ! -name '.*' -print)")"
fi

# Keep the pair as a /test-pipeline regression case before the transcript goes: the
# transcript and the issued .docx, in <project>/pipeline-tests/<HELD ON date>/ (outside
# Meeting Notes, so no normal run reads it). The date comes from the run's scorecard key;
# without one the folder is named undated-<stem>. Only the newest KEEP_TESTS folders this
# script made are kept. A folder is pruned only when its name matches TEST_NAME and it
# holds the TEST_MARK file this script writes, so hand-picked cases are never touched.
TESTS="$ROOT/pipeline-tests"
KEEP_TESTS=8
TEST_MARK=".from-cleanup"
TEST_NAME='^([0-9]{4}-[0-9]{2}-[0-9]{2}|undated-.+)$'
case "$ARCHIVED" in
  *.docx|*.DOCX) issued_docx=1 ;;
  *) issued_docx=0 ;;
esac
if [ -z "$TRANSCRIPT" ] || [ "$issued_docx" -eq 0 ]; then
  echo "  not kept for testing — needs this meeting's transcript and an issued .docx"
else
  held_on=""
  [ -f "$RUN/scorecard-row.txt" ] && held_on="$(cut -c1-10 "$RUN/scorecard-row.txt" | head -1)"
  if [[ "$held_on" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    case_name="$held_on"; sort_key="$held_on"
  else
    case_name="undated-$STEM"; sort_key="$(date +%Y-%m-%d)"
  fi
  CASE="$TESTS/$case_name"
  if [ -d "$CASE" ] && [ ! -f "$CASE/$TEST_MARK" ]; then
    echo "  not kept for testing — pipeline-tests/$case_name/ exists and was not made here"
  elif [ "$DRY_RUN" -eq 1 ]; then
    echo "  would keep    transcript and issued notes in pipeline-tests/$case_name/"
  else
    # A re-issued meeting replaces its own case; its old baseline no longer applies.
    rm -rf -- "$CASE/transcript" "$CASE/baseline.json"
    mkdir -p "$CASE/transcript"
    cp -p -- "$TRANSCRIPT" "$CASE/transcript/"
    cp -p -- "$ARCHIVE/$ARCHIVED" "$CASE/issued.docx"
    echo "$sort_key" > "$CASE/$TEST_MARK"
    echo "  kept     transcript and issued notes in pipeline-tests/$case_name/"
    kept=0
    while IFS=$'\t' read -r _key old; do
      [ -n "$old" ] || continue
      kept=$((kept + 1))
      if [ "$kept" -gt "$KEEP_TESTS" ]; then
        rm -rf -- "$old"
        echo "  pruned   pipeline-tests/$(basename "$old")/ (keeping the newest $KEEP_TESTS)"
      fi
    done < <(find "$TESTS" -mindepth 1 -maxdepth 1 -type d -print | while IFS= read -r d; do
               [[ "$(basename "$d")" =~ $TEST_NAME ]] && [ -f "$d/$TEST_MARK" ] \
                 && printf '%s %s\t%s\n' "$(head -1 "$d/$TEST_MARK")" "$(basename "$d")" "$d"
             done | sort -r)
  fi
fi

[ -n "$TRANSCRIPT" ] && remove "$TRANSCRIPT" "transcripts/$(basename "$TRANSCRIPT")"
if [ -n "$OUTPUT" ] && [ -f "$NOTES/output/$OUTPUT" ]; then
  remove "$NOTES/output/$OUTPUT" "output/$OUTPUT"
elif [ "$(count_files "$NOTES/output")" -gt 0 ]; then
  echo "  left in place  output/ — no draft recorded for '$STEM'; clear it by hand"
fi
[ -d "$RUN" ] && remove "$RUN" "working/runs/$STEM/"

# render/ and anything else in working/ is shared scratch from the latest render. It
# holds meeting content, so it goes once no other meeting has a run in flight.
if [ "$others" -eq 0 ] && [ -d "$NOTES/working" ]; then
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    [ "$(basename "$entry")" = "runs" ] && continue
    remove "$entry" "working/$(basename "$entry")"
  done < <(find "$NOTES/working" -mindepth 1 -maxdepth 1 ! -name '.*' -print)
fi

# The review form is regenerated every cycle and holds meeting content. It is written
# to whichever folder Claude was started in: the project root, or Meeting Notes/ when
# the launcher starts it there. Clear both.
for form in "$ROOT/qa-session.html" "$NOTES/qa-session.html"; do
  [ -f "$form" ] && remove "$form" "$form"
done

echo
if [ "$DRY_RUN" -eq 1 ]; then
  echo "$deleted file(s) would be cleared. Nothing was deleted."
else
  echo "Cleared $deleted file(s) for '$STEM'. Folders left in place; archive untouched."
fi
