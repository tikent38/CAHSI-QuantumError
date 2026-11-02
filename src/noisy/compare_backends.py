# compare_backends.py
# The same experiment as compare_fez.py, but on any of the fake IBM backends instead of only Fez: runs one 1-qubit test
# circuit on that backend's noise simulator with no correction and with each error-correction code, and prints how far
# each result is from the exact answer and how big each circuit is once it is on the backend.
# Change the experiment, and which backend it runs on, in the settings block at the bottom of the file
import math
import os
import random
import sys
from collections import deque
from functools import cache
from itertools import combinations

from qiskit import transpile
from qiskit.circuit import Gate
from qiskit.quantum_info import PTM, Statevector, average_gate_fidelity
from qiskit.transpiler import Target, TranspilerError
from qiskit_aer import AerSimulator
from qiskit_aer.noise.device import basic_device_gate_errors, basic_device_readout_errors
from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

# Reuse the test circuits, the codes and the results table from compare_fez.py, so the only difference is the backend
from compare_fez import CODES, DEFAULT_CODES, GATE_SETS, encode_all, print_results, test_circuit
from fez_common import (DEFAULT_ANCILLA_QUBITS, DEFAULT_DATA_QUBITS, DEFAULT_SHOR_ANCILLA_QUBITS,
                        DEFAULT_SHOR_DATA_QUBITS, physical_qubits, prob_one)

# The code for printing tables lives in src/output_tools
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output_tools"))
from output_tools import print_table_header

# Every backend compare() can run on, by its short name (e.g. "fez", "torino", "brisbane"): the fake IBM backends in
# qiskit_ibm_runtime, which are copies of real IBM machines with their wiring and noise
BACKENDS = sorted(b.name.removeprefix("fake_") for b in FakeProviderForBackendV2().backends())
# How compare() picks a backend's qubits when it isn't told which to use (on Fez both give the fez_common.py defaults):
#   "best"      the backend's least noisy qubits (see auto_qubits)
#   "like fez"  the qubits whose noise is closest to the Fez defaults, wired the same way (see matched_qubits), so
#               every backend runs with about the same noise as Fez
PICKS = ("best", "like fez")


# ---- The backend ----

def short_name(name):
    # The backend's short name, e.g. "fez" for "fez", "fake_fez" or "FakeFez" ("FakeCairoV2" -> "cairo")
    short = name.lower().removeprefix("fake").removeprefix("_").removesuffix("v2")
    if short not in BACKENDS:
        raise ValueError(f"unknown backend '{name}'; use any of {BACKENDS}")
    return short


def get_backend(name):
    # A new copy of the fake backend called name
    return FakeProviderForBackendV2().backend(f"fake_{short_name(name)}")


def backend_label(backend):
    # The name printed for a backend, e.g. "Fez" for fake_fez
    return backend.name.removeprefix("fake_").capitalize()


def working_target(backend, max_error=0.5):
    # The backend's target (its gates, connections and error rates) without connections whose error is max_error or
    # more: fake backends list a broken connection with an error of 1.0, and routing through one would ruin the
    # circuit. The same as working_target in src/real_hardware_runs/hardware_common.py. compare_fez.py leaves the
    # broken connections out of the CZ wiring instead, which only works on backends whose 2-qubit gate is CZ
    target = backend.target
    kept = Target(num_qubits=target.num_qubits, dt=target.dt, granularity=target.granularity,
                  min_length=target.min_length, pulse_alignment=target.pulse_alignment,
                  acquire_alignment=target.acquire_alignment, qubit_properties=target.qubit_properties,
                  concurrent_measurements=target.concurrent_measurements)
    for name in target.operation_names:
        props = target[name]
        if props is None or list(props) == [None]:
            props = None   # available on every qubit (e.g. if_else, barrier)
        else:
            props = {qargs: p for qargs, p in props.items()
                     if len(qargs) < 2 or p is None or p.error is None or p.error < max_error}
        kept.add_instruction(target.operation_from_name(name), props, name=name)
    return kept


# ---- Picking the qubits ----

def gates(target, num_qubits):
    # The backend's gates that act on num_qubits qubits, as {name: {qubits: error}} (measure and reset aren't gates)
    found = {}
    for name in target.operation_names:
        op, props = target.operation_from_name(name), target[name]
        if isinstance(op, Gate) and op.num_qubits == num_qubits and props is not None:
            found[name] = {qargs: (p.error or 0) if p is not None else 0 for qargs, p in props.items() if qargs}
    return found


def qubit_error(target, q):
    # How bad a qubit is: its readout error plus its worst 1-qubit gate error (rz has none, it is done in software)
    measure = target["measure"].get((q,)) if "measure" in target.operation_names else None
    readout = (measure.error or 0) if measure is not None else 0
    return readout + max((errors[(q,)] for errors in gates(target, 1).values() if (q,) in errors), default=0)


def wiring(target):
    # Every working connection, as {qubit: {neighbour: error of the 2-qubit gate between them}}. Either direction
    # counts, and when a pair has more than one 2-qubit gate (e.g. Cairo's CX and ECR) the better one counts
    graph = {}
    for errors in gates(target, 2).values():
        for (a, b), error in errors.items():
            for q, n in ((a, b), (b, a)):
                graph.setdefault(q, {})[n] = min(error, graph.get(q, {}).get(n, 1))
    return graph


def nearest(graph, error, sources, k, used):
    # Up to k unused qubits closest to sources along the wiring (fewest connections away), the best ones first among
    # those equally close. Adds them to used
    distance, queue = {q: 0 for q in sources}, deque(sources)
    while queue:
        q = queue.popleft()
        for n in graph[q]:
            if n not in distance:
                distance[n] = distance[q] + 1
                queue.append(n)
    picked = sorted((q for q in distance if q not in used), key=lambda q: (distance[q], error[q]))[:k]
    used.update(picked)
    return picked


def grow(graph, error, start, k, used):
    # k unused qubits running along the wiring from start: each is the best unused neighbour of the one before, or,
    # at a dead end, the closest unused qubit. Adds them to used
    picked, last = [], start
    while len(picked) < k:
        free = [n for n in graph[last] if n not in used]
        if free:
            last = min(free, key=lambda n: error[n] + graph[last][n])
            used.add(last)
        else:
            closest = nearest(graph, error, [start] + picked, 1, used)
            if not closest:
                break
            last = closest[0]
        picked.append(last)
    return picked


def auto_qubits(backend):
    # Picks qubits on any backend the way the Fez defaults in fez_common.py were picked by hand:
    #   bit/phase-flip data: q_0 wired to both q_1 and q_2, so encoding and decoding need no SWAPs. Of every qubit and
    #       two of its neighbours, the three (and two connections) with the smallest total error
    #   bit/phase-flip ancillas: the 2 best qubits closest to the data qubits
    #   Shor data: its outer phase-flip code (q_0, q_3, q_6) on the same qubits as the bit/phase-flip data (q_0, q_2,
    #       q_1), and each block's other two qubits running along the wiring from its first one
    #   Shor ancillas: the 8 best qubits closest to the Shor data qubits
    # A role the backend doesn't have enough connected qubits for is None, and the codes that need it are skipped
    target = working_target(backend)
    graph = wiring(target)
    error = {q: qubit_error(target, q) for q in graph}
    centres = [(error[q] + sum(error[n] + graph[q][n] for n in pair), q, pair)
               for q in graph for pair in combinations(sorted(graph[q]), 2)]
    if not centres:
        return dict(data=None, ancillas=None, shor_data=None, shor_ancillas=None)
    _, q0, (q1, q2) = min(centres)
    data = (q0, q1, q2)
    ancillas = tuple(nearest(graph, error, data, 2, set(data)))

    used = set(data)
    shor_data = []
    for head in (q0, q2, q1):
        shor_data += [head] + grow(graph, error, head, 2, used)
    shor_ancillas = tuple(nearest(graph, error, shor_data, 8, set(shor_data)))
    return dict(data=data, ancillas=ancillas if len(ancillas) == 2 else None,
                shor_data=tuple(shor_data) if len(shor_data) == 9 else None,
                shor_ancillas=shor_ancillas if len(shor_data) == 9 and len(shor_ancillas) == 8 else None)


# ---- Picking qubits with the same noise as Fez's ----

FLOOR = 1e-6   # the smallest error compared, so an error listed as 0 can still be compared on a log scale


@cache
def noise_levels(name):
    # The noise the simulator of backend name puts on each qubit and connection, from the same Aer functions
    # AerSimulator.from_backend builds its noise from: ({qubit: (bit flips per gate, phase flips per gate, readout
    # error)}, {(a, b): error of the 2-qubit gate between a and b, a < b}), for the qubits and working connections.
    # The 1-qubit numbers are from the X gate (u3 on backends without one), which gets the same noise as SX and id.
    # They are the gate's whole error, T1/T2 relaxation included, which can be bigger than the backend's listed gate
    # error (e.g. Fez qubit 87, whose T1 is only 27 us). Takes a few seconds on 156 qubits, so it runs once a backend
    backend = get_backend(name)
    graph = wiring(working_target(backend))
    readout = {qargs[0]: (err.probabilities[0][1] + err.probabilities[1][0]) / 2
               for qargs, err in basic_device_readout_errors(target=backend.target)}
    one, links = {}, {}
    for gate, qargs, err in basic_device_gate_errors(target=backend.target):
        if len(qargs) == 1:
            one.setdefault(gate, {})[qargs[0]] = err
            continue
        pair = tuple(sorted(qargs))
        if qargs[1] in graph.get(qargs[0], {}) and (gate, pair) not in links:   # one direction of each pair is enough
            links[gate, pair] = 1 - average_gate_fidelity(err.to_quantumchannel())
    x_errors = next(one[g] for g in ("x", "u3", "sx", "u2") if g in one)
    qubits = {}
    for q in graph:
        # The X gate's error as a Pauli transfer matrix: its diagonal says how much of X, Y and Z survives, so
        # (1 - Z part) / 2 is the chance of a bit flip and (1 - X part) / 2 the chance of a phase flip
        ptm = PTM(x_errors[q].to_quantumchannel()).data.real
        qubits[q] = ((1 - ptm[3, 3]) / 2, (1 - ptm[1, 1]) / 2, readout[q])
    pairs = {}
    for (gate, pair), error in links.items():   # a pair with more than one 2-qubit gate keeps the better one
        pairs[pair] = min(error, pairs.get(pair, 1))
    return qubits, pairs


def mismatch(levels, fez_levels):
    # How different two qubits' (or connections') noise numbers are: how many times bigger one is than the other, on a
    # log scale (|ln(a / b)|), added up over the numbers. Twice as noisy counts the same as half as noisy
    return sum(abs(math.log(max(a, FLOOR) / max(b, FLOOR))) for a, b in zip(levels, fez_levels))


def fez_tree(qubits, graph):
    # Fez's qubits as a tree to copy onto another backend: [(Fez qubit, index of the earlier one it is wired to)], and
    # where in the tree each of qubits is. A qubit not wired to an earlier one is joined to them along the shortest
    # path on Fez, and the qubits on that path go in the tree too, so it ends up as far from them as on Fez (e.g. the
    # bit/phase-flip ancilla 108, which is joined to ancilla 97 through 107)
    tree, at = [(qubits[0], None)], {qubits[0]: 0}
    for q in qubits[1:]:
        back, queue = {s: None for s in at}, deque(at)
        while q not in back:   # breadth-first from the tree's qubits until q is reached
            a = queue.popleft()
            for n in graph[a]:
                if n not in back:
                    back[n] = a
                    queue.append(n)
        path = [q]
        while back[path[-1]] is not None:
            path.append(back[path[-1]])
        for prev, nxt in zip(path[::-1], path[::-1][1:]):
            at[nxt] = len(tree)
            tree.append((nxt, at[prev]))
    return tree, [at[q] for q in qubits]


def placements(tree, graph, cost, start=()):
    # Every way to put tree's qubits on the backend's qubits, each used once and each wired to the one its parent is
    # on, as [(total mismatch, (backend qubit for each tree qubit))]. start: the first part, already placed, to extend.
    # cost(i, q, parent_q) is the mismatch of putting tree qubit i on backend qubit q, next to parent_q
    found = []

    def place(placed, total):
        i = len(placed)
        if i == len(tree):
            found.append((total, tuple(placed)))
            return
        parent = tree[i][1]
        for q in (graph if parent is None else graph[placed[parent]]):
            if q not in placed:
                parent_q = None if parent is None else placed[parent]
                place(placed + [q], total + cost(i, q, parent_q))

    place(list(start), 0)
    return found


@cache
def matched_qubits(name):
    # Like auto_qubits, but on backend name picks the qubits whose noise is closest to that of the Fez defaults in
    # fez_common.py (see noise_levels and mismatch), wired to each other the way those are on Fez. Each code's data
    # qubits are matched as closely as possible first, then its ancillas around them. Only Fez's default qubits are
    # matched, so changing those in fez_common.py changes what every backend is matched to. A role the backend
    # doesn't have room for is None, and the codes that need it are skipped
    fez_levels, fez_links = noise_levels("fez")
    levels, links = noise_levels(name)
    fez_graph = wiring(working_target(get_backend("fez")))
    graph = {q: [n for n in ns if n in levels] for q, ns in wiring(working_target(get_backend(name))).items()
             if q in levels}
    picked = {}
    for role, data, ancillas in (("", DEFAULT_DATA_QUBITS, DEFAULT_ANCILLA_QUBITS),
                                 ("shor_", DEFAULT_SHOR_DATA_QUBITS, DEFAULT_SHOR_ANCILLA_QUBITS)):
        tree, at = fez_tree(data + ancillas, fez_graph)

        def cost(i, q, parent_q):
            fez_q, parent = tree[i]
            total = mismatch(levels[q], fez_levels[fez_q])
            if parent_q is not None:
                fez_pair = tuple(sorted((fez_q, tree[parent][0])))
                total += mismatch([links[tuple(sorted((q, parent_q)))]], [fez_links[fez_pair]])
            return total

        firsts = sorted(placements(tree[:at[len(data) - 1] + 1], graph, cost))   # the data qubits, best first
        best = None
        for _, first in firsts:
            rest = placements(tree, graph, cost, start=first)
            if rest:
                best = min(rest)[1]
                break
        if best is None and firsts:   # no room for the ancillas anywhere: keep the best data qubits
            best = firsts[0][1]
        picked[role + "data"] = tuple(best[i] for i in at[:len(data)]) if best else None
        picked[role + "ancillas"] = (tuple(best[i] for i in at[len(data):])
                                     if best and len(best) == len(tree) else None)
    return picked


def default_qubits(backend, pick="best"):
    # The qubits each role runs on when compare() isn't told: on Fez, the ones picked by hand in fez_common.py (so the
    # results match compare_fez.py and the hardware runs), and on every other backend the ones auto_qubits picks
    # (pick="best") or matched_qubits picks (pick="like fez"), see PICKS
    if pick not in PICKS:
        raise ValueError(f"unknown pick '{pick}'; use any of {PICKS}")
    if backend.name == "fake_fez":
        return dict(data=DEFAULT_DATA_QUBITS, ancillas=DEFAULT_ANCILLA_QUBITS, shor_data=DEFAULT_SHOR_DATA_QUBITS,
                    shor_ancillas=DEFAULT_SHOR_ANCILLA_QUBITS)
    return matched_qubits(short_name(backend.name)) if pick == "like fez" else auto_qubits(backend)


def code_layout(backend, data, ancillas, num_data, num_ancillas, code):
    # One code's layout, data + ancillas, after checking it has the right number of qubits, uses each qubit once, and
    # only uses qubits the backend has. None when there are no data qubits for it, and only the data qubits when there
    # are no ancillas (then only the Toffoli codes, which need no ancillas, can run)
    if data is None:
        return None
    label = backend_label(backend)
    layout = list(data) + list(ancillas or ())
    if len(data) != num_data or (ancillas is not None and len(ancillas) != num_ancillas):
        raise ValueError(f"{code} codes need {num_data} data qubits and {num_ancillas} ancillas, "
                         f"got {len(data)} and {len(ancillas or ())}")
    if len(set(layout)) != len(layout):
        raise ValueError(f"{code} codes can only use each {label} qubit once, got {layout}")
    bad = [q for q in layout if not 0 <= q < backend.num_qubits]
    if bad:
        raise ValueError(f"{label} only has qubits 0-{backend.num_qubits - 1}, got {bad}")
    return layout


def set_layout(backend, data=None, ancillas=None, shor_data=None, shor_ancillas=None, pick="best"):
    # Which of the backend's physical qubits each circuit qubit runs on. data = (qubit for q_0, q_1, q_2), ancillas =
    # (qubit for a_0, a_1) of the bit-flip and phase-flip codes. shor_data = (qubit for q_0, ..., q_8), shor_ancillas =
    # (qubit for a_0, ..., a_7) of the Shor codes. Any left as None are picked by default_qubits, the way pick says
    # (see PICKS). Every code puts its data qubits first and its ancillas after, so each layout is data + ancillas:
    # the Toffoli codes use only the data qubits. The two layouts can share qubits, since every code runs on its own.
    # "no correction" is the qubit the circuit runs on when no code is run
    picked = default_qubits(backend, pick)
    data, ancillas = picked["data"] if data is None else data, picked["ancillas"] if ancillas is None else ancillas
    shor_data = picked["shor_data"] if shor_data is None else shor_data
    shor_ancillas = picked["shor_ancillas"] if shor_ancillas is None else shor_ancillas
    target = working_target(backend)
    best = min(range(backend.num_qubits), key=lambda q: qubit_error(target, q))
    return {"bit/phase-flip": code_layout(backend, data, ancillas, 3, 2, "bit-flip and phase-flip"),
            "Shor": code_layout(backend, shor_data, shor_ancillas, 9, 8, "Shor"),
            "no correction": (data or shor_data or [best])[0]}


# ---- Helpers ----

def layout_for(name, layouts):
    return layouts["Shor" if name.startswith("Shor") else "bit/phase-flip"]


def skip_unrunnable(encoded, skipped, layouts, backend, pick):
    # Moves the codes the backend can't run into skipped, with the reason: ones needing more connected qubits than
    # it has (e.g. the Shor codes on a 5-qubit backend, or every code on Kyoto, whose fake data lists all its
    # connections as broken), or, with pick="like fez", more than it has room for wired the way the Fez defaults are,
    # and if-block codes on backends that can't run if blocks
    label = backend_label(backend)
    for name, qc in list(encoded.items()):
        layout = layout_for(name, layouts)
        missing = [op for op in qc.count_ops() if op in ("if_else", "switch_case")
                   and op not in backend.target.operation_names]
        if (layout is None or len(layout) < qc.num_qubits) and pick == "like fez" and backend.name != "fake_fez":
            skipped[name] = (f"needs {qc.num_qubits} qubits wired the way the Fez default qubits are, and {label} "
                             "doesn't have room for them (picking its qubits with \"best\" doesn't need that)")
        elif layout is None or len(layout) < qc.num_qubits:
            skipped[name] = (f"needs {qc.num_qubits} qubits joined by working connections, and {label} doesn't have "
                             "that many")
        elif missing:
            skipped[name] = f"{label} can't run {', '.join(missing)} (the if blocks)"
        else:
            continue
        del encoded[name]


def on_backend(plain, encoded, skipped, backend, layouts, seed):
    # Every circuit converted to the backend's gates and placed on its qubits.
    # optimization_level=0 keeps every gate: otherwise the transpiler would merge the test gates into one or two.
    # The target passed in leaves out the backend's broken connections (see working_target). Every code starts on the
    # same qubits (layouts), so differences between the codes don't come from landing on better or worse qubits.
    # Routing moves a code's qubits around with SWAPs, so its result is often measured on a different qubit than the
    # one q_0 started on. As in compare_fez.py, no correction runs on the qubit each code is measured on, so both are
    # read out on the same physical qubit (with no codes, it runs on layouts["no correction"]).
    # A code the transpiler can't put on the backend is moved into skipped, with the reason. This happens on Cairo:
    # some of its CX gates only work one way, and the transpiler can't turn a CX around without an H gate, which Cairo
    # doesn't have.
    # Returns the circuits, {run: circuit}, and the no-correction run each code is compared with, {code: run}
    options = dict(optimization_level=0, routing_method="sabre", seed_transpiler=seed, target=working_target(backend))
    label = backend_label(backend)
    coded = {}
    for name, qc in list(encoded.items()):
        try:
            coded[name] = transpile(qc, initial_layout=layout_for(name, layouts)[:qc.num_qubits], **options)
        except TranspilerError as err:
            skipped[name] = f"the transpiler can't put it on {label}: {str(err).strip(chr(39))}"
            del encoded[name]
    measured_on = {name: physical_qubits(qc)[1] for name, qc in coded.items()}
    plain_for = {name: f"no correction ({label} {q})" for name, q in measured_on.items()}
    circuits = {f"no correction ({label} {q})": transpile(plain, initial_layout=[q], **options)
                for q in dict.fromkeys(measured_on.values()) or [layouts["no correction"]]}
    circuits.update(coded)
    return circuits, plain_for


def run_all(plain, circuits, backend, shots, seed):
    # [(name, counts)]: the test circuit on a perfect simulator, then every circuit on the backend's noise simulator.
    # method="statevector" runs every shot on its own: it applies the gates one by one, with random errors picked
    # from the backend's noise for that shot, and measures at the end. Left to itself Aer would use a density matrix
    # for the circuits with no if blocks, working out the exact probabilities and sampling every shot from them
    runs = [("no noise", AerSimulator().run(plain, shots=shots).result().get_counts())]
    noisy_sim = AerSimulator.from_backend(backend, method="statevector")
    for name, circuit in circuits.items():
        counts = noisy_sim.run(circuit, shots=shots, seed_simulator=seed).result().get_counts()
        runs.append((f"{backend_label(backend)} noise, {name}", counts))
    return runs


# ---- Printing ----

def print_match(backend, data):
    # Each bit/phase-flip data qubit's noise next to that of the Fez default qubit with the same role, and the same
    # for the connections q_0-q_1 and q_0-q_2, to see how closely pick="like fez" matched them
    def numbers(levels):
        return "  ".join(f"{x:.1e}" for x in levels)
    label = backend_label(backend)
    fez_levels, fez_links = noise_levels("fez")
    levels, links = noise_levels(short_name(backend.name))
    width = max(len(label), 3) + 5
    print(f"Noise (bit flips per X gate, phase flips per X gate, readout error) of each data qubit, next to the Fez "
          f"qubit it copies:")
    for i, (fez_q, q) in enumerate(zip(DEFAULT_DATA_QUBITS, data)):
        print(f"  q_{i}   {'Fez ' + str(fez_q) + ':':<{width}}{numbers(fez_levels[fez_q])}     "
              f"{label + ' ' + str(q) + ':':<{width}}{numbers(levels[q])}")
    for i in (1, 2):
        fez_pair = tuple(sorted((DEFAULT_DATA_QUBITS[0], DEFAULT_DATA_QUBITS[i])))
        pair = tuple(sorted((data[0], data[i])))
        print(f"  q_0-q_{i} 2-qubit gate error: Fez {fez_links[fez_pair]:.1e}   {label} {links.get(pair, float('nan')):.1e}")


def print_setup(backend, gate_set, num_gates, seed, mirror, shots, layouts, exact_p1, skipped, plain_for, pick,
                given=None):
    # given: the test circuit compare() was handed, if it wasn't made from gate_set
    label = backend_label(backend)
    print(f"Backend:       {label} ({backend.name}, {backend.num_qubits} qubits)")
    if given is not None:
        counts = ", ".join(f"{gate}:{n}" for gate, n in given.count_ops().items())
        print(f"Given circuit: {given.size()} gates ({counts})")
    else:
        kind, gate_names = GATE_SETS[gate_set]
        print(f"{kind.capitalize()} circuit: {num_gates} gates from {', '.join(gate_names)}  (seed {seed}"
              f"{', mirrored' if mirror else ''})")
    print(f"Shots per run: {shots}")
    small, shor = layouts["bit/phase-flip"], layouts["Shor"]
    print(f"{label + ' qubits:':<15}bit/phase-flip " + (f"data {small[:3]}, ancillas {small[3:]}" if small else "none"))
    print(" " * 15 + "Shor " + (f"data {shor[:9]}, ancillas {shor[9:]}" if shor else "none"))
    if pick == "like fez" and small and backend.name != "fake_fez":
        print_match(backend, small[:3])
    print("Compared with:  " + ",  ".join(f"{name} -> {run}" for name, run in plain_for.items())
          + "  (no correction runs on the qubit each code is measured on)")
    print(f"Exact answer:  P(0) = {1 - exact_p1:.4f}   P(1) = {exact_p1:.4f}")
    for name, err in skipped.items():
        print(f"Skipped {name}: {err}")
    print()


def print_sizes(backend, circuits, exact_p1):
    # Each transpiled circuit's size: gates (barriers left out, measurements counted), two-qubit gates, depth, and how
    # many of each gate
    print(f"\nTranspiled circuits on {backend_label(backend)}:")
    size_width = max(22, max(len(name) for name in circuits) + 2)
    print_table_header(f"  {'run':<{size_width}}{'gates':>8}{'2-qubit':>9}{'depth':>8}   gate counts")
    for name, circuit in circuits.items():
        counts = " ".join(f"{gate}:{n}" for gate, n in circuit.count_ops().items() if gate != "barrier")
        print(f"  {name:<{size_width}}{circuit.size():>8}{circuit.num_nonlocal_gates():>9}{circuit.depth():>8}"
              f"   {counts}")
    if 0.35 < exact_p1 < 0.65:
        print("\nNote: the exact answer is close to 50/50, and noise tends to push results toward 50/50,")
        print("so noise is hard to see here. Try another SEED or set MIRROR = True (exact answer is then always 0).")


def compare(backend="fez", num_gates=1000, shots=1000, seed=None, gate_set="all", mirror=False, codes=DEFAULT_CODES,
            data_qubits=None, ancilla_qubits=None, shor_data_qubits=None, shor_ancilla_qubits=None, pick="best",
            circuit=None, show=True):
    # backend: which fake backend to run on (any of BACKENDS, e.g. "fez", "torino", "brisbane").
    # gate_set: which test circuit (a key of GATE_SETS). codes: which codes to compare (keys of CODES).
    # circuit: a 1-qubit test circuit (no measurements) to run instead of making one from gate_set. Unlike the gate
    # sets it may have H gates, which the bit-flip and phase-flip codes decode around (src/pay_off/pay_off_h.py)
    # data_qubits / ancilla_qubits: the backend's qubits for the bit-flip and phase-flip codes' q_0-q_2 / a_0-a_1
    # shor_data_qubits / shor_ancilla_qubits: its qubits for the Shor codes' q_0-q_8 / a_0-a_7 (see set_layout)
    # Any qubits left as None are picked for the backend the way pick says: "best" or "like fez" (see PICKS).
    # show=False skips the printing. Returns each run's error, {run: |P(1) - exact P(1)|}, e.g. for
    # "Torino noise, no correction (Torino 12)" and "Torino noise, bit-flip, Toffoli", and the no-correction run each
    # code is compared with, e.g. {"bit-flip, Toffoli": "no correction (Torino 12)"} (src/pay_off/pay_off.py uses both).
    # Codes the backend can't run are left out of both
    if seed is None:
        seed = random.randrange(10**6)
    given = circuit
    if circuit is None:
        circuit = test_circuit(gate_set, num_gates, seed, mirror)
    exact_p1 = Statevector(circuit).probabilities()[1]   # the exact answer, straight from the state: no shots or noise
    plain = circuit.copy()
    plain.measure_all()   # the codes add their own measurement
    encoded, skipped = encode_all(circuit, codes)

    backend = get_backend(backend)
    layouts = set_layout(backend, data_qubits, ancilla_qubits, shor_data_qubits, shor_ancilla_qubits, pick)
    skip_unrunnable(encoded, skipped, layouts, backend, pick)
    circuits, plain_for = on_backend(plain, encoded, skipped, backend, layouts, seed)
    runs = run_all(plain, circuits, backend, shots, seed)

    if show:
        print_setup(backend, gate_set, num_gates, seed, mirror, shots, layouts, exact_p1, skipped, plain_for, pick,
                    given)
        print_results(runs, shots, exact_p1)
        print_sizes(backend, circuits, exact_p1)
    return {name: abs(prob_one(counts)[0] / shots - exact_p1) for name, counts in runs}, plain_for


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    BACKEND = "fez"    # which fake backend to run on: any of BACKENDS, e.g. "fez", "torino", "kingston", "brisbane",
                       # "sherbrooke", "washington", "kolkata", "rome". print(BACKENDS) lists all 68
    NUM_GATES = 100    # how many gates in the circuit
    SHOTS = 1000       # how many times each version of the circuit is run
    SEED = None        # a number (e.g. 3) gives the same circuit every time; None picks a new random one
    GATE_SET = "x"     # "all" = random X, Y, Z, S, T, id     "xz" = random X and Z     "repeat" = X, Y, Z in order,
                       # over and over     "x", "y", "z", "id" = only that gate (Z is done in software, so it adds no
                       # noise; id is only waiting)
    MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0
    # Which codes to compare (keys of CODES). Add "Shor, if blocks" and "Shor, Toffoli" to include the Shor codes,
    # which are much slower and only run Pauli gates (not GATE_SET = "all")
    CODES_TO_RUN = ["bit-flip, if blocks", "bit-flip, Toffoli", "phase-flip, if blocks", "phase-flip, Toffoli"]

    # Which of the backend's qubits to run on (see set_layout). None picks them for the backend: on Fez the defaults in
    # fez_common.py, on any other backend the way PICK_QUBITS says
    PICK_QUBITS = "like fez"     # "like fez" = the qubits whose noise is closest to the Fez defaults', "best" = the
                                 # backend's least noisy qubits
    DATA_QUBITS = None           # bit/phase-flip data q_0, q_1, q_2
    ANCILLA_QUBITS = None        # bit/phase-flip ancilla a_0, a_1 (only the if-block codes use these)
    SHOR_DATA_QUBITS = None      # Shor data q_0, ..., q_8
    SHOR_ANCILLA_QUBITS = None   # Shor ancilla a_0, ..., a_7 (only "Shor, if blocks" uses these)

    compare(backend=BACKEND, num_gates=NUM_GATES, shots=SHOTS, seed=SEED, gate_set=GATE_SET, mirror=MIRROR,
            codes=CODES_TO_RUN, data_qubits=DATA_QUBITS, ancilla_qubits=ANCILLA_QUBITS,
            shor_data_qubits=SHOR_DATA_QUBITS, shor_ancilla_qubits=SHOR_ANCILLA_QUBITS, pick=PICK_QUBITS)
