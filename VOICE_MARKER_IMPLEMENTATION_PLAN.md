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

7. **Update text processing** (line 1063 - replace `chapter_text` with `segment_text`):
   ```python
   # OLD: text_segments = spacy_sentences if spacy_sentences else [chapter_text]
   # NEW:
   text_segments = spacy_sentences if spacy_sentences else [segment_text]
   ```

   Also update the spaCy segmentation call (line 1037):
   ```python
   # OLD: spacy_sentences = segment_sentences(chapter_text, ...)
   # NEW:
   spacy_sentences = segment_sentences(segment_text, ...)
   ```

8. **Ensure proper loop indentation**:
   - All TTS processing code (lines 1000-1270 approximately) should be indented one level deeper
   - This code now runs inside the voice segment loop
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
