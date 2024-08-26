import sys
import pandas as pd
import pyomo.environ as pyo

from pyomo.opt import SolverFactory
from pyomo.environ import *
from pyomo.network import *

from mpisppy.opt.ph import PH
from mpisppy.opt.lshaped import LShapedMethod
from mpisppy.opt.ef import ExtensiveForm
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


class Model:
    """Model class."""
    
    def __init__(self):
        self.PATH_IN = PATH_IN
        self.PATH_OUT = PATH_OUT
        self.model = AbstractModel()
        self.instance = None
        self.ef_instance = None
        self.solver = None
        self.timeseries_data = None
        self.results = None
        self.results_data = None
        self._initialize_model_components()

    def _initialize_model_components(self):
        """Initialize basic model components."""
        self.model.t = Set(ordered=True)
        self._define_parameters()
        self._define_assets()
        self._define_expressions()

    def _define_parameters(self):
        """Define model parameters."""
        # Load Constants and the heat demand
        # self.model.GAS_PRICE = Param(initialize=GAS_PRICE)
        self.model.POWER_PRICE = Param(initialize=POWER_PRICE)
        self.model.HEAT_PRICE = Param(initialize=HEAT_PRICE)
        self.model.heat_demand = Param(self.model.t)
        

    def _define_assets(self):
        """Define model assets."""
        chp_filepaths = [
            self.PATH_IN + '/assets/chp.csv',
            self.PATH_IN + '/assets/chp_operation.csv'
        ]

        boiler_filepaths = [
            self.PATH_IN + '/assets/boiler.csv',
            self.PATH_IN + '/assets/boiler_operation.csv'
        ]

        chp1 = chp.Chp(
            'chp1', chp_filepaths
        )

        boiler1 = boiler.Boiler(
            'boiler1', boiler_filepaths
        )

        heat_storage1 = heat_storage.HeatStorage(
            'heat_storage1', self.PATH_IN + '/assets/heat_storage.csv'
        )

        ngas_grid = grid.NGasGrid('ngas_grid')

        power_grid = grid.ElectricalGrid(
            'power_grid', self.PATH_IN + '/assets/power_grid.csv'
        )

        heat_grid = grid.HeatGrid(
            'heat_grid', self.PATH_IN + '/assets/heat_grid.csv'
        )

        for asset in [chp1, boiler1, heat_storage1, ngas_grid, power_grid, heat_grid]:
            asset.add_to_model(self.model)

    
    def _define_expressions(self):
        """Define model expressions"""
        
        def first_stage_cost_rule(model):
            return quicksum(model.chp1.gas[t] * model.price for t in model.t)
        self.model.first_stage_cost = Expression(rule=first_stage_cost_rule)

        def second_stage_cost_rule(model):  
            return 2
        self.model.second_stage_cost = Expression(rule=second_stage_cost_rule)
    
    # __________________________________________________________________________

    
    def add_objective(self):
        """Add objective function to model."""
        def objective_expression_rule(model):
            return model.first_stage_cost + model.second_stage_cost
        self.model.objective = Objective(rule=objective_expression_rule,sense=maximize)  

    def load_timeseries_data(self):
        """Load timeseries data from file."""
        self.timeseries_data = DataPortal()
        self.timeseries_data.load(
            filename=self.PATH_IN + '/demands/heat_demand_20230401.csv',
            index='t',
            param='heat_demand'
        )

    def set_solver(self, solver_name, **kwargs):
        """Set solver for the model."""
        self.solver = SolverFactory(solver_name)
        for key in kwargs:
            self.solver.options[key] = kwargs[key]    

    def scenario_creator(self, scenario_name, use_integer=False, sense=pyo.minimize, crops_multiplier=1, num_scens=None):
        """Erstellt die Szenarien für das Modell."""
        #Erstelle die konkrete Instanz des Modells
        
        scennum = sputils.extract_num(scenario_name)
        basenames = ['FirstScenario', 'SecondScenario', 'ThirdScenario']
        basenum = scennum % 3
        groupnum = scennum // 3
        scenname = basenames[basenum] + str(groupnum)
        scenario_base_name = scenname.rstrip('1234567890')


        # Szenario-spezifische Initialisierungen
        price = {
            'FirstScenario':  0.1541,
            'SecondScenario': 0.1542,
            'ThirdScenario': 0.1543
        }

        # def price_init(model):
        #     price_base_name = 'GAS_PRICE'
        #     print("price[scenario_base_name][price_base_name]", price[scenario_base_name][price_base_name])
        #     return price[scenario_base_name][price_base_name]

        print(f"Price for {scenario_base_name}: {price[scenario_base_name]}")
        self.model.price = Param(within=NonNegativeReals, initialize=price[scenario_base_name], mutable=True)

        self.instance = self.model.create_instance(self.timeseries_data)
        
        if num_scens is not None:
            self.instance._mpisppy_probability = 1 / num_scens

        # Variable mit Index t anlegen
        varlist = [self.instance.chp1.gas]
        sputils.attach_root_node(self.instance, self.instance.first_stage_cost, varlist)

        print("Writing instance output.txt ...")
        with open('output.txt', 'w') as f:
            self.instance.pprint(ostream=f)

        print("____________________________________")
        print("Model instance created successfully.")
        print("First stage cost expression:", self.instance.first_stage_cost.expr)
        print("Price parameter value:", pyo.value(self.instance.price))
        print("____________________________________")

        with open('constraints_output.txt', 'w') as f:
            # Iteriere über alle aktiven Constraints in der Modellinstanz
            for con in self.instance.component_objects(Constraint, active=True):
                # Schreibe den Namen der Constraint-Komponente in die Datei
                f.write(f"Constraint: {con.name}\n")
                f.write("Details:\n")
                # Nutze pprint, um die Details der Constraint in die Datei zu schreiben
                con.pprint(ostream=f)
                f.write("____________________________________\n")
        
        
        
        return self.instance


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

    def expand_arcs(self):
        """Expands arcs and generate connection constraints."""
        TransformationFactory('network.expand_arcs').apply_to(self.instance)

       
    def create_extensive_form2(self,options , all_scenario_names, scenario_creator_kwargs):
        """Create the extensive form."""
        self.ef_instance = ExtensiveForm(
            options = options,
            all_scenario_names=all_scenario_names,
            scenario_creator=self.scenario_creator,
            scenario_creator_kwargs=scenario_creator_kwargs
        )
        return self.ef_instance
    
    def solve2(self):
        """Solve the model."""
        self.results = self.ef_instance.solve_extensive_form()


    def write_results(self):
        """Write results to file."""

        # self.results.write()

        # df_params = pd.DataFrame()
        # df_vars = pd.DataFrame()
        # df_output = pd.DataFrame()

        # for params in self.ef_instance.component_objects(Param, active=True):
        #     name = params.name
        #     if len(params) == 1:
        #         single_value = value(list(params.values())[0])
        #         df_params[name]= [single_value for t in self.instance.t]
        #     else:                        
        #         df_params[name] = [value(params[t]) for t in self.instance.t]
    
        # # for vars in self.ef_instance.component_objects(Var, active = True):
        # #     name = vars.name
        # #     df_vars[name] = [value(vars[t]) for t in self.instance.t]

        solution = self.ef_instance.get_root_solution()
        for [var_name, var_val] in solution.items():
            print(var_name, var_val)



        # df_output = pd.concat([df_params, df_vars], axis=1)
        # df_output.index = self.instance.t
        # df_output.index.name = 't'

        # self.results_data = df_params
    
    
    def save_results(self, filename):
        self.results_data.to_csv(filename, index=False)