Please analyze the following interview practice video and answer content, and complete visual analysis, voice analysis, tone analysis, and feedback generation.

---

## 【Input Data】

**Video Frame Count**: {total_frames} frames
**Video Duration**: {duration} seconds
**Language**: {language}

**User Answer Text**:
```
{transcript}
```

**Interviewer Question** (if any):
```
{question}
```

**Audio Features** (if any):
{audio_features}

**Previous Test Scores** (within 7 days, if any):
{previous_scores}

---

## 【Video Frames】

{frame_images}

---

## 【Task Requirements】

Please complete all of the following analyses:

1. **Visual Performance Analysis**:
   - Detect face visibility (if face is not detected, must mark as Critical)
   - Detect inappropriate behaviors (picking nose, touching face, scratching ears, etc.)
   - Analyze eye contact, facial expressions, posture, appearance

2. **Voice Performance Analysis**:
   - Analyze speaking speed, intonation, volume, pronunciation clarity, pauses
   - Detect issues like coughing, unclear pronunciation, stuttering, voice breaks, etc.

3. **Tone Analysis**:
   - Based on text and audio features, analyze emotional expression and engagement

4. **Feedback Generation**:
   - For 6 dimensions (Clarity, Evidence, Impact, Engagement, Verbal Performance, Visual Performance), generate:
     - Score (0-100)
     - One-sentence comment (20-30 words)
     - Detailed feedback (including detailed evaluation and improvement suggestions)

---

## 【Output Requirements】

Please output strictly in the JSON format specified in the system prompt, ensuring:
- All fields are complete
- Score ranges are correct (0-100)
- score_labels are correct (Good/Fair/Poor/Critical)
- If critical issues are detected, must directly point out, do not use euphemistic language
- If score > 75, use positive tone
- If score > previous score, clearly point out areas of improvement

