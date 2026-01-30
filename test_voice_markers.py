#!/usr/bin/env python3
"""
Test script for voice marker functionality.
Tests the voice marker splitting logic without running the full TTS system.
"""

import sys
import os

# Add the abogen directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from abogen.subtitle_utils import split_text_by_voice_markers, validate_voice_name

def test_validate_voice_name():
    """Test voice name validation."""
    print("=" * 60)
    print("Testing voice name validation...")
    print("=" * 60)

    # Test valid single voice
    is_valid, invalid = validate_voice_name("af_heart")
    print(f"[OK] af_heart: valid={is_valid}, invalid={invalid}")
    assert is_valid and invalid is None

    # Test invalid single voice
    is_valid, invalid = validate_voice_name("invalid_voice")
    print(f"[INVALID] invalid_voice: valid={is_valid}, invalid={invalid}")
    assert not is_valid and invalid == "invalid_voice"

    # Test valid formula
    is_valid, invalid = validate_voice_name("af_heart*0.5 + am_echo*0.5")
    print(f"[OK] af_heart*0.5 + am_echo*0.5: valid={is_valid}, invalid={invalid}")
    assert is_valid and invalid is None

    # Test invalid formula
    is_valid, invalid = validate_voice_name("af_heart*0.5 + invalid_voice*0.5")
    print(f"[INVALID] af_heart*0.5 + invalid_voice*0.5: valid={is_valid}, invalid={invalid}")
    assert not is_valid and invalid == "invalid_voice"

    print("\n[PASS] All validation tests passed!\n")


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

    segments, last_voice, valid_count, invalid_count = split_text_by_voice_markers(text, "af_heart")
    print(f"Input voice: AM_FENRIR")
    print(f"Normalized voice: {segments[1][0]}")
    assert segments[1][0] == "am_fenrir", f"Expected 'am_fenrir', got '{segments[1][0]}'"

    # Test formula normalization
    text2 = """Default voice.
<<VOICE:AF_Heart*0.5 + AM_Echo*0.5>>
Mixed voice formula."""

    segments2, last_voice2, valid_count2, invalid_count2 = split_text_by_voice_markers(text2, "af_heart")
    print(f"Input formula: AF_Heart*0.5 + AM_Echo*0.5")
    print(f"Normalized formula: {segments2[1][0]}")
    assert segments2[1][0] == "af_heart*0.5 + am_echo*0.5", f"Expected normalized formula, got '{segments2[1][0]}'"

    print("\n[PASS] Voice normalization test passed!\n")


def test_split_text_by_voice_markers():
    """Test text splitting by voice markers."""
    print("=" * 60)
    print("Testing text splitting by voice markers...")
    print("=" * 60)

    # Test 1: No voice markers
    text1 = "This is plain text without markers."
    segments1, last_voice1, valid_count1, invalid_count1 = split_text_by_voice_markers(text1, "af_heart")
    print(f"\nTest 1: No markers")
    print(f"  Segments: {segments1}")
    print(f"  Last voice: {last_voice1}")
    assert len(segments1) == 1
    assert segments1[0] == ("af_heart", text1)
    assert last_voice1 == "af_heart"

    # Test 2: Single voice change
    text2 = """First part with default voice.
<<VOICE:bf_alice>>
Second part with British female voice."""
    segments2, last_voice2, valid_count2, invalid_count2 = split_text_by_voice_markers(text2, "af_heart")
    print(f"\nTest 2: Single voice change")
    for i, (voice, text) in enumerate(segments2):
        print(f"  Segment {i+1}: voice={voice}, text='{text[:50]}...'")
    print(f"  Last voice: {last_voice2}")
    assert len(segments2) == 2
    assert segments2[0][0] == "af_heart"
    assert segments2[1][0] == "bf_alice"
    assert last_voice2 == "bf_alice"

    # Test 3: Multiple voice changes
    text3 = """Default voice.
<<VOICE:bf_alice>>
British female.
<<VOICE:am_fenrir>>
American male."""
    segments3, last_voice3, valid_count3, invalid_count3 = split_text_by_voice_markers(text3, "af_heart")
    print(f"\nTest 3: Multiple voice changes")
    for i, (voice, text) in enumerate(segments3):
        print(f"  Segment {i+1}: voice={voice}, text='{text[:30]}...'")
    print(f"  Last voice: {last_voice3}")
    assert len(segments3) == 3
    assert segments3[0][0] == "af_heart"
    assert segments3[1][0] == "bf_alice"
    assert segments3[2][0] == "am_fenrir"
    assert last_voice3 == "am_fenrir"

    # Test 4: Invalid voice (should fallback to previous)
    text4 = """Default voice.
<<VOICE:bf_alice>>
British female.
<<VOICE:invalid_voice>>
Should continue with bf_alice."""
    segments4, last_voice4, valid_count4, invalid_count4 = split_text_by_voice_markers(text4, "af_heart")
    print(f"\nTest 4: Invalid voice (fallback to previous)")
    for i, (voice, text) in enumerate(segments4):
        print(f"  Segment {i+1}: voice={voice}, text='{text[:30]}...'")
    print(f"  Last voice: {last_voice4}")
    assert len(segments4) == 3
    assert segments4[0][0] == "af_heart"
    assert segments4[1][0] == "bf_alice"
    assert segments4[2][0] == "bf_alice"  # Should fallback to bf_alice, NOT af_heart
    assert last_voice4 == "bf_alice"

    # Test 5: Voice formula
    text5 = """Default voice.
<<VOICE:af_heart*0.5 + am_echo*0.5>>
Mixed voice formula."""
    segments5, last_voice5, valid_count5, invalid_count5 = split_text_by_voice_markers(text5, "af_heart")
    print(f"\nTest 5: Voice formula")
    for i, (voice, text) in enumerate(segments5):
        print(f"  Segment {i+1}: voice={voice}, text='{text[:30]}...'")
    print(f"  Last voice: {last_voice5}")
    assert len(segments5) == 2
    assert segments5[0][0] == "af_heart"
    assert segments5[1][0] == "af_heart*0.5 + am_echo*0.5"
    assert last_voice5 == "af_heart*0.5 + am_echo*0.5"

    print("\n[PASS] All splitting tests passed!\n")


def test_voice_persistence_across_chapters():
    """Test that voice persists across chapters."""
    print("=" * 60)
    print("Testing voice persistence across chapters...")
    print("=" * 60)

    # Simulate chapter processing
    chapters = [
        ("Chapter 1", "Default voice.\n<<VOICE:bf_alice>>\nBritish female."),
        ("Chapter 2", "This should continue with bf_alice."),
        ("Chapter 3", "Still bf_alice.\n<<VOICE:am_fenrir>>\nSwitch to American male."),
        ("Chapter 4", "This should continue with am_fenrir."),
    ]

    current_voice = "af_heart"  # Default voice
    all_segments = []

    for chapter_name, chapter_text in chapters:
        segments, last_voice, valid_count, invalid_count = split_text_by_voice_markers(chapter_text, current_voice)
        all_segments.append((chapter_name, segments))
        current_voice = last_voice  # Voice persists to next chapter

    print(f"\nProcessing {len(chapters)} chapters:")
    for chapter_name, segments in all_segments:
        print(f"\n{chapter_name}:")
        for i, (voice, text) in enumerate(segments):
            print(f"  Segment {i+1}: voice={voice}, text='{text[:40]}...'")

    # Verify expectations
    assert all_segments[0][1][0][0] == "af_heart"  # Chapter 1, segment 1
    assert all_segments[0][1][1][0] == "bf_alice"  # Chapter 1, segment 2
    assert all_segments[1][1][0][0] == "bf_alice"  # Chapter 2, segment 1 (persisted!)
    assert all_segments[2][1][0][0] == "bf_alice"  # Chapter 3, segment 1 (persisted!)
    assert all_segments[2][1][1][0] == "am_fenrir"  # Chapter 3, segment 2
    assert all_segments[3][1][0][0] == "am_fenrir"  # Chapter 4, segment 1 (persisted!)

    print("\n[PASS] Voice persistence test passed!\n")


if __name__ == "__main__":
    try:
        test_validate_voice_name()
        test_case_insensitive_validation()
        test_voice_normalization()
        test_split_text_by_voice_markers()
        test_voice_persistence_across_chapters()

        print("=" * 60)
        print("*** ALL TESTS PASSED! ***")
        print("=" * 60)
        print("\nVoice marker feature is working correctly!")
        print("The implementation handles:")
        print("  [OK] Voice validation (single voices and formulas)")
        print("  [OK] Text splitting by voice markers")
        print("  [OK] Invalid voice fallback to previous voice")
        print("  [OK] Voice persistence across chapters")
        print("\nYou can now use <<VOICE:voice_name>> markers in your text files!")

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
