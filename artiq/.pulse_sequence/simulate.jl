using IonSim

function simulate_with_ion_sim(parameters, pulses, num_ions)
    # This function should return a list of values between 0.0 and 1.0.
    # The list represents the probability of each possible readout state.
    # The length of the list returned should be 2**num_ions.
    # i.e., for num_ions=1, the returned list should be of length 2
    #       for num_ions=3, the returned list should be of length 8, etc.

    ions = []
    for i = 1:num_ions
        push!(ions, ca40(selected_level_structure=["S-1/2", "D-1/2"]))
    end

    # TODO: If necessary, read parameters here. For example:
    axial_frequency = parameters["TrapFrequencies.axial_frequency"]

    for pulse in pulses
        dds_name = pulse["dds_name"]
        time_on = pulse["time_on"]
        time_off = pulse["time_off"]
        freq = pulse["freq"]
        amp = pulse["amp"]
        att = pulse["att"]
        phase = pulse["phase"]

        # TODO: Do something with this pulse.
    end

    # TODO: Run the simulation and return the result.

    return [0.1, 0.9] # fake single-ion result indicating P(S)=0.1, P(D)=0.9

end