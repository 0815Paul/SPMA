import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class Boiler:
    """Boiler class"""

    def __init__(self, name, filepath, index_col=0, **kwargs):
        self.name = name
        self.get_data(filepath, index_col)
        # leave **kwargs for future use

    def get_data(self, filepath, index_col):
        self.data = pd.read_csv(
            filepath,
            index_col=index_col
        )
    
    def add_to_model(self, model):
        model.add_component(
            self.name,
            Block(rule=self.boiler_block_rule)
        )

    def boiler_block_rule(self, asset):

        # Get index from model
        t = asset.model().t

        # Declare components
        asset.bin = Var(t, within=Binary)
        asset.heat = Var(t, domain=NonNegativeReals)
        asset.gas = Var(t, domain=NonNegativeReals)
        asset.eta_th = Var(t, domain=NonNegativeReals)

       # Binary variable for Big-M constraints
        asset.y1 = Var(t, domain=Binary)
        asset.y2 = Var(t, domain=Binary)

        asset.heat_out = Port()
        asset.heat_out.add(
            asset.heat,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        asset.gas_in = Port()
        asset.gas_in.add(
            asset.gas,
            'gas',
            Port.Extensive,
            include_splitfrac=False
        )

        boiler_op_data = self.data

        # Heat
        heat_1 = boiler_op_data.loc[1, 'heat']
        heat_2 = boiler_op_data.loc[2, 'heat']
        heat_3 = boiler_op_data.loc[3, 'heat']

        # eta_th
        eta_th_1 = boiler_op_data.loc[1, 'eta_th']
        eta_th_2 = boiler_op_data.loc[2, 'eta_th']
        eta_th_3 = boiler_op_data.loc[3, 'eta_th']

        # Gas
        gas_1 = heat_1 / eta_th_1
        gas_2 = heat_2 / eta_th_2
        gas_3 = heat_3 / eta_th_3

        # print("Gas Boiler :", gas_1, gas_2, gas_3)
        # print("Heat Boiler:", heat_1, heat_2, heat_3)
        # print("eta_th Boiler:", eta_th_1, eta_th_2, eta_th_3)

        # Constraints

        def thermal_load_max_rule(asset, t):
            """Maximum heat production constraint"""
            return asset.heat[t] <= heat_3*asset.bin[t]
        asset.max_heat_constr = Constraint(t, rule=thermal_load_max_rule)

        def thermal_load_min_rule(asset, t):
            """Minimum heat production constraint"""
            return heat_1*asset.bin[t] <= asset.heat[t]
        asset.min_heat_constr = Constraint(t, rule=thermal_load_min_rule)


        # Helper function
        def linear_function(x, x1, x2, y1, y2):
            """Helper function for linear interpolation."""
            a = (y2 - y1) / (x2 - x1)
            b = y1 - a * x1
            return a * x + b 
        
        # Big-M Parameter
        M = 1e5

        def y_activation_constraint(asset, t):
            """Ensures that y1 and y2 sum up to bin"""
            return asset.y1[t] + asset.y2[t] == asset.bin[t]
        asset.y_activation_constr = Constraint(t, rule=y_activation_constraint)

        # Constraints for heat depending on y1 and y2
        def heat_upper_bound_y1_constraint(asset, t):
            """Upper bound on heat when y1 is active"""
            return asset.heat[t] <= heat_2 * asset.y1[t]
        asset.heat_upper_bound_y1_constr = Constraint(t, rule=heat_upper_bound_y1_constraint)

        def heat_lower_bound_y2_constraint(asset, t):
            """Lower bound on heat when y2 is active"""
            return asset.heat[t] >= heat_2 * asset.y2[t]
        asset.heat_lower_bound_y2_constr = Constraint(t, rule=heat_lower_bound_y2_constraint)

        # Constraints for gas consumption depending on thermal load

        # Upper bounds
        def gas_upper_bound_y1_constraint(asset, t):
            """Upper bound on gas consumption in region 1"""
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.gas_upper_bound_y1_constr = Constraint(t, rule=gas_upper_bound_y1_constraint)

        def gas_upper_bound_y2_constraint(asset, t):
            """Upper bound on gas consumption in region 2"""
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) + M * (1 - asset.y2[t])) * asset.bin[t]
        asset.gas_upper_bound_y2_constr = Constraint(t, rule=gas_upper_bound_y2_constraint)

        # Lower bounds
        def gas_lower_bound_y1_constraint(asset, t):
            """Lower bound on gas consumption in region 1"""
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2) - M * (1 - asset.y1[t])) * asset.bin[t]
        asset.gas_lower_bound_y1_constr = Constraint(t, rule=gas_lower_bound_y1_constraint)

        def gas_lower_bound_y2_constraint(asset, t):
            """Lower bound on gas consumption in region 2"""
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) - M * (1 - asset.y2[t])) * asset.bin[t]
        asset.gas_lower_bound_y2_constr = Constraint(t, rule=gas_lower_bound_y2_constraint)

        # Constraints for thermal efficiency depending on thermal load

        # Upper bounds
        def eta_th_upper_bound_y1_constraint(asset, t):
            """Upper bound on thermal efficiency in region 1"""
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.eta_th_upper_bound_y1_constr = Constraint(t, rule=eta_th_upper_bound_y1_constraint)

        def eta_th_upper_bound_y2_constraint(asset, t):
            """Upper bound on thermal efficiency in region 2"""
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) + M * (1 - asset.y2[t])) * asset.bin[t]
        asset.eta_th_upper_bound_y2_constr = Constraint(t, rule=eta_th_upper_bound_y2_constraint)

        # Lower bounds
        def eta_th_lower_bound_y1_constraint(asset, t):
            """Lower bound on thermal efficiency in region 1"""
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2) - M * (1 - asset.y1[t])) * asset.bin[t]
        asset.eta_th_lower_bound_y1_constr = Constraint(t, rule=eta_th_lower_bound_y1_constraint)

        def eta_th_lower_bound_y2_constraint(asset, t):
            """Lower bound on thermal efficiency in region 2"""
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) - M * (1 - asset.y2[t])) * asset.bin[t]
        asset.eta_th_lower_bound_y2_constr = Constraint(t, rule=eta_th_lower_bound_y2_constraint)
       
