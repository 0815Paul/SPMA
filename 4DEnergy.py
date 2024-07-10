import pandas as pd

from pyomo.opt import SolverFactory
from pyomo.environ import *
from pyomo.network import *

import assets.chp as chp
import assets.boiler as boiler
import assets.heat_storage as heat_storage
import assets.grid as grid


# Path
PATH_IN = 'data/input/'
PATH_OUT = 'data/output/'

# Declare constants


class Model:
    
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
        self.timeseries_data = DataPortal()

        self.timeseries.load(
            filename=PATH_IN + '',
            index='t',
            Param='gas_price',
        )

        self.timeseries.load(
            filename=PATH_IN + '',
            index='t',
            Param='power_price',
        )

        self.timeseries.load(
            filename=PATH_IN + '',
            index='t',
            Param='heat_demand',
        )
    
    def add_components(self):

        # Sets
        self.model.t = Set(orderd=True)

        # Parameters
        self.model.gas_price = Param(self.model.t)
        self.model.power_price = Param(self.model.t)
        self.model.heat_demand = Param(self.model.t)

        # Assets
        chp = chp.Chp(
            'chp', PATH_IN + '/assets/chp.csv'
        )

        boiler = boiler.Boiler(
            'boiler', PATH_IN + '/assets/boiler.csv',
        )

        heat_storage = heat_storage.HeatStorage(
            'heat_storage', PATH_IN + '/assets/heat_storage.csv',
        )

        ngas_grid = grid.NGasGrid(
            'ngas_grid', PATH_IN + '/assets/ngas_grid.csv',
        )

        power_grid = grid.ElectricalGrid(
            'power_grid', PATH_IN + '/assets/power_grid.csv',
        )

        heat_grid = grid.HeatGrid(
            'heat_grid', PATH_IN + '/assets/heat_grid.csv',
        )

        chp.add_to_model(self.model)
        boiler.add_to_model(self.model)
        heat_storage.add_to_model(self.model)
        ngas_grid.add_to_model(self.model)
        power_grid.add_to_model(self.model)
        heat_grid.add_to_model(self.model)


    def add_objective(self):
        """Add objective function to model."""
        self.model.objective = Objective(
            rule=self.model.objective_expr,
            sense=minimize,
        )
    
    def instantiate_model(self):
        """Create a concrete instance of the model."""
        self.instance = self.model.create_instance(self.timeseries_data)

    
    def expand_arcs(self):
        """Expands arcs and generate connection constraints."""
        TransformationFactory('network.expand_arcs').apply_to(self.instance)
    
    def add_instance_components(self, component_name, component):
        """Add components to the instance."""
        self.instance.add_component(component_name, component)

    def add_arcs(self, arcs):
        """Add arcs to the instance."""
        self.instance.arc01 = Arc(
            source=self.instance.chp.power_out,
            destination=self.instance.power_grid.power_in,
        )
        self.instance.arc02 = Arc(
            source=self.instance.chp.heat_out,
            destination=self.instance.heat_storage.heat_in,
        )
        self.instance.arc03 = Arc(
            source=self.instance.heat_storage.heat_out,
            destination=self.instance.heat_grid.heat_in,
        )
        self.instance.arc04 = Arc(
            source=self.instance.boiler.heat_out,
            destination=self.instance.heat_grid.heat_in,
        )
        self.instance.arc05 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.boiler.natural_gas_in,
        )
        self.instance.arc06 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.chp.natural_gas_in,
        )

    def solve(self):
        """Solve the model."""
        self.results =self.solver.solve(
            self.instance,
            symbolic_solver_labels=True,
            tee=True,
            logfile=PATH_OUT + 'logfile.txt',
            load_solutions=True,
            report_timing=True,
        )
    
    def write_results(self):
        """Write results to file."""
        # empty for now
        pass

    def save_results(self, filepath):
        """Save results to object."""
        self.results_data.to_csv(filepath)

    def objective_expr(self, model):
        """Objective function expression."""
        objective_expr = (
        quicksum(model.gas_price[t] * model.ngas_grid.gas_balance[t] for t in model) +
        quicksum(model.power_price[t] * model.power_grid.power_balance[t] for t in model) +
        quicksum(model.heat_price[t] * model.heat_grid.heat_balance[t] for t in model) 
        )
        return objective_expr

        


    if name == "__main__":
        model = Model()

        print('Setting solver...')
        model.set_solver('gurobi')
        
        print('Loading timeseries data...')
        model.load_timeseries_data()

        print('Adding components...')
        model.add_components()

        print('Adding objective...')
        model.add_objective()

        print('Instantiating model...')
        model.instantiate_model()

        print('Declairing arcs...')
        model.add_arcs()
        model.expand_arcs()

        print('Solving model...')
        model.solve()

        print('Writing results...')
        model.write_results()
        model.save_results(PATH_OUT + 'results.csv')
    