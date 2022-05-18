# Copyright 2018-2021 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Contains the tape transform that splits non-commuting terms
"""
# pylint: disable=protected-access
import pennylane as qml


def split_non_commuting(tape):
    r"""
    Splits a tape measuring non-commuting observables into groups of commuting observables.

    Args:
        tape (.QuantumTape): the tape used when calculating the expectation value
            of the Hamiltonian

    Returns:
        tuple[list[.QuantumTape], function]: Returns a tuple containing a list of
        quantum tapes to be evaluated, and a function to be applied to these
        tape executions to restore the ordering of the inputs.

    **Example**

    We can create a tape with non-commuting observables:

    .. code-block:: python3

        import pennylane as qml
        with qml.tape.QuantumTape() as tape:
            qml.expval(qml.PauliZ(0))
            qml.expval(qml.PauliY(0))
        tapes, processing_fn = qml.transforms.split_non_commuting(tape)

    Now ``tapes`` is a list of two tapes, each for one of the non-commuting terms.

    >>> [t.observables for t in tapes]
    [[expval(PauliZ(wires=[0]))], [expval(PauliY(wires=[0]))]]

    The processing function becomes important when creating the commuting groups distorts the orde of the inputs.

    .. code-block:: python3

        with qml.tape.QuantumTape() as tape:
            qml.expval(qml.PauliZ(0) @ qml.PauliZ(1))
            qml.expval(qml.PauliX(0) @ qml.PauliX(1))
            qml.expval(qml.PauliZ(0))
            qml.expval(qml.PauliX(0))
        tapes, processing_fn = qml.transforms.split_non_commuting(tape)

    In this example, the groupings are ``group_coeffs = [[0,2], [1,3]]`` and processing_fn makes sure that the final output is of the same shape and ordering:

    >>> processing_fn(tapes)
    tensor([tensor(expval(PauliZ(wires=[0]) @ PauliZ(wires=[1])), dtype=object, requires_grad=True),
        tensor(expval(PauliX(wires=[0]) @ PauliX(wires=[1])), dtype=object, requires_grad=True),
        tensor(expval(PauliZ(wires=[0])), dtype=object, requires_grad=True),
        tensor(expval(PauliX(wires=[0])), dtype=object, requires_grad=True)],
       dtype=object, requires_grad=True)

    """

    measurements = tape.measurements

    obs_list = []
    # get the observables from the measurements
    # TO DO: This loop should become superfluous when the reworked operator classes are implemented
    for measurement in measurements:
        if hasattr(measurement.obs, "obs"):
            # this loop re-creates multi-qubit observables, e.g. PauliZ(0) @ PauliZ(1)
            _list = (
                measurement.obs.obs
            )  # the list of individual observables before composition
            obs = _list[0]
            for ob_i in _list[1:]:
                obs @= ob_i  # I am sure there must be a better way to do this?
        else:
            obs = measurement.obs
        obs_list.append(obs)

    # If there is more than one group of commuting observables, split tapes
    groups, group_coeffs = qml.grouping.group_observables(obs_list, range(len(obs_list)))
    if len(groups) > 1:
        # make one tape per commuting group
        tapes = []
        for group in groups:
            with qml.tape.QuantumTape() as new_tape:
                for op in tape.operations:
                    qml.apply(op)

                for o in group:
                    qml.expval(o)

            tapes.append(new_tape)

        def reorder_fn(res):
            """re-order the output to the original shape and order"""
            res = qml.math.concatenate(res)
            new_res = res.copy() # to keep the same format as res
            reorder_indxs = qml.math.concatenate(group_coeffs)
            for i,out in zip(reorder_indxs, res):
                new_res[i] = out

            return new_res

        return tapes, reorder_fn
    # if the group is already commuting, no need to do anything
    return [tapes], lambda res: res[0]
