using IonSim

function simulate_with_ion_sim(pulses, num_ions)
    # This function should return a list of values between 0.0 and 1.0.
    # The list represents the probability of each possible readout state.
    # The length of the list returned should be 2**num_ions.
    # i.e., for num_ions=1, the returned list should be of length 2
    #       for num_ions=3, the returned list should be of length 8, etc.
    
    # BEGIN TEMP
    # Call IonSim for real here, using "pulses" and "num_ions".
    # This is just an example showing how to call some IonSim code:
    ion = ca40(selected_level_structure=["S-1/2", "D-1/2"])
    return [0.1, 0.9] # fake single-ion result indicating P(S)=0.1, P(D)=0.9
    # END TEMP
end