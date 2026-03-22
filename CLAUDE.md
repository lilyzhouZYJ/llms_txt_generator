Use explicit `for` loops instead of dense list/set/dict comprehensions when the logic involves conditions or transformations. One-liners that pack filtering, transformation, and logic into a single expression are hard to read.

**Why:** User explicitly asked to stop writing many logic steps on one line and use proper loops.

**How to apply:** Any time a comprehension has an `if` clause plus a transformation (e.g. `str(x).strip()`), or combines multiple conditions, expand it into a loop with named variables.
