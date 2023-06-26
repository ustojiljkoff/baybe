"""
Run history simulation for a direct arylation where all possible combinations have
been measured. This uses the lookup mechanism that allows us to access information about
previously conducted experiments from .xlsx-files.
"""

import matplotlib.pyplot as plt

import pandas as pd
import seaborn as sns

from baybe.core import BayBE
from baybe.parameters import GenericSubstance, NumericDiscrete
from baybe.searchspace import SearchSpace
from baybe.simulation import simulate_scenarios
from baybe.strategies.sampling import RandomRecommender
from baybe.strategies.strategy import Strategy
from baybe.targets import NumericalTarget, Objective

# We read the information about the conducted expderiments from a .xlsx-file and save it
# as a pandas DataFrame.
# NOTE Depending on your sysem and settings, you might need to slightly adjust the
# following path as this is relevant to the folder in which you execute the 'python'
# call. This path assumes that this call is made from the main BayBE folder.

lookup = pd.read_excel("examples/Simulation_and_Lookup/lookup.xlsx")

# As usual, we set up some experiment. Note that we now need to ensure that the names
# fit the names in the provided .xlsx file!
dict_solvent = {
    "DMAc": r"CC(N(C)C)=O",
    "Butyornitrile": r"CCCC#N",
    "Butyl Ester": r"CCCCOC(C)=O",
    "p-Xylene": r"CC1=CC=C(C)C=C1",
}
solvent = GenericSubstance(name="Solvent", data=dict_solvent, encoding="MORDRED")

dict_base = {
    "Potassium acetate": r"O=C([O-])C.[K+]",
    "Potassium pivalate": r"O=C([O-])C(C)(C)C.[K+]",
    "Cesium acetate": r"O=C([O-])C.[Cs+]",
    "Cesium pivalate": r"O=C([O-])C(C)(C)C.[Cs+]",
}
base = GenericSubstance(name="Base", data=dict_base, encoding="MORDRED")

dict_ligand = {
    "BrettPhos": r"CC(C)C1=CC(C(C)C)=C(C(C(C)C)=C1)C2=C(P(C3CCCCC3)C4CCCCC4)C(OC)="
    "CC=C2OC",
    "Di-tert-butylphenylphosphine": r"CC(C)(C)P(C1=CC=CC=C1)C(C)(C)C",
    "(t-Bu)PhCPhos": r"CN(C)C1=CC=CC(N(C)C)=C1C2=CC=CC=C2P(C(C)(C)C)C3=CC=CC=C3",
    "Tricyclohexylphosphine": r"P(C1CCCCC1)(C2CCCCC2)C3CCCCC3",
    "PPh3": r"P(C1=CC=CC=C1)(C2=CC=CC=C2)C3=CC=CC=C3",
    "XPhos": r"CC(C1=C(C2=CC=CC=C2P(C3CCCCC3)C4CCCCC4)C(C(C)C)=CC(C(C)C)=C1)C",
    "P(2-furyl)3": r"P(C1=CC=CO1)(C2=CC=CO2)C3=CC=CO3",
    "Methyldiphenylphosphine": r"CP(C1=CC=CC=C1)C2=CC=CC=C2",
    "1268824-69-6": r"CC(OC1=C(P(C2CCCCC2)C3CCCCC3)C(OC(C)C)=CC=C1)C",
    "JackiePhos": r"FC(F)(F)C1=CC(P(C2=C(C3=C(C(C)C)C=C(C(C)C)C=C3C(C)C)C(OC)=CC=C2OC)"
    r"C4=CC(C(F)(F)F)=CC(C(F)(F)F)=C4)=CC(C(F)(F)F)=C1",
    "SCHEMBL15068049": r"C[C@]1(O2)O[C@](C[C@]2(C)P3C4=CC=CC=C4)(C)O[C@]3(C)C1",
    "Me2PPh": r"CP(C)C1=CC=CC=C1",
}
ligand = GenericSubstance(name="Ligand", data=dict_ligand, encoding="MORDRED")
temperature = NumericDiscrete(name="Temp_C", values=[90, 105, 120], tolerance=2)
concentration = NumericDiscrete(
    name="Concentration", values=[0.057, 0.1, 0.153], tolerance=0.005
)

parameters = [solvent, base, ligand, temperature, concentration]

# Construct searchspace and objective. Note that the objective is maximization!
searchspace = SearchSpace.create(parameters=parameters)
objective = Objective(
    mode="SINGLE", targets=[NumericalTarget(name="yield", mode="MAX")]
)

# Create two baybe objects: One using the default recommender and one making random
# recommendations.
baybe = BayBE(searchspace=searchspace, objective=objective)
baybe_rand = BayBE(
    searchspace=searchspace,
    strategy=Strategy(recommender=RandomRecommender()),
    objective=objective,
)

# We can now use the simulate_scenarios function from simulation.py to simulate a
# full experiment. Note that this function enables to run multiple scenarios one after
# another by a single function call, which is why we need to define a dictionary
# mapping names for the scenarios to actual baybe objects
scenarios = {"Test_Scenario": baybe, "Random": baybe_rand}

# This is the call to the actual function.
# Note that, in contrast to other cases where we use the lookup functionality, it is
# not necessary to include the 'impute' keyword here as we know that all data is
# part of our table.
BATCH_QUANTITY = 2
N_EXP_ITERATIONS = 5
N_MC_ITERATIONS = 3
results = simulate_scenarios(
    scenarios=scenarios,
    batch_quantity=BATCH_QUANTITY,
    n_exp_iterations=N_EXP_ITERATIONS,
    n_mc_iterations=N_MC_ITERATIONS,
    lookup=lookup,
)

# The following lines plot the results and save the plot in run_full_lookup.png
max_yield = lookup["yield"].max()
sns.lineplot(
    data=results, x="Num_Experiments", y="yield_CumBest", hue="Variant", marker="x"
)
plt.plot(
    [BATCH_QUANTITY, BATCH_QUANTITY * N_EXP_ITERATIONS], [max_yield, max_yield], "--r"
)
plt.legend(loc="lower right")
plt.gcf().set_size_inches(20, 8)
plt.savefig("./run_full_lookup.png")
