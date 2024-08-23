import sys
import pandas as pd
import pyomo.environ as pyo

from pyomo.opt import SolverFactory
from pyomo.environ import *
from pyomo.network import *

from mpisppy.opt.ph import PH
from mpisppy.opt.lshaped import LShapedMethod
from mpisppy.utils.sputils import scenario_tree
from mpisppy.utils import config
import mpisppy.utils.sputils as sputils
import mpisppy.utils.solver_spec as solver_spec



import assets.chp as chp
import assets.boiler as boiler
import assets.heat_storage as heat_storage
import assets.grid as grid


# Path
PATH_IN = 'data/input/'
PATH_OUT = 'data/output/'

# Declare constants
GAS_PRICE = 0.1543 # €/kWh  (HS)
POWER_PRICE = 0.251 # €/kWh (el)
HEAT_PRICE = 0.105 # €/kWh (th)
CALORIFIC_VALUE_NGAS = 10 # kWh/m3

# CHP 
CHP_BONUS_SELF_CONSUMPTION= 0.08  # €/kWhel
CHP_BONUS= 0.16  # €/kWhel
CHP_INDEX_EEX= 0.1158  # €/kWhel
ENERGY_TAX_REFUND_GAS= 0.0055  # €/kWhHS
AVOIDED_GRID_FEES= 0.0097  # €/kWhel
SHARE_SELF_CONSUMPTION= 0.03 # %
SHARE_FEED_IN= 0.97 # %

# Costs
MAINTENANCE_COSTS = 1.8 # €/kWh (HS)


class Model:
    """Model class."""
    
    def __init__(self):
        self.model = AbstractModel()
        self.instance = None
        self.solver = None
        self.timeseries_data = None
        self.results = None
        self.results_data = None

    def set_solver(self, solver_name, **kwargs):
        self.solver = SolverFactory(solver_name)
        
        for key in kwargs:
            self.solver.options[key] = kwargs[key]    


    def load_timeseries_data(self):
        """Load timeseries data from file."""
        self.timeseries_data = DataPortal()

        self.timeseries_data.load(
            filename=PATH_IN + '/demands/heat_demand_20230401.csv',
            index='t',
            param='heat_demand'
        )

    def add_components(self):
        """Add components to the model."""

        # Sets
        self.model.t = Set(ordered=True)
    
        # Parameters
        self.model.GAS_PRICE = Param(initialize=GAS_PRICE)
        self.model.POWER_PRICE = Param(initialize=POWER_PRICE)
        self.model.HEAT_PRICE = Param(initialize=HEAT_PRICE)
        self.model.heat_demand = Param(self.model.t)



        # Assets

        chp_filepaths = [
            PATH_IN + '/assets/chp.csv',
            PATH_IN + '/assets/chp_operation.csv'
        ]

        boiler_filepaths = [
            PATH_IN + '/assets/boiler.csv',
            PATH_IN + '/assets/boiler_operation.csv'
        ]

        chp1 = chp.Chp(
            'chp1', chp_filepaths
        )


        # chp1 = chp.Chp(
        #     'chp1', PATH_IN + '/assets/chp.csv'
        # )

        boiler1 = boiler.Boiler(
            'boiler1', boiler_filepaths
        )

        #boiler1 = boiler.Boiler(
        #    'boiler1', PATH_IN + '/assets/boiler.csv'
        #)

        heat_storage1 = heat_storage.HeatStorage(
            'heat_storage1', PATH_IN + '/assets/heat_storage.csv'
        )

        ngas_grid = grid.NGasGrid('ngas_grid')

        power_grid = grid.ElectricalGrid(
            'power_grid', PATH_IN + '/assets/power_grid.csv'
        )

        heat_grid = grid.HeatGrid(
            'heat_grid', PATH_IN + '/assets/heat_grid.csv'
        )

        chp1.add_to_model(self.model)
        boiler1.add_to_model(self.model)
        heat_storage1.add_to_model(self.model)
        ngas_grid.add_to_model(self.model)
        power_grid.add_to_model(self.model)
        heat_grid.add_to_model(self.model)

        # Expressions

        def first_stage_cost_rule(model):
            return quicksum(model.chp1.gas[t] * model.price_scenario for t in model.t)
        self.model.FirstStageCost = Expression(rule=first_stage_cost_rule)

        def second_stage_cost_rule(model):
            return 2
        self.model.SecondStageCost = Expression(rule=second_stage_cost_rule)

        # Testing 



    def add_objective(self):
        """Add objective function to model."""
        self.model.objective = Objective(
            rule=self.objective_expr,
            sense=minimize
        )
      
    # def instantiate_model(self, scenario_name=None, **scenario_creator_kwargs):
    #     if scenario_name is None:
    #         # Fallback to deterministic model
    #         self.instance = self.model.create_instance(self.timeseries_data)

    #     else:
    #         self.instance = self.scenario_creator(scenario_name, **scenario_creator_kwargs)
        

    ## **scenario_creator_kwargs später hinzufügen
    def scenario_creator(self, scenario_name, use_integer=False, sense=pyo.minimize, crops_multiplier=1, num_scens=None):
        """Create a scenario for the energy system model.
        
        Parameters:
        scenario_name: str
            Name of the scenario to construct.
        use_integer: bool, optional
            If True, restricts variables to be integer. Default is False.
        sense: int, optional
            Model sense (minimization or maximization). Must be either pyo.minimize or pyo.maximize. Default is pyo.minimize.
        crops_multiplier: int, optional
            Factor to control scaling. There will be three times this many crops. Default is 1.
        num_scens: int, optional
            Number of scenarios. We use it to compute _mpisppy_probability. Default is None.
        seedoffset: int, optional
            Used by confidence interval code. Default is 0.
        """
        # My abstract model
        model = self.model

        # Brauche ich nicht
        # scenario_base_name = scenario_name.rstrip('1234567890')
        # print("scenario_base_name=", scenario_base_name)
        

        # Use the scenario_creator function to create a stochastic model
        scennum = sputils.extract_num(scenario_name)
        basenames = ['FirstScenario', 'SecondScenario', 'ThirdScenario']
        basenum = scennum % 3
        groupnum = scennum // 3
        scenname = basenames[basenum] + str(groupnum)
        print(f"Creating scenario {scenname} from {scenario_name}")

        scenario_base_name = scenname.rstrip('1234567890')
        print(f"Creating scenario base name {scenario_base_name} from {scenname}")

        # Check for minimization vs. maximization
        if sense not in [pyo.minimize, pyo.maximize]:
            raise ValueError("Model sense Not recognized")
            
        ##### Create the concrete model object #####
        
        """Hier müssen meine konkreten Daten rein"""
        #____________ Add Stochastic ____________
       
        # Define the price scenarios for the gas price
        price_scenario = {
            'FirstScenario': {'GAS_PRICE': 0.1541},
            'SecondScenario': {'GAS_PRICE': 0.1542},
            'ThirdScenario': {'GAS_PRICE': 0.1543}
}

        def price_init(m ,t):
            price_base_name = 'GAS_PRICE'
            return price_scenario[scenario_base_name][price_base_name]
        
        self.model.price_scenario = Param(within=NonNegativeReals, initialize=price_init, mutable=True)

        instance = model.create_instance(self.timeseries_data)


        if num_scens is not None:
            instance._mpisppy_probability = 1 / num_scens
        
        # Varlist ist die Liste der Variablen, die an den Root-Knoten angehängt werden, 
        # also quasi Entscheidung der Ersten Stufe, welche Ausgang für die Zweite Stufe sind
        
        # Variable mit Index t anlegen 
        varlist = [instance.chp1.gas[t] for t in instance.t]
        sputils.attach_root_node(instance, instance.FirstStageCost, varlist)



        return instance



        #_______________________________________
    
    def expand_arcs(self):
        """Expands arcs and generate connection constraints."""
        TransformationFactory('network.expand_arcs').apply_to(self.instance)
    
    def add_instance_components(self, component_name, component):
        """Add components to the instance."""
        self.instance.add_component(component_name, component)

    def add_arcs(self):
        """Add arcs to the instance."""
        self.instance.arc01 = Arc(
            source=self.instance.chp1.power_out,
            destination=self.instance.power_grid.power_in
        )
        self.instance.arc02 = Arc(
            source=self.instance.chp1.heat_out,
            destination=self.instance.heat_storage1.heat_in
        )
        self.instance.arc03 = Arc(
            source=self.instance.heat_storage1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc04 = Arc(
            source=self.instance.boiler1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc05 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.boiler1.gas_in
        )
        self.instance.arc06 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.chp1.gas_in
        )


    # Noch mit einbauen später.

    # def solve(self):
    #     """Solve the model."""
    #     self.results =self.solver.solve(
    #         self.instance,
    #         symbolic_solver_labels=True,
    #         tee=True,
    #         logfile=PATH_OUT + 'logfile.txt',
    #         load_solutions=True,
    #         report_timing=True,
    #     )
    
    def write_results(self):
        """Write results to file."""
        self.results.write()

        df_params = pd.DataFrame()
        df_variables = pd.DataFrame()
        df_output = pd.DataFrame()

        for params in self.instance.component_objects(Param, active=True):
            name = params.name
            if len(params) == 1:
                single_value = value(list(params.values())[0])
                df_params[name]= [single_value for t in self.instance.t]
            else:                        
                df_params[name] = [value(params[t]) for t in self.instance.t]
        
        for variables in self.instance.component_objects(Var, active=True):
            name = variables.name
            df_variables[name] = [value(variables[t]) for t in self.instance.t]

        df_output = pd.concat([df_params, df_variables], axis=1)
        df_output.index = self.instance.t
        df_output.index.name = 't'

        self.results_data = df_output


    def save_results(self, filepath):
        """Save results to object."""
        self.results_data.to_csv(filepath)

    def objective_expr(self, model):
        """Objective function expression."""
        objective_expr = (
            self._ComputeFirstStageCost(model) +
            self._gas_costs(model) +
            self._maintenance_costs(model) -
            self._power_revenue(model) -
            self._heat_revenue(model) -
            self._chp_revenue(model)
        )
        return objective_expr
    
    # Implementierung der Stage Costs war falsch. Expressions für die Stage Costs wurde jetzt weiter oben im Quellcode implementiertö

    def _ComputeFirstStageCost(self, model):
        """Calculate first stage cost."""
        firststagecost = model.FirstStageCost
        return firststagecost
   
    # def _ComputeSecondStageCost(self, model):
    #     """Calculate second stage cost."""
    #     secondstagecost = 0
    #     return secondstagecost
    # model.SecondStageCost = Expression(rule=_ComputeSecondStageCost)

    def _gas_costs(self, model):
        """ Calculate gas costs for CHP and Boiler."""
        gas_costs = (
        quicksum(model.chp1.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t) + 
        quicksum(model.boiler1.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t)
        )
        return gas_costs
    
    def _maintenance_costs(self, model):
        """Calculate maintenance costs for CHP."""
        maintenance_costs = quicksum(model.chp1.bin[t] * MAINTENANCE_COSTS for t in model.t)
        return maintenance_costs

    def _power_revenue(self, model):
        """Calculate power revenue for CHP."""
        power_revenue = quicksum(model.chp1.power[t] * model.POWER_PRICE for t in model.t)
        return power_revenue
    
    def _heat_revenue(self, model):
        """Calculate heat revenue for CHP and Boiler."""
        heat_revenue = (
        quicksum(model.chp1.heat[t] * model.HEAT_PRICE for t in model.t) +
        quicksum(model.boiler1.heat[t] * model.HEAT_PRICE for t in model.t)
        )
        return heat_revenue
    
    def _chp_revenue(self, model):
        """Calculate CHP revenue."""
        chp_bonus_for_self_consumption = quicksum(model.chp1.power[t] * CHP_BONUS_SELF_CONSUMPTION * SHARE_SELF_CONSUMPTION for t in model.t)
        chp_bonus_for_feed_in = quicksum(model.chp1.power[t] * CHP_BONUS * SHARE_FEED_IN for t in model.t)
        chp_index = quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * CHP_INDEX_EEX for t in model.t)
        avoided_grid_fees = quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * AVOIDED_GRID_FEES for t in model.t)
        energy_tax_refund = quicksum(model.chp1.gas[t] * CALORIFIC_VALUE_NGAS * ENERGY_TAX_REFUND_GAS for t in model.t)
        
        chp_revenue = (
            chp_bonus_for_self_consumption +
            chp_bonus_for_feed_in +
            chp_index +
            avoided_grid_fees +
            energy_tax_refund
        )
        return chp_revenue

# ____________ Add Stochastic ____________
    def main_no_cfg(self):
        # Some parameters from sys.argv and some hard-wired.
        if len(sys.argv) != 4:
            print("usage python 4DEnergy.py {crops_multiplier} {scen_count} {solver_name}")
            print("e.g., python 4DEnergy.py 1 3 gurobi")
            quit()

        scenario_creator = self.scenario_creator

        crops_multiplier = int(sys.argv[1])
        scen_count = int(sys.argv[2])
        solver_name = sys.argv[3]
        
        scenario_creator_kwargs = {
            "use_integer": False,
            "crops_multiplier": crops_multiplier,
        }

        scenario_names = ['Scenario' + str(i) for i in range(scen_count)]

        # _____________
        print('Setting solver...')
        self.set_solver(solver_name)

        print('Loading timeseries data...')
        self.load_timeseries_data()

        print('Adding components...')
        self.add_components()

        print('Adding objective...')
        self.add_objective()

        # print('Creating extensive Form...')
        # ef = sputils.create_EF(
        #     scenario_names,
        #     scenario_creator, # must be the concrete Model!!
        #     scenario_creator_kwargs=scenario_creator_kwargs,
        # )

        options = {
            "root_solver": "gurobi",
            "sp_solver": "gurobi",
            "sp_solver_options" : {"threads" : 2},
            "max_iter": 10,
        }

        print('Creating L-Shaped Method...')
        ls = LShapedMethod(options, scenario_names, scenario_creator)
        #result = ls.lshaped_algorithm()

        variables = ls.gather_var_values_to_rank0()
        for ((scen_name, var_name), var_value) in variables.items():
            print(scen_name, var_name, var_value)

        # solver = pyo.SolverFactory(solver_name)
        # solver.solve(ef, tee=True, symbolic_solver_labels=True, logfile=PATH_OUT + 'logfile.txt', load_solutions=True, report_timing=True)
        
        ls.write_tree_solution("output/data/lshaped_res_all_stages")
        ls.write_first_stage_solution("output/data/lshaped_res_first_stage/lshaped_res_first_stage.csv")


        # print('Write results...')
        # self.write_results()
        
        return ls
        

    
    
# ________________________________________ 



if __name__ == "__main__":
    m = Model()

    # print('Setting solver...')
    # m.set_solver(
    #     solver_name= 'gurobi',
    #     MIPGap=0.015,
    #     TimeLimit=30
    #     )

    # print('Loading timeseries data...')
    # m.load_timeseries_data()

    # print('Adding components...')
    # m.add_components()

    # print('Adding objective...')
    # m.add_objective()

    # print('Instantiating model...')
    # m.instantiate_model()

    # print('Declairing arcs...')
    # m.add_arcs()
    # m.expand_arcs()

    print('Solving model...')
    main_ef = m.main_no_cfg()

    print('Writing results...')
    print(f"EF objective: {pyo.value(main_ef.EF_Obj)}")
    #sputils.write_ef_tree_solution(main_ef, "4DEnergy_ef")

    #sputils.ef_ROOT_nonants_npy_serializer(main_ef, "farmer_root_nonants.npy")
    
    result = dict()
    for (sname, scenario) in main_ef.items():
        result[sname] = dict()
        for node in scenario._mpisppy_node_list:
            for var in node.nonant_vardata_list:
                result[sname][var.name] = var.value
        result[sname]['z'] = scenario.z[0].value
    