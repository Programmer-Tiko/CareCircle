"""Fixed capture protocol; count words as spoken, never estimate from spelling.

Rainbow Passage, Grant Fairbanks, first two sentences. Source transcription:
https://dailycues.com/learn/iqpedia/pages/rainbow-passage/
American English convention: prism=2, division=3, beautiful=3, colors=2.
Natural pronunciation can vary; this is the protocol's fixed rate numerator,
not a measured count or a verification that the participant read the passage.
Use a fresh profile for this protocol: older baselines used placeholder 40.
"""
PASSAGE_ID = 'rainbow-first-two-sentences-v1'
PASSAGE_TEXT = (
    'When the sunlight strikes raindrops in the air, they act as a prism and form a rainbow. '
    'The rainbow is a division of white light into many beautiful colors.'
)
# Word-by-word audit, in passage order. Sentence totals: 21 + 20 = 41.
PASSAGE_SYLLABLES = (
    ('When', 1), ('the', 1), ('sunlight', 2), ('strikes', 1), ('raindrops', 2),
    ('in', 1), ('the', 1), ('air', 1), ('they', 1), ('act', 1), ('as', 1),
    ('a', 1), ('prism', 2), ('and', 1), ('form', 1), ('a', 1), ('rainbow', 2),
    ('The', 1), ('rainbow', 2), ('is', 1), ('a', 1), ('division', 3), ('of', 1),
    ('white', 1), ('light', 1), ('into', 2), ('many', 2), ('beautiful', 3), ('colors', 2),
)
PASSAGE_SYLLABLE_COUNT = 41
