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

| Error           | State after error                            | $a_0$ | $a_1$ |
|-----------------|----------------------------------------------|-------|-------|
| none            | $\alpha\|000\rangle + \beta\|111\rangle$     | 0     | 0     |
| $X$ on $q_0$    | $\alpha\|001\rangle + \beta\|110\rangle$     | 1     | 0     |
| $X$ on $q_1$    | $\alpha\|010\rangle + \beta\|101\rangle$     | 1     | 1     |
| $X$ on $q_2$    | $\alpha\|100\rangle + \beta\|011\rangle$     | 0     | 1     |



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

To measure this, put the ancillas in $|+\rangle$, use them as the CNOT **controls** with the data qubits as
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


| Error           | State after error                                       | $a_0$ | $a_1$ |
|-----------------|---------------------------------------------------------|-------|-------|
| none            | $\alpha\|{+}{+}{+}\rangle + \beta\|{-}{-}{-}\rangle$    | 0     | 0     |
| $Z$ on $q_0$    | $\alpha\|{+}{+}{-}\rangle + \beta\|{-}{-}{+}\rangle$    | 1     | 0     |
| $Z$ on $q_1$    | $\alpha\|{+}{-}{+}\rangle + \beta\|{-}{+}{-}\rangle$    | 1     | 1     |
| $Z$ on $q_2$    | $\alpha\|{-}{+}{+}\rangle + \beta\|{+}{-}{-}\rangle$    | 0     | 1     |

- **Correction:** apply a $Z$ gate to the qubit with the error, since $Z \cdot Z = I$.

## How the Codes Are Built

The diagrams above show one check on an encoded qubit. The experiments in `src/noisy/` wrap a whole 1-qubit test circuit in the code instead, in the same order every time:

1. Encode.
2. Apply every gate of the test circuit to the encoded qubit.
3. Correct, once.
4. Measure.

The correction only happens at the end, so errors build up for the whole circuit. The code has to fix all of them at once, and two flipped qubits are already too many.

### Gates on the encoded qubit

| Gate in the test circuit | Bit-flip code | Phase-flip code |
|--------------------------|---------------|-----------------|
| $X$                      | $X$ on all 3 qubits | $Z$ on all 3 qubits |
| $Z$                      | $Z$ on all 3 qubits | $X$ on all 3 qubits |
| $Y$, id                  | the same gate on all 3 qubits | the same gate on all 3 qubits |
| $S$, $T$ and other phase gates | the gate on $q_0$ only | $H$, the gate, $H$ on $q_0$ only |
| $H$ and anything else    | decode, the gate on $q_0$, encode again | decode, the gate on $q_0$, encode again |

In the last row the qubit is **not protected** while the gate runs, and each one costs 4 more 2-qubit gates.

### Two ways to correct

- **If blocks** (`bit_flip_encoded.py`, `phase_flip_encoded.py`): measure the parities on 2 ancillas as in the diagrams above, then a classical `switch` picks which qubit to fix, then decode. That's 5 qubits, and the machine has to support mid-circuit measurement and if blocks.
- **Toffoli** (`bit_flip_toffoli.py`, `phase_flip_toffoli.py`, after Reed et al. 2012): decode first, then let a Toffoli fix $q_0$ inside the circuit. That's 3 qubits, with no ancillas and no measurement before the end. The pay-off and real hardware runs use this version.

### The Toffoli correction

Decoding leaves the syndrome on $q_1$ and $q_2$, so they do the ancillas' job:

```
                  ░  ░           ┌───┐ ░ ┌─┐
  q_0: ──■────■───░──░───■────■──┤ X ├─░─┤M├
       ┌─┴─┐  │   ░  ░   │  ┌─┴─┐└─┬─┘ ░ └╥┘
  q_1: ┤ X ├──┼───░──░───┼──┤ X ├──■───░──╫─
       └───┘┌─┴─┐ ░  ░ ┌─┴─┐└───┘  │   ░  ║
  q_2: ─────┤ X ├─░──░─┤ X ├───────■───░──╫─
            └───┘ ░  ░ └───┘           ░  ║
out: 1/═══════════════════════════════════╩═
                                          0
```

The test circuit's gates go between the first two barriers, followed by decoding and the Toffoli.

| Flipped qubit | $q_1$ | $q_2$ | The Toffoli |
|---------------|-------|-------|-------------|
| none          | 0     | 0     | does nothing |
| $q_1$         | 1     | 0     | does nothing: the flip stays on $q_1$ and never reaches $q_0$ |
| $q_2$         | 0     | 1     | does nothing: the flip stays on $q_2$ and never reaches $q_0$ |
| $q_0$         | 1     | 1     | flips $q_0$ back |

- Only a flip on $q_0$ needs fixing, unlike the if blocks, which fix whichever qubit flipped.
- With two or three flipped qubits, $q_0$ ends up wrong, which is the $3p^2 - 2p^3$ failure rate from the repetition code.
- The phase-flip code uses the same Toffoli: decoding's $H$ gates turn a sign flip back into a bit flip, so the table holds with "sign flipped" in place of "flipped".
- The measurement comes after the correction, so the code can't fix a readout error on $q_0$.

**Cost:** encoding and decoding take 2 CNOTs each and the Toffoli takes 6, so 10 2-qubit gates. On the IBM wiring it also needs one SWAP (3 more), which makes 13. The test circuit's gates are all 1-qubit gates, so this stays at 13 however long the circuit is, as long as it has no $H$ gates.

