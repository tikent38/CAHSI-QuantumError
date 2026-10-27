# phase_flip_toffoli.py
# The same phase-flip code as phase_flip_encoded.py, but the error is corrected with a Toffoli (CCNOT) gate
# inside the circuit instead of measuring ancillas and using if blocks.

# Reuse the encoding and the gate handling from phase_flip_encoded.py, and the Toffoli correction from
# bit_flip_toffoli.py, so the code is built exactly the same way as the bit-flip one
from bit_flip_toffoli import toffoli_code
from phase_flip_encoded import apply_gates, decode, encode


def phase_flip_toffoli(circuit, measure=True):
    # Returns the phase-flip-code version of a 1-qubit circuit (no measurements in it), corrected with a Toffoli.
    # measure=True also measures the result into the "out" register;
    # measure=False leaves the corrected state decoded on q_0, with the syndrome left on q_1 and q_2.
    # Encoding makes a|+++> + b|--->. Decoding's H gates turn a sign flip into a bit flip, so afterwards q_1 and q_2
    # are the syndrome:
    #   q_1 q_2 = 0 0 -> no flip,  1 0 -> q_1 sign flipped,  0 1 -> q_2 sign flipped,  1 1 -> q_0 sign flipped
    return toffoli_code(circuit, measure, encode, apply_gates, decode)
