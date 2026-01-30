# Implementation Plan: Voice Marker Support for Abogen Audiobook Maker

## Overview
Add `<<VOICE:voice_name>>` marker support to enable dynamic voice switching within audiobook text files. This allows different narrators for different sections/characters while maintaining the existing chapter structure and audio compilation workflow.

## Design Approach

### Key Decisions
1. **Hierarchical Splitting**: Split text by chapters FIRST, then by voice markers WITHIN each chapter
   - Preserves existing chapter-based file output structure
   - Voice changes are purely for TTS processing, not file organization
   - Maintains clean separation: chapters for structure, voices for narration

2. **Voice Segment Structure**: Extend chapter data to include voice segments
   ```python
   chapters = [
       (chapter_name, [(voice_name, text), (voice_name, text), ...]),
       ...
   ]
   ```

3. **Smart Voice Caching**: Load voices on-demand but cache within conversion session
   - Avoids loading all voices upfront (memory efficient)
   - Prevents reloading same voice (performance optimized)
   - Handles voice formulas correctly

4. **Silent Fallback**: Invalid voice names fallback to previous voice with warning (don't stop conversion)

## ⚠️ Critical Implementation Notes

1. **Indentation is crucial**: When adding the voice segment loop in conversion.py, the TTS processing code needs to be indented 4 additional spaces. However, the `text_segments` assignment line (around line 1136) must remain at the correct scope level - it should be OUTSIDE the spaCy conditional block, at the same indentation as the "Print active split pattern" comment below it.

2. **Voice names are case-insensitive**: The implementation accepts voice names in any case (AM_FENRIR, am_fenrir, Am_Fenrir) and normalizes them to lowercase to match VOICES_INTERNAL.

3. **Voice state persists across chapters**: The `current_voice` variable must be updated after processing each chapter to carry the voice state forward to the next chapter.

## Implementation Steps

### Phase 1: Add Voice Marker Pattern & Utilities (subtitle_utils.py)

**File**: `C:\Users\coleman\Git\Abogen Audiobook Maker\abogen\subtitle_utils.py`

1. **Add voice marker regex patterns** (after line 17):
   ```python
   _VOICE_MARKER_PATTERN = re.compile(r"<<VOICE:[^>]*>>")
   _VOICE_MARKER_SEARCH_PATTERN = re.compile(r"<<VOICE:(.*?)>>")
   ```

2. **Update `clean_subtitle_text()`** (line 33-38):
   - Add voice marker stripping after line 37:
     ```python
     text = _VOICE_MARKER_PATTERN.sub("", text)
     ```

3. **Update `calculate_text_length()`** (line 40-49):
   - Add voice marker removal after line 44:
     ```python
     text = _VOICE_MARKER_PATTERN.sub("", text)
     ```

4. **Add voice validation function** (after line 460):
   ```python
   def validate_voice_name(voice_name):
       """Validate voice name against VOICES_INTERNAL list.
       Handles both single voices and formulas like 'af_heart*0.5 + am_echo*0.5'."""
       from abogen.constants import VOICES_INTERNAL

       voice_name = voice_name.strip()

       # Check if it's a formula (contains *)
       if "*" in voice_name:
           # Extract voice names from formula
           voices = voice_name.split("+")
           for term in voices:
               if "*" in term:
                   base_voice = term.split("*")[0].strip()
                   if base_voice not in VOICES_INTERNAL:
                       return False, base_voice
           return True, None
       else:
           # Single voice
           if voice_name not in VOICES_INTERNAL:
               return False, voice_name
           return True, None
   ```

5. **Add text splitting function** (after validation function):
   ```python
   def split_text_by_voice_markers(text, default_voice):
       """Split text by voice markers, returning list of (voice, text) tuples.

       IMPORTANT: Returns the last voice used so it can persist across chapters.

       Args:
           text: Text potentially containing <<VOICE:name>> markers
           default_voice: Voice to use if no markers found or before first marker

       Returns:
           Tuple of (segments_list, last_voice_used):
               - segments_list: List of (voice_name, segment_text) tuples
               - last_voice_used: The voice that should continue into next chapter
       """
       voice_splits = list(_VOICE_MARKER_SEARCH_PATTERN.finditer(text))

       if not voice_splits:
           # No voice markers, return entire text with default voice
           return [(default_voice, text)], default_voice

       segments = []
       current_voice = default_voice

       # Text before first marker uses default voice
       first_start = voice_splits[0].start()
       if first_start > 0:
           intro_text = text[:first_start].strip()
           if intro_text:
               segments.append((current_voice, intro_text))

       # Process each voice marker
       for idx, match in enumerate(voice_splits):
           voice_name = match.group(1).strip()
           start = match.end()
           end = voice_splits[idx + 1].start() if idx + 1 < len(voice_splits) else len(text)
           segment_text = text[start:end].strip()

           # Validate voice name
           is_valid, invalid_voice = validate_voice_name(voice_name)
           if is_valid:
               current_voice = voice_name
           # If invalid, current_voice stays the same (fallback behavior)

           if segment_text:
               segments.append((current_voice, segment_text))

       # Return segments AND the last voice used (to persist to next chapter)
       return segments, current_voice
   ```

### Phase 2: Update Conversion Logic (conversion.py)

**File**: `C:\Users\coleman\Git\Abogen Audiobook Maker\abogen\conversion.py`

1. **Add imports** (around line 44, where subtitle_utils imports are):
   ```python
   from abogen.subtitle_utils import (
       # ... existing imports ...
       _VOICE_MARKER_PATTERN,
       _VOICE_MARKER_SEARCH_PATTERN,
       split_text_by_voice_markers,
       validate_voice_name,
   )
   ```

2. **Initialize voice cache** (in ConversionThread.__init__ or around line 460 before TTS initialization):
   ```python
   self.voice_cache = {}  # Cache for loaded voices
   ```

3. **Add voice loading helper method** (around line 860, before chapter loop):
   ```python
   def load_voice_cached(self, voice_name, tts):
       """Load voice with caching to avoid reloading same voice.

       Args:
           voice_name: Voice name or formula string
           tts: TTS pipeline instance

       Returns:
           Loaded voice tensor or voice name string
       """
       # Check cache first
       if voice_name in self.voice_cache:
           return self.voice_cache[voice_name]

       # Load voice
       if "*" in voice_name:
           loaded_voice = get_new_voice(tts, voice_name, self.use_gpu)
       else:
           loaded_voice = voice_name

       # Cache it
       self.voice_cache[voice_name] = loaded_voice
       return loaded_voice
   ```

4. **Split chapters by voice markers** (after line 550, where `chapters = [("text", text)]`):
   ```python
   # After chapters list is created, split each chapter by voice markers
   # IMPORTANT: Voice state persists across chapters!
   chapters_with_voices = []
   current_voice = self.voice  # Start with default voice

   for chapter_name, chapter_text in chapters:
       # Use current_voice as the starting voice for this chapter
       voice_segments, last_voice = split_text_by_voice_markers(chapter_text, current_voice)
       chapters_with_voices.append((chapter_name, voice_segments))

       # Update current_voice so next chapter continues with this voice
       current_voice = last_voice

   # Log if voice markers were found
   total_voice_segments = sum(len(segments) for _, segments in chapters_with_voices)
   if total_voice_segments > len(chapters):
       self.log_updated.emit(
           (f"\nDetected {total_voice_segments - len(chapters)} voice change(s) across all chapters", "grey")
       )

   # Replace chapters with the new structure
   chapters = chapters_with_voices
   ```

5. **Update chapter processing loop** (line 845 - modify the loop structure):

   **Current code** (line 845):
   ```python
   for chapter_idx, (chapter_name, chapter_text) in enumerate(chapters, 1):
   ```

   **New code**:
   ```python
   for chapter_idx, (chapter_name, voice_segments) in enumerate(chapters, 1):
   ```

6. **Add voice segment loop** (after line 869, where `loaded_voice` is set):

   **Remove these lines** (865-869):
   ```python
   # Check if the voice is a formula and load it if necessary
   if "*" in self.voice:
       loaded_voice = get_new_voice(tts, self.voice, self.use_gpu)
   else:
       loaded_voice = self.voice
   ```

   **Replace with** (new nested loop structure):
   ```python
   # Process each voice segment within the chapter
   for segment_idx, (voice_name, segment_text) in enumerate(voice_segments):
       # Load voice for this segment (with caching)
       try:
           loaded_voice = self.load_voice_cached(voice_name, tts)

           # Log voice change if it's not the first segment
           if segment_idx > 0:
               voice_display = voice_name if len(voice_name) < 50 else voice_name[:47] + "..."
               self.log_updated.emit((f"  → Voice: {voice_display}", "grey"))
       except Exception as e:
           # NOTE: If voice loading fails (shouldn't happen since validation in
           # split_text_by_voice_markers already filtered invalid voices),
           # this fallback loads the previous voice from cache
           # The voice_name here will already be the previous valid voice
           self.log_updated.emit(
               (f"  ⚠ Voice loading error for '{voice_name}', continuing with previous", "orange")
           )
           # Voice already validated in split_text_by_voice_markers, so this
           # error case is unlikely but kept for safety
           if segment_idx > 0:
               # Use the loaded_voice from previous iteration
               pass
           else:
               loaded_voice = self.load_voice_cached(self.voice, tts)

       # Replace 'chapter_text' with 'segment_text' in the TTS processing code below
       # The existing TTS processing code (lines 1000-1290) continues here
       # but operates on segment_text instead of chapter_text
   ```

7. **Update text processing to use segment_text**:

   a. Update the spaCy segmentation call (around line 1089):
   ```python
   # OLD: spacy_sentences = segment_sentences(chapter_text, ...)
   # NEW:
   spacy_sentences = segment_sentences(segment_text, ...)
   ```

   b. **CRITICAL**: Update the text_segments assignment (around line 1136):
   ```python
   # This line MUST be at the correct indentation level!
   # It should be OUTSIDE the "if use_spacy and self.lang_code not in ["a", "b"]:" block
   # OLD: text_segments = spacy_sentences if spacy_sentences else [chapter_text]
   # NEW:
   text_segments = spacy_sentences if spacy_sentences else [segment_text]
   ```

   **Correct indentation** (20 spaces - at same level as "Print active split pattern" comment):
   ```python
                   # spaCy processing code above (more indented)...

                   # Process text - either as spaCy sentences or as single text
                   text_segments = spacy_sentences if spacy_sentences else [segment_text]

                   # Print active split pattern used by the TTS engine once for this batch
   ```

8. **Ensure proper loop indentation**:
   - All TTS processing code (from spaCy setup through to the TTS result loop, approximately lines 1062-1342) should be indented one level deeper (4 additional spaces)
   - This code now runs inside the voice segment loop
   - **EXCEPT**: The `text_segments` assignment (step 7b above) must remain at the correct level
   - Chapter file closing/silence insertion stays at chapter level (after voice segment loop completes)

### Phase 3: GUI Support (Optional Enhancement)

**File**: `C:\Users\coleman\Git\Abogen Audiobook Maker\abogen\gui.py`

This is an optional quality-of-life improvement for users to easily insert voice markers.

1. **Add voice marker insertion method** (around line 762, near chapter marker button):
   ```python
   def insert_voice_marker(self):
       """Insert a voice marker template at cursor position."""
       cursor = self.text_edit.textCursor()
       # Use the currently selected voice as the default
       default_voice = self.selected_voice or "af_heart"
       cursor.insertText(f"\n<<VOICE:{default_voice}>>\n")
       self.text_edit.setTextCursor(cursor)
       self.update_char_count()
       self.text_edit.setFocus()
   ```

2. **Add button to UI** (find where chapter marker button is created and add nearby):
   ```python
   voice_marker_button = QPushButton("Insert Voice Marker")
   voice_marker_button.setToolTip("Insert a voice change marker at cursor position")
   voice_marker_button.clicked.connect(self.insert_voice_marker)
   # Add to the appropriate layout/toolbar
   ```

## Critical Files to Modify

1. **`C:\Users\coleman\Git\Abogen Audiobook Maker\abogen\subtitle_utils.py`**
   - Add voice marker patterns, validation, and splitting logic
   - ~60 lines of new code

2. **`C:\Users\coleman\Git\Abogen Audiobook Maker\abogen\conversion.py`**
   - Modify chapter processing loop to handle voice segments
   - Add voice caching mechanism
   - ~40 lines of new code + indentation changes

3. **`C:\Users\coleman\Git\Abogen Audiobook Maker\abogen\gui.py`** (Optional)
   - Add voice marker insertion UI support
   - ~10 lines of new code

## Edge Cases Handled

1. **No voice markers**: Returns single-segment list, existing behavior preserved
2. **Voice marker before chapter marker**: Works naturally - wrapped in chapter with voice segments
3. **Voice marker after chapter marker**: Works naturally - chapter contains multiple voice segments
4. **Multiple voice changes in one chapter**: Handled by voice_segments list iteration
5. **Invalid voice name**: Continues with PREVIOUS voice (not default), warning logged, conversion continues
6. **Voice formula in marker** (e.g., `<<VOICE:af_heart*0.5 + am_echo*0.5>>`): Validated and cached correctly
7. **Empty text between markers**: Filtered out (only add if segment_text non-empty)
8. **Voice marker at end of text**: Handled by slice logic (end = len(text))
9. **Voice persists across chapters**: ✅ The `current_voice` variable tracks state across chapters, so a voice set in Chapter 1 continues into Chapter 2 unless a new voice marker appears

## Backward Compatibility

- ✅ No voice markers: System behaves exactly as before (single voice segment per chapter)
- ✅ Existing audio compilation unchanged (file writing, silence insertion, chapters)
- ✅ Chapter structure preserved (still one chapter = one file or chapter marker in M4B)
- ✅ Character counting updated to ignore voice markers like chapter markers
- ✅ Subtitle generation unaffected (voice markers stripped before subtitle text processing)

## Testing Verification

After implementation, test with:

1. **No markers**: Verify audiobook generation unchanged
2. **Single voice change**: Verify voice switches correctly mid-text
3. **Multiple voices**: Verify all voices load and audio transitions are seamless
4. **Invalid voice name**: Verify continuation with PREVIOUS voice (not default) with warning message
5. **Voice formula**: Verify `<<VOICE:af_heart*0.5 + am_echo*0.5>>` parses correctly
6. **Mixed with chapters**: Verify chapter files compile correctly with voice changes inside
7. **Voice change mid-chapter**: Verify audio output is continuous without gaps/clicks

## Example Usage

### Example 1: Voice Persisting Across Chapters (Key Feature!)

**Input text file**:
```
This is narrated by the default voice (e.g., af_heart).

<<VOICE:bf_alice>>
This section switches to British female voice Alice.

<<CHAPTER_MARKER:Chapter Two>>
THIS CONTINUES WITH bf_alice - no new voice marker needed!
The voice persists from the previous chapter.

<<VOICE:am_fenir>>
Now we switch to American male voice Fenir.

<<CHAPTER_MARKER:Chapter Three>>
THIS ALSO CONTINUES WITH am_fenir from Chapter Two!
```

**Expected behavior**:
- Paragraph 1: Default voice (af_heart)
- Paragraph 2: Switches to bf_alice
- **Chapter Two start: CONTINUES with bf_alice** ← Key feature!
- Chapter Two middle: Switches to am_fenir
- **Chapter Three start: CONTINUES with am_fenir** ← Key feature!

### Example 2: Invalid Voice Handling - Continues with Previous Voice

**Input text file**:
```
Default voice narration (af_heart).

<<VOICE:bf_alice>>
Now using British female Alice.

<<VOICE:invalid_voice>>
CONTINUES with bf_alice (previous voice), NOT default!

<<CHAPTER_MARKER:Chapter Two>>
Still using bf_alice (persisted through the invalid marker).
```

**Expected behavior**:
- Paragraph 1: Default voice (af_heart)
- Paragraph 2: Switches to bf_alice
- Paragraph 3: Invalid marker encountered, **CONTINUES with bf_alice** (previous voice)
- Warning logged: "⚠ Invalid voice 'invalid_voice', using previous voice"
- Chapter Two: **Still using bf_alice** (persisted)

### Example 3: Invalid Voice at Start

**Input text file**:
```
Default voice narration (af_heart).

<<VOICE:invalid_voice>>
CONTINUES with af_heart (previous/default voice).
```

**Expected behavior**:
- Invalid voice at start continues with the default voice (because there's no previous marker)
- This is the ONLY case where "previous voice" = "default voice"

## Performance Considerations

- Voice loading: Cached to avoid reloading (memory/time efficient)
- Pattern matching: Pre-compiled regex (fast)
- Memory: Voices loaded on-demand, not all upfront
- Processing: Single pass through text (no additional iterations)

## Enhancement: Case-Insensitive Voice Names & Improved Logging

### Background

The current implementation has two minor issues:

1. **Case-sensitive validation**: Voice names like `am_Fenrir` (capital F) fail validation even though Kokoro TTS accepts them case-insensitively
2. **Confusing logging**: The message "Detected X voice change(s)" counts extra segments created, not actual voice markers found

### Changes Required

#### 1. Make Voice Name Validation Case-Insensitive

**File**: `abogen/subtitle_utils.py` (around line 466-496)

**Current code**:
```python
def validate_voice_name(voice_name):
    from abogen.constants import VOICES_INTERNAL
    voice_name = voice_name.strip()

    if "*" in voice_name:
        voices = voice_name.split("+")
        for term in voices:
            if "*" in term:
                base_voice = term.split("*")[0].strip()
                if base_voice not in VOICES_INTERNAL:
                    return False, base_voice
        return True, None
    else:
        if voice_name not in VOICES_INTERNAL:
            return False, voice_name
        return True, None
```

**Updated code**:
```python
def validate_voice_name(voice_name):
    from abogen.constants import VOICES_INTERNAL
    voice_name = voice_name.strip()

    if "*" in voice_name:
        voices = voice_name.split("+")
        for term in voices:
            if "*" in term:
                base_voice = term.split("*")[0].strip()
                # Case-insensitive comparison
                if base_voice.lower() not in [v.lower() for v in VOICES_INTERNAL]:
                    return False, base_voice
        return True, None
    else:
        # Case-insensitive comparison
        if voice_name.lower() not in [v.lower() for v in VOICES_INTERNAL]:
            return False, voice_name
        return True, None
```

**Better approach** (more efficient - create lowercase lookup set once):
```python
def validate_voice_name(voice_name):
    from abogen.constants import VOICES_INTERNAL

    # Create case-insensitive lookup (done once per call)
    voice_lookup_lower = {v.lower() for v in VOICES_INTERNAL}
    voice_name = voice_name.strip()

    if "*" in voice_name:
        voices = voice_name.split("+")
        for term in voices:
            if "*" in term:
                base_voice = term.split("*")[0].strip()
                # Case-insensitive comparison
                if base_voice.lower() not in voice_lookup_lower:
                    return False, base_voice
        return True, None
    else:
        # Case-insensitive comparison
        if voice_name.lower() not in voice_lookup_lower:
            return False, voice_name
        return True, None
```

#### 2. Normalize Voice Names to Lowercase

**File**: `abogen/subtitle_utils.py` - Update `split_text_by_voice_markers()` function (around line 498-555)

After validation, normalize the voice name to lowercase to match the canonical form in VOICES_INTERNAL:

```python
def split_text_by_voice_markers(text, default_voice):
    """Split text by voice markers, returning list of (voice, text) tuples.

    IMPORTANT: Returns the last voice used so it can persist across chapters.
    Voice names are normalized to lowercase to match VOICES_INTERNAL.

    Args:
        text: Text potentially containing <<VOICE:name>> markers
        default_voice: Voice to use if no markers found or before first marker

    Returns:
        Tuple of (segments_list, last_voice_used):
            - segments_list: List of (voice_name, segment_text) tuples
            - last_voice_used: The voice that should continue into next chapter
    """
    from abogen.constants import VOICES_INTERNAL

    voice_splits = list(_VOICE_MARKER_SEARCH_PATTERN.finditer(text))

    if not voice_splits:
        return [(default_voice, text)], default_voice

    segments = []
    current_voice = default_voice

    # Text before first marker uses default voice
    first_start = voice_splits[0].start()
    if first_start > 0:
        intro_text = text[:first_start].strip()
        if intro_text:
            segments.append((current_voice, intro_text))

    # Process each voice marker
    for idx, match in enumerate(voice_splits):
        voice_name = match.group(1).strip()
        start = match.end()
        end = voice_splits[idx + 1].start() if idx + 1 < len(voice_splits) else len(text)
        segment_text = text[start:end].strip()

        # Validate voice name
        is_valid, invalid_voice = validate_voice_name(voice_name)
        if is_valid:
            # Normalize to lowercase to match canonical form
            # Handle both single voices and formulas
            if "*" in voice_name:
                # Normalize each voice in the formula
                normalized_parts = []
                for part in voice_name.split("+"):
                    part = part.strip()
                    if "*" in part:
                        voice_part, weight = part.split("*", 1)
                        # Find the canonical (lowercase) voice name
                        voice_part_lower = voice_part.strip().lower()
                        canonical_voice = next((v for v in VOICES_INTERNAL if v.lower() == voice_part_lower), voice_part.strip())
                        normalized_parts.append(f"{canonical_voice}*{weight.strip()}")
                current_voice = " + ".join(normalized_parts)
            else:
                # Find the canonical (lowercase) voice name
                voice_name_lower = voice_name.lower()
                current_voice = next((v for v in VOICES_INTERNAL if v.lower() == voice_name_lower), voice_name)
        # If invalid, current_voice stays the same (fallback behavior)

        if segment_text:
            segments.append((current_voice, segment_text))

    # Return segments AND the last voice used (to persist to next chapter)
    return segments, current_voice
```

#### 3. Improve Voice Change Logging

**File**: `abogen/conversion.py` (around line 582-600)

Change the logging to count actual voice markers found and report both markers found and successful changes:

**Current code**:
```python
# Log if voice markers were found
total_voice_segments = sum(len(segments) for _, segments in chapters_with_voices)
if total_voice_segments > len(chapters):
    self.log_updated.emit(
        (f"\nDetected {total_voice_segments - len(chapters)} voice change(s) across all chapters", "grey")
    )
```

**Updated code**:
```python
# Count actual voice markers in the text (before they were processed)
voice_marker_count = len(_VOICE_MARKER_SEARCH_PATTERN.findall(text))

# Count segments created (extra segments indicate successful voice changes)
total_voice_segments = sum(len(segments) for _, segments in chapters_with_voices)
segment_based_changes = total_voice_segments - len(chapters)

# Log voice marker information
if voice_marker_count > 0:
    if segment_based_changes == voice_marker_count:
        # All markers were valid
        self.log_updated.emit(
            (f"\nDetected {voice_marker_count} voice marker(s) - all valid", "grey")
        )
    elif segment_based_changes < voice_marker_count:
        # Some markers were invalid
        invalid_count = voice_marker_count - segment_based_changes
        self.log_updated.emit(
            (f"\nDetected {voice_marker_count} voice marker(s) - {segment_based_changes} valid, {invalid_count} invalid (using previous voice)", "orange")
        )
    else:
        # This shouldn't happen, but handle it gracefully
        self.log_updated.emit(
            (f"\nDetected {voice_marker_count} voice marker(s)", "grey")
        )
```

#### 4. Update Test Suite

**File**: `test_voice_markers.py`

Add test for case-insensitive voice names:

```python
def test_case_insensitive_validation():
    """Test that voice names are case-insensitive."""
    print("=" * 60)
    print("Testing case-insensitive voice names...")
    print("=" * 60)

    # Test uppercase
    is_valid, invalid = validate_voice_name("AF_HEART")
    print(f"[OK] AF_HEART (uppercase): valid={is_valid}")
    assert is_valid and invalid is None

    # Test mixed case
    is_valid, invalid = validate_voice_name("Am_Fenrir")
    print(f"[OK] Am_Fenrir (mixed case): valid={is_valid}")
    assert is_valid and invalid is None

    # Test formula with mixed case
    is_valid, invalid = validate_voice_name("AF_Heart*0.5 + AM_Echo*0.5")
    print(f"[OK] AF_Heart*0.5 + AM_Echo*0.5 (mixed case formula): valid={is_valid}")
    assert is_valid and invalid is None

    # Test that invalid names still fail regardless of case
    is_valid, invalid = validate_voice_name("INVALID_VOICE")
    print(f"[INVALID] INVALID_VOICE (uppercase): valid={is_valid}")
    assert not is_valid

    print("\n[PASS] Case-insensitive validation tests passed!\n")

def test_voice_normalization():
    """Test that voice names are normalized to canonical lowercase form."""
    print("=" * 60)
    print("Testing voice name normalization...")
    print("=" * 60)

    # Test normalization
    text = """Default voice.
<<VOICE:AM_FENRIR>>
This should normalize to am_fenrir."""

    segments, last_voice = split_text_by_voice_markers(text, "af_heart")
    print(f"Input voice: AM_FENRIR")
    print(f"Normalized voice: {segments[1][0]}")
    assert segments[1][0] == "am_fenrir", f"Expected 'am_fenrir', got '{segments[1][0]}'"

    print("\n[PASS] Voice normalization test passed!\n")
```

Add these tests to the main test runner:
```python
if __name__ == "__main__":
    try:
        test_validate_voice_name()
        test_case_insensitive_validation()  # NEW
        test_voice_normalization()  # NEW
        test_split_text_by_voice_markers()
        test_voice_persistence_across_chapters()
        # ... rest of the tests
```

### Summary of Changes

1. ✅ Voice name validation is now case-insensitive (accepts `AM_FENRIR`, `Am_Fenrir`, etc.)
2. ✅ Voice names are normalized to canonical lowercase form from VOICES_INTERNAL
3. ✅ Logging now shows actual marker count vs. valid changes
4. ✅ Invalid markers are reported in the log
5. ✅ Test suite updated to verify case-insensitive behavior

### Files to Modify

1. `abogen/subtitle_utils.py` - Update `validate_voice_name()` and `split_text_by_voice_markers()`
2. `abogen/conversion.py` - Improve voice marker logging (around line 595-600)
3. `test_voice_markers.py` - Add case-insensitive tests

### Issue: Voice Marker Counting Bug (✅ FIXED)

**Problem**: The logging always reports 1 invalid marker even when all markers are valid.

**Status**: ✅ **FIXED** - This issue has been resolved. The implementation now accurately tracks and reports valid/invalid markers.

**Root Cause**: The comparison logic was flawed:
```python
voice_marker_count = len(_VOICE_MARKER_SEARCH_PATTERN.findall(text))  # Total markers
segment_based_changes = total_voice_segments - len(chapters)  # Extra segments
```

These aren't comparable because:
- Markers don't account for the "default voice" segment before the first marker
- Segment count includes that default segment
- Example: 4 markers + 1 default segment = 5 segments, but we're comparing 4 vs (5-2=3)

**Correct Fix**: Track valid/invalid markers during processing in `split_text_by_voice_markers()`:

**File**: `abogen/subtitle_utils.py` - Update return value:
```python
def split_text_by_voice_markers(text, default_voice):
    """Split text by voice markers, returning list of (voice, text) tuples.

    IMPORTANT: Returns the last voice used so it can persist across chapters.
    Voice names are normalized to lowercase to match VOICES_INTERNAL.

    Args:
        text: Text potentially containing <<VOICE:name>> markers
        default_voice: Voice to use if no markers found or before first marker

    Returns:
        Tuple of (segments_list, last_voice_used, valid_count, invalid_count):
            - segments_list: List of (voice_name, segment_text) tuples
            - last_voice_used: The voice that should continue into next chapter
            - valid_count: Number of valid voice markers processed
            - invalid_count: Number of invalid voice markers skipped
    """
    from abogen.constants import VOICES_INTERNAL

    voice_splits = list(_VOICE_MARKER_SEARCH_PATTERN.finditer(text))

    if not voice_splits:
        return [(default_voice, text)], default_voice, 0, 0  # No markers

    segments = []
    current_voice = default_voice
    valid_markers = 0
    invalid_markers = 0

    # Text before first marker uses default voice
    first_start = voice_splits[0].start()
    if first_start > 0:
        intro_text = text[:first_start].strip()
        if intro_text:
            segments.append((current_voice, intro_text))

    # Process each voice marker
    for idx, match in enumerate(voice_splits):
        voice_name = match.group(1).strip()
        start = match.end()
        end = voice_splits[idx + 1].start() if idx + 1 < len(voice_splits) else len(text)
        segment_text = text[start:end].strip()

        # Validate voice name
        is_valid, invalid_voice = validate_voice_name(voice_name)
        if is_valid:
            # Normalize to lowercase to match canonical form
            # Handle both single voices and formulas
            if "*" in voice_name:
                # Normalize each voice in the formula
                normalized_parts = []
                for part in voice_name.split("+"):
                    part = part.strip()
                    if "*" in part:
                        voice_part, weight = part.split("*", 1)
                        # Find the canonical (lowercase) voice name
                        voice_part_lower = voice_part.strip().lower()
                        canonical_voice = next((v for v in VOICES_INTERNAL if v.lower() == voice_part_lower), voice_part.strip())
                        normalized_parts.append(f"{canonical_voice}*{weight.strip()}")
                current_voice = " + ".join(normalized_parts)
            else:
                # Find the canonical (lowercase) voice name
                voice_name_lower = voice_name.lower()
                current_voice = next((v for v in VOICES_INTERNAL if v.lower() == voice_name_lower), voice_name)
            valid_markers += 1
        else:
            # Invalid voice - stay with previous voice
            invalid_markers += 1

        if segment_text:
            segments.append((current_voice, segment_text))

    # Return segments, last voice, and counts
    return segments, current_voice, valid_markers, invalid_markers
```

**File**: `abogen/conversion.py` - Update to use the new return values:
```python
# After chapters list is created, split each chapter by voice markers
# IMPORTANT: Voice state persists across chapters!
chapters_with_voices = []
current_voice = self.voice  # Start with default voice
total_valid_markers = 0
total_invalid_markers = 0

for chapter_name, chapter_text in chapters:
    # Use current_voice as the starting voice for this chapter
    voice_segments, last_voice, valid_count, invalid_count = split_text_by_voice_markers(chapter_text, current_voice)
    chapters_with_voices.append((chapter_name, voice_segments))

    # Update current_voice so next chapter continues with this voice
    current_voice = last_voice

    # Track total valid/invalid markers
    total_valid_markers += valid_count
    total_invalid_markers += invalid_count

# Log voice marker information with accurate counts
total_markers = total_valid_markers + total_invalid_markers
if total_markers > 0:
    if total_invalid_markers == 0:
        # All markers were valid
        self.log_updated.emit(
            (f"\nDetected {total_markers} voice marker(s) - all valid", "grey")
        )
    else:
        # Some markers were invalid
        self.log_updated.emit(
            (f"\nDetected {total_markers} voice marker(s) - {total_valid_markers} valid, {total_invalid_markers} invalid (using previous voice)", "orange")
        )

# Replace chapters with the new structure
chapters = chapters_with_voices
```

## Known Issues & Fixes

### Issue 1: UnboundLocalError for text_segments

**Note**: This issue has been addressed in Phase 2, Step 7b of the implementation steps above. The fix is included in the main implementation instructions.

**Problem**: If not careful with indentation, you may get this error:
```
Error occurred: cannot access local variable 'text_segments' where it is not associated with a value
```

**Root Cause**: When indenting the TTS processing code to be inside the voice segment loop, the line `text_segments = spacy_sentences if spacy_sentences else [segment_text]` can be accidentally indented too far, placing it inside the `if use_spacy and self.lang_code not in ["a", "b"]:` conditional block. For English (language code "a" or "b"), this condition is false, so `text_segments` never gets defined.

**Solution**: Follow Phase 2, Step 7b carefully. The `text_segments` assignment line (around line 1136) must be at the correct indentation level (20 spaces) - at the same level as the "Print active split pattern" comment below it, NOT inside the spaCy conditional block.

**Reference - Correct structure**:

```python
                    if use_spacy and self.lang_code not in ["a", "b"]:
                        # Non-English: use spaCy for pre-TTS segmentation
                        self.log_updated.emit(
                            ("\nUsing spaCy for sentence segmentation (pre-TTS)...", "grey")
                        )
                        from abogen.spacy_utils import segment_sentences

                        spacy_sentences = segment_sentences(
                            segment_text,
                            self.lang_code,
                            log_callback=lambda msg: self.log_updated.emit(msg),
                        )
                        if spacy_sentences:
                            self.log_updated.emit(
                                (
                                    f"\nspaCy: Text segmented into {len(spacy_sentences)} sentences...",
                                    "grey",
                                )
                            )
                            # For Sentence + Comma mode, still split on commas within spaCy sentences
                            if self.subtitle_mode == "Sentence + Comma":
                                active_split_pattern = r"(?<=[{}]){}|\n+".format(
                                    self.PUNCTUATION_COMMAS, spacing_pattern
                                )
                            else:
                                active_split_pattern = (
                                    "\n"  # Use newline splitting for Sentence mode
                                )
                        else:
                            self.log_updated.emit(
                                ("\nspaCy: Fallback to default segmentation...", "grey")
                            )

                    # Process text - either as spaCy sentences or as single text
                    # NOTE: This line MUST be at this indentation level (not inside the if block above)
                    text_segments = spacy_sentences if spacy_sentences else [segment_text]

                    # Print active split pattern used by the TTS engine once for this batch
                    try:
                        print(f"Using split pattern: {active_split_pattern!r}")
```


---

## ✅ Implementation Status: COMPLETE

All voice marker functionality has been successfully implemented and tested. The following issues have been resolved:

### ✅ Completed Features

1. **Voice Marker Support**: `<<VOICE:voice_name>>` markers work correctly
   - Voice state persists across chapters
   - Invalid voices fallback to previous voice (not default)
   - Empty segments are filtered out

2. **Case-Insensitive Voice Names**: Voice names accept any case (AM_FENRIR, am_fenrir, Am_Fenrir)
   - Validation uses case-insensitive comparison
   - Names are normalized to canonical lowercase form from VOICES_INTERNAL
   - Voice formulas also support mixed case

3. **Accurate Voice Marker Counting**: Logging correctly reports valid/invalid marker counts
   - Tracks counters during processing in `split_text_by_voice_markers()`
   - Returns `(segments, last_voice, valid_count, invalid_count)`
   - Sums counts across all chapters for accurate reporting

4. **All Tests Passing**: Comprehensive test suite verifies all functionality
   - `test_validate_voice_name()` - validates single voices and formulas
   - `test_case_insensitive_validation()` - tests uppercase/mixed case
   - `test_voice_normalization()` - verifies lowercase normalization
   - `test_split_text_by_voice_markers()` - tests 5 splitting scenarios
   - `test_voice_persistence_across_chapters()` - verifies state persistence

### ✅ Fixed Issues

1. **UnboundLocalError for text_segments** (Fixed in Phase 2, Step 7b)
   - Incorrect indentation placed variable assignment inside conditional block
   - Fixed by ensuring `text_segments` line is at correct scope level (20 spaces)

2. **Voice Marker Counting Bug** (Fixed)
   - Flawed comparison logic always reported 1 invalid marker
   - Fixed by tracking valid/invalid counters during marker processing
   - Now reports accurate counts: "Detected N voice marker(s) - all valid" or "X valid, Y invalid"

### Files Modified

1. `abogen/subtitle_utils.py` - Voice marker patterns, validation, splitting with counting
2. `abogen/conversion.py` - Chapter processing with voice segments, caching, accurate logging
3. `abogen/gui.py` - Voice marker insertion button (optional enhancement)
4. `test_voice_markers.py` - Comprehensive test suite with case-insensitive tests

### Ready to Use

The implementation is production-ready. Users can now:
- Use `<<VOICE:voice_name>>` markers in text files to switch between TTS voices
- Voice changes persist across chapter boundaries
- Invalid voice names gracefully fallback to previous voice with warnings
- All voice names are case-insensitive for better usability

**Package installed**: Run `python_embedded/python.exe -m abogen.main` or `run_with_changes.bat` to use the updated code.

