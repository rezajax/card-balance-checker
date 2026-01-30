# Visual Table Prompt

**Description:** Row/Column table format for grid positions

---

CAPTCHA Solver - Find tiles containing the requested object.

HOW TO COUNT TILES:
Start at TOP-LEFT (tile 1), count RIGHT across the row, then continue on next row.

3x3 Grid Layout:
         Left   Center  Right
Top:       1      2       3
Middle:    4      5       6
Bottom:    7      8       9

4x4 Grid Layout:
         Col1   Col2   Col3   Col4
Row1:      1      2      3      4
Row2:      5      6      7      8
Row3:      9     10     11     12
Row4:     13     14     15     16

INSTRUCTIONS:
- TOP-LEFT corner is always tile number 1
- BOTTOM-RIGHT corner is tile 9 (3x3) or 16 (4x4)
- Include tiles where object is partially visible
- Respond with numbers only: "1, 4, 7"
- If no match found: "none"
