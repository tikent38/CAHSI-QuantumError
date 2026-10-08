# Error Codes

> **Notation:** Kets are written in Qiskit's order, $|q_2\,q_1\,q_0\rangle$, so $q_0$ (the top wire in a
> circuit diagram) is the **rightmost** bit. `a_0`, `a_1` are ancilla (helper) qubits and `s` is the
> classical register holding the syndrome.

## Repetition Codes (classical)

- In a 3-bit repetition code, each bit we care about is repeated 3 times: $0 \to 000$, $1 \to 111$.
- If one bit flips by mistake, the other 2 bits are still correct. We decode by taking the
  **majority** value.
- It fails if 2 or 3 bits flip.
- If each bit flips independently with probability $p$, decoding gives the wrong bit only when 2 or 3 bits flip:

$$
P_{\text{error}} = \underbrace{3p^2(1-p)}_{\text{2 flips}} + \underbrace{p^3}_{\text{3 flips}} = 3p^2 - 2p^3
$$

- The two curves cross at $p = 0.5$. The code only helps when $p < 0.5$. When $p > 0.5$ it makes
  the error rate **worse**.

## Quantum Bit-Flip Errors

- Start with $\alpha|0\rangle + \beta|1\rangle$ and encode it as $\alpha|000\rangle + \beta|111\rangle$
  using two CNOTs. (This is **not** copying the state. The no-cloning theorem forbids that. The
  qubits are entangled instead.)
- If the middle qubit flips by mistake, we get $\alpha|010\rangle + \beta|101\rangle$.
- To find the error we can't just measure the data qubits. A measurement would show which bit
  flipped, but it would also collapse the superposition and destroy $\alpha|0\rangle + \beta|1\rangle$,
  the state we were trying to protect.
- **Instead**, add 2 extra **ancilla qubits** and use them to measure **pairwise parities**:
  - $a_0 = q_0 \oplus q_1$
  - $a_1 = q_1 \oplus q_2$

  This tells us whether neighboring qubits agree, but not the values themselves, so it says nothing
  about $\alpha$ or $\beta$ and the encoded state survives.

```
     (encode)        
q_0: ──■────■─────■───────────────────────
     ┌─┴─┐  │     │
q_1: ┤ X ├──┼─────┼────■────■─────────────
     └───┘┌─┴─┐   │    │    │
q_2: ─────┤ X ├───┼────┼────┼───────■─────
          └───┘ ┌─┴─┐┌─┴─┐  │  ┌─┐  │
a_0: ───────────┤ X ├┤ X ├──┼──┤M├──┼─────
                └───┘└───┘┌─┴─┐└╥┘┌─┴─┐┌─┐
a_1: ─────────────────────┤ X ├─╫─┤ X ├┤M├
                          └───┘ ║ └───┘└╥┘
s: 2/═══════════════════════════╩═══════╩═
                                0       1
```

**Syndrome table** (the error happens between encoding and syndrome measurement):

| Error           | State after error                            | $a_0$ | $a_1$ |
|-----------------|----------------------------------------------|-------|-------|
| none            | $\alpha\|000\rangle + \beta\|111\rangle$     | 0     | 0     |
| $X$ on $q_0$    | $\alpha\|001\rangle + \beta\|110\rangle$     | 1     | 0     |
| $X$ on $q_1$    | $\alpha\|010\rangle + \beta\|101\rangle$     | 1     | 1     |
| $X$ on $q_2$    | $\alpha\|100\rangle + \beta\|011\rangle$     | 0     | 1     |

- Each single-qubit flip gives a different syndrome, so we know which qubit to fix.
- **Correction:** apply another $X$ gate to the qubit that flipped, since $X \cdot X = I$.

## Quantum Phase-Flip Errors

- A phase flip is a $Z$ error: $Z|0\rangle = |0\rangle$, $Z|1\rangle = -|1\rangle$.
- The 3-qubit bit-flip code **cannot detect** phase flips. A $Z$ on *any* one qubit sends
  $\alpha|000\rangle + \beta|111\rangle \to \alpha|000\rangle - \beta|111\rangle$:
  - It's the same state no matter which qubit was hit, so we can't tell where the error happened.
  - The parity checks above still read `00`, so we don't even know an error happened.
  - The phase belongs to the whole encoded state, so a single $Z$ silently corrupts the logical qubit.
- **Fix:** after the two CNOTs, apply an $H$ gate to every qubit. This encodes in the $|\pm\rangle$ basis:

$$
\alpha|0\rangle + \beta|1\rangle \;\to\; \alpha|{+}{+}{+}\rangle + \beta|{-}{-}{-}\rangle
$$

- Why this works: $Z|+\rangle = |-\rangle$ and $Z|-\rangle = |+\rangle$. In the $\pm$ basis, a phase flip
  behaves like a bit flip, so the same parity-check idea can catch it.
- Trade-off: this code catches phase flips but **not** bit flips. $X|\pm\rangle = \pm|\pm\rangle$, so an
  $X$ error now acts like an undetectable phase error. (Verified: an $X$ on $q_0$ gives syndrome `00`.)

There are two equivalent ways to measure the syndrome.

**Option A:** rotate the data qubits back with $H$, run the bit-flip parity checks, then apply $H$ again
to return to the $\pm$ basis.

```
     (encode)                   (syndrome measurement)
               ┌───┐ ┌───┐     ┌───┐
q_0: ──■────■──┤ H ├─┤ H ├──■──┤ H ├────────────────────
     ┌─┴─┐  │  ├───┤ ├───┤  │  └───┘     ┌───┐
q_1: ┤ X ├──┼──┤ H ├─┤ H ├──┼────■────■──┤ H ├──────────
     └───┘┌─┴─┐├───┤ ├───┤  │    │    │  └───┘     ┌───┐
q_2: ─────┤ X ├┤ H ├─┤ H ├──┼────┼────┼─────────■──┤ H ├
          └───┘└───┘ └───┘┌─┴─┐┌─┴─┐  │   ┌─┐   │  └───┘
a_0: ─────────────────────┤ X ├┤ X ├──┼───┤M├───┼───────
                          └───┘└───┘┌─┴─┐ └╥┘ ┌─┴─┐ ┌─┐
a_1: ───────────────────────────────┤ X ├──╫──┤ X ├─┤M├─
                                    └───┘  ║  └───┘ └╥┘
s: 2/══════════════════════════════════════╩═════════╩══
                                           0         1
```

**Option B:** put the ancillas in $|+\rangle$, use them as the CNOT **controls** with the data qubits as
targets (phase kickback), then apply $H$ to the ancillas and measure.

```
     (encode)             (syndrome measurement)
               ┌───┐      ┌───┐
q_0: ──■────■──┤ H ├──────┤ X ├───────────────────────────────
     ┌─┴─┐  │  ├───┤      └─┬─┘┌───┐┌───┐
q_1: ┤ X ├──┼──┤ H ├────────┼──┤ X ├┤ X ├─────────────────────
     └───┘┌─┴─┐├───┤        │  └─┬─┘└─┬─┘     ┌───┐
q_2: ─────┤ X ├┤ H ├────────┼────┼────┼───────┤ X ├───────────
          └───┘└───┘ ┌───┐  │    │    │  ┌───┐└─┬─┘┌─┐
a_0: ────────────────┤ H ├──■────■────┼──┤ H ├──┼──┤M├────────
                     ├───┤            │  └───┘  │  └╥┘┌───┐┌─┐
a_1: ────────────────┤ H ├────────────■─────────■───╫─┤ H ├┤M├
                     └───┘                          ║ └───┘└╥┘
s: 2/═══════════════════════════════════════════════╩═══════╩═
                                                    0       1
```

**Syndrome table** (same pattern as the bit-flip code):

| Error           | State after error                                       | $a_0$ | $a_1$ |
|-----------------|---------------------------------------------------------|-------|-------|
| none            | $\alpha\|{+}{+}{+}\rangle + \beta\|{-}{-}{-}\rangle$    | 0     | 0     |
| $Z$ on $q_0$    | $\alpha\|{+}{+}{-}\rangle + \beta\|{-}{-}{+}\rangle$    | 1     | 0     |
| $Z$ on $q_1$    | $\alpha\|{+}{-}{+}\rangle + \beta\|{-}{+}{-}\rangle$    | 1     | 1     |
| $Z$ on $q_2$    | $\alpha\|{-}{+}{+}\rangle + \beta\|{+}{-}{-}\rangle$    | 0     | 1     |

- **Correction:** apply a $Z$ gate to the qubit with the error, since $Z \cdot Z = I$.

## Next Step

- Each 3-qubit code protects against only one kind of error. **Shor's 9-qubit code** combines them by
  using the phase-flip code on the outside and a bit-flip code inside each of its 3 qubits. It can
  correct any single-qubit error ($X$, $Z$, or $Y = iXZ$).
