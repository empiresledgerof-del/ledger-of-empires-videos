# Thumbnail playbook (Ledger of Empires) - researched 19 Nov 2026

## What the data says
- vidIQ, 500 breakout long videos across 30 niches (June 2026): 69% used a human face (80% of the top 50),
  89% used a face OR high contrast, 72% had overlay text, median 5 words; most breakouts used 3 words or fewer.
  Only ~5% used an exaggerated face. Advice: avoid YouTube's own red/white/black so the thumbnail does not blend in.
- Eden (507k videos): 4-6 words was the sweet spot gap vs underperformers; 62% of breakout text is ALL CAPS;
  only 6% repeat the title, 39% share no words with it. The thumbnail adds what the title does not say.
- Desaturated, cinematic looks with one accent colour suit documentary/finance (our navy + gold).
- Native A/B testing (Studio "A/B Testing", 3 versions, winner by watch-time share) needs YPP: use it once accepted.

## Our rules
1. ONE focal subject, big (40-60% of the frame): a face from history whenever possible (portrait painting or
   archive photo of the person: Rockefeller, Newton, Mansa Musa in the Catalan Atlas) or one striking object
   (a striped tulip, a stack of gold, a crashing chart drawn by us).
2. Text: 2-4 words, ALL CAPS, Inter Black, huge (readable at 320x180), one word in gold, the rest white,
   on the darker side of the image. Never repeat the title; add the curiosity the title leaves open.
   Title "Tulip Mania: When a Flower Cost a House" -> thumb "WORTH A HOUSE?".
3. Curiosity must be TRUE to the video. No fake quotes, no invented numbers, no misleading arrows.
4. Brand look: navy shadows, gold accent, warm grade; a thin gold frame line is optional. No YouTube red.
5. Make 3 options per long video (different image or different words or layout). Check each at full size
   AND at 320x180 (the build writes thumb_check.jpg); pick the one whose subject and words read instantly small.
   Record which one was used in state.json; when YPP unlocks A/B testing, upload all 3.
6. Shorts: 1080x1920 cover with the same rule (subject + 2-3 words in the top half). If Metricool returns
   VIDEO_THUMBNAIL_NOT_APPLICABLE, post without it.
7. Avoid: busy collages, more than 5 words, thin fonts, text over faces, tiny old-map details, dark-on-dark.

## Spec in script.json
"thumbs": [
  {"image": "s2_1.jpg", "lines": ["WORTH", "A HOUSE?"], "accent": 1, "side": "left", "focus": "right"},
  {"image": "s0_0.jpg", "lines": ["THE FIRST", "BUBBLE"], "accent": 1, "side": "right"},
  {"image": "s5_0.mp4@3", "lines": ["IT ALL", "VANISHED"], "accent": 1, "side": "left"}
]
`side` = where the text goes; `focus` = which part of the image to keep (left/center/right/top).
