"""The known-marque list this catalogue carries (D14).

`KNOWN_MARQUES` is **generated and committed**, never parsed at runtime from
`backend/resources/bike-list.txt` (D14 is explicit about this: a runtime parse
would make manufacturer normalisation depend on a resource file's shape at
import time, for no benefit — the set of marques this catalogue targets
changes only when someone deliberately adds one).

Derivation: the distinct first whitespace-separated token of every entry line
in `backend/resources/bike-list.txt` (bracketed section headers, e.g.
`[Sport]`, excluded), canonical casing exactly as printed in that file:

    awk '{print $1}' backend/resources/bike-list.txt | grep -v '^\\[' | sort -u

Regeneration rule: re-run that command and re-commit this tuple whenever
`bike-list.txt` gains a marque. Do not hand-edit around it.
"""

KNOWN_MARQUES: tuple[str, ...] = (
    "Aprilia",
    "BMW",
    "Ducati",
    "Harley-Davidson",
    "Honda",
    "Kawasaki",
    "KTM",
    "Suzuki",
    "Triumph",
    "Yamaha",
)
