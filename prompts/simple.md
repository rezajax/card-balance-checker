# Simple Prompt

**Description:** Compact prompt with essential grid info

---

Identify tiles containing the target object.

TILE NUMBERING (left-to-right, top-to-bottom):
- 3x3 grid: Row1=[1,2,3] Row2=[4,5,6] Row3=[7,8,9]
- 4x4 grid: Row1=[1,2,3,4] Row2=[5,6,7,8] Row3=[9,10,11,12] Row4=[13,14,15,16]

KEY POINTS:
- Tile 1 = TOP-LEFT corner
- Last tile = BOTTOM-RIGHT corner
- Include tiles with partial objects

Respond with tile numbers only. Example: "2, 5, 8"
If none match: "none"
