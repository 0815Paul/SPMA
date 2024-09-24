import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class Chp:
    """Combined Heat and Power Plant (CHP) class"""

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
            Block(rule=self.chp_block_rule)
        )
    
    def chp_block_rule(self, asset):

        # Get index fom model
        t = asset.model().t

        # Declare components
        asset.bin = Var(t, within=Binary)
        asset.power = Var(t, domain=NonNegativeReals)
        asset.gas = Var(t, domain=NonNegativeReals)
        asset.heat = Var(t, domain=NonNegativeReals)
        asset.eta_th = Var(t, domain=NonNegativeReals)
        asset.eta_el = Var(t, domain=NonNegativeReals)
        
        # Binary variable for Big-M constraints
        asset.y1 = Var(t, domain=Binary)
        asset.y2 = Var(t, domain=Binary)

        # Second stage components

        # asset.dispatch_power = Var(t, domain=NonNegativeReals)
        # asset.dispatch_gas = Var(t, domain=NonNegativeReals)
        # asset.dispatch_heat = Var(t, domain=NonNegativeReals)
        # asset.dispatch_eta_th = Var(t, domain=NonNegativeReals)
        # asset.dispatch_eta_el = Var(t, domain=NonNegativeReals)
        
        # asset.dispatch_y1 = Var(t, domain=Binary)
        # asset.dispatch_y2 = Var(t, domain=Binary)
        # asset.dispatch_bin = Var(t, within=Binary)


        asset.power_out = Port()
        asset.power_out.add(
            asset.power,
            'power',
            Port.Extensive,
            include_splitfrac=False
        )

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
        
        chp_op_data = self.data

        # Heat
        heat_1 = chp_op_data.loc[1, 'heat']
        heat_2 = chp_op_data.loc[2, 'heat']
        heat_3 = chp_op_data.loc[3, 'heat']

        # eta_th
        eta_th_1 = chp_op_data.loc[1, 'eta_th']
        eta_th_2 = chp_op_data.loc[2, 'eta_th']
        eta_th_3 = chp_op_data.loc[3, 'eta_th']

        # eta_el
        eta_el_1 = chp_op_data.loc[1, 'eta_el']
        eta_el_2 = chp_op_data.loc[2, 'eta_el']
        eta_el_3 = chp_op_data.loc[3, 'eta_el']

        # Power 
        power_1 = eta_el_1 * (heat_1/eta_th_1)
        power_2 = eta_el_2 * (heat_2/eta_th_2)
        power_3 = eta_el_3 * (heat_3/eta_th_3)
            
        # Gas 
        gas_1 = heat_1/eta_th_1
        gas_2 = heat_2/eta_th_2
        gas_3 = heat_3/eta_th_3

        # print("Gas CHP :", gas_1, gas_2, gas_3)
        # print("Power CHP:", power_1, power_2, power_3)
        # print("Heat CHP:", heat_1, heat_2, heat_3)

        # Constraints

        def thermal_load_max_rule(asset, t):
            """Rule for the maximum thermal load."""
            thermal_load_max = chp_op_data.loc[3, 'heat']
            return asset.heat[t] <= thermal_load_max * asset.bin[t]
        asset.thermal_load_max_constr = Constraint(t, rule=thermal_load_max_rule)
    
        def thermal_load_min_rule(asset, t):
            """Rule for the minimum thermal load."""
            thermal_load_min = chp_op_data.loc[1, 'heat']
            return thermal_load_min * asset.bin[t] <= asset.heat[t]
        asset.thermal_load_min_constr = Constraint(t, rule=thermal_load_min_rule)

        def linear_function(x, x1, x2, y1, y2):
            """Helper function for linear interpolation."""
            a = (y2 - y1) / (x2 - x1)
            b = y1 - a * x1
            return a * x + b
            
        
        # Big-M
        M = 1e6
     

        def y_constraint1_upper(asset, t):
            """Big-M constraint 1 - upper bound"""
            return asset.y1[t] + asset.y2[t] == asset.bin[t]
        asset.y_constr1_upper = Constraint(t, rule=y_constraint1_upper)
    
        # Big-M constraints for gas consumption depending on the thermal load

        def gas_depends_on_thermal_load_rule2(asset, t):
            return asset.heat[t] <= heat_2 *asset.y1[t]
        asset.gas_depends_on_thermal_load2 = Constraint(t, rule=gas_depends_on_thermal_load_rule2)

        def gas_depends_on_thermal_load_rule3(asset, t):
            return asset.heat[t] >= heat_2 * asset.y2[t]
        asset.gas_depends_on_thermal_load3 = Constraint(t, rule=gas_depends_on_thermal_load_rule3)

        
        # Big-M constraints for power depending on thermal load

        # Upper bound
        def power_depends_on_thermal_load_constr1(asset, t):
            return asset.power[t] <= (linear_function(asset.heat[t], heat_1, heat_2, power_1, power_2)  + M * (1 - asset.y1[t]))*asset.bin[t]
        asset.power_depends_on_thermal_load1 = Constraint(t, rule=power_depends_on_thermal_load_constr1)

        def power_depends_on_thermal_load_constr2(asset, t):
            return asset.power[t] <= (linear_function(asset.heat[t], heat_2, heat_3, power_2, power_3) + M * (1 - asset.y2[t]))* asset.bin[t]
        asset.power_depends_on_thermal_load2 = Constraint(t, rule=power_depends_on_thermal_load_constr2)

        # Lower bound

        def power_depends_on_thermal_load_constr1_lower(asset, t):
            return asset.power[t] >= linear_function(asset.heat[t], heat_1, heat_2, power_1, power_2) - M * (1 - asset.y1[t])
        asset.power_depends_on_thermal_load1_lower = Constraint(t, rule=power_depends_on_thermal_load_constr1_lower)

        def power_depends_on_thermal_load_constr2_lower(asset, t): 
            return asset.power[t] >= linear_function(asset.heat[t], heat_2, heat_3, power_2, power_3) - M * (1 - asset.y2[t])
        asset.power_depends_on_thermal_load2_lower = Constraint(t, rule=power_depends_on_thermal_load_constr2_lower)
        
        # Big-M constraints for gas depending on thermal load
        
        # Upper bound
        def gas_depends_on_thermal_load_constr1(asset, t):
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.gas_depends_on_thermal_load1 = Constraint(t, rule=gas_depends_on_thermal_load_constr1)

        def gas_depends_on_thermal_load_constr2(asset, t):
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3)  + M * (1 - asset.y2[t])) *asset.bin[t]
        asset.gas_depends_on_thermal_load2 = Constraint(t, rule=gas_depends_on_thermal_load_constr2)
        
        # Lower bound
        def gas_depends_on_thermal_load_constr1_lower(asset, t):
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2)  - M * (1 - asset.y1[t])) *asset.bin[t]
        asset.gas_depends_on_thermal_load1_lower = Constraint(t, rule=gas_depends_on_thermal_load_constr1_lower)

        def gas_depends_on_thermal_load_constr2_lower(asset, t):
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) - M * (1 - asset.y2[t])) *asset.bin[t]
        asset.gas_depends_on_thermal_load2_lower = Constraint(t, rule=gas_depends_on_thermal_load_constr2_lower)

        # Big-M constraints for thermal efficiency depending on thermal load

        # Upper bound
        def thermal_efficiency_depends_on_thermal_load_constr1(asset, t):
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2) + M * (1 - asset.y1[t])) *asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load1 = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr1)
       
        def thermal_efficiency_depends_on_thermal_load_constr2(asset, t):
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) + M * (1 - asset.y2[t]))*asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load2 = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr2)

        # Lower bound
        def thermal_efficiency_depends_on_thermal_load_constr1_lower(asset, t):
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2) - M * (1 - asset.y1[t])) *asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load1_lower = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr1_lower)

        def thermal_efficiency_depends_on_thermal_load_constr2_lower(asset, t):
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) - M * (1 - asset.y2[t])) *asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load2_lower = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr2_lower)


        # Big-M constraints for electrical efficiency depending on thermal load
        
        # Upper bound
        def electrical_efficiency_depends_on_thermal_load_constr1(asset, t):
            return asset.eta_el[t] <= (linear_function(asset.heat[t], heat_1, heat_2, eta_el_1, eta_el_2) + M * (1 - asset.y1[t])) *asset.bin[t]
        asset.electrical_efficiency_depends_on_thermal_load1 = Constraint(t, rule=electrical_efficiency_depends_on_thermal_load_constr1)


        def electrical_efficiency_depends_on_thermal_load_constr2(asset, t):
            return asset.eta_el[t] <= (linear_function(asset.heat[t], heat_2, heat_3, eta_el_2, eta_el_3) + M * (1 - asset.y2[t]))*asset.bin[t]
        asset.electrical_efficiency_depends_on_thermal_load2 = Constraint(t, rule=electrical_efficiency_depends_on_thermal_load_constr2)

        # Lower bound
        def electrical_efficiency_depends_on_thermal_load_constr1_lower(asset, t):
            return asset.eta_el[t] >= (linear_function(asset.heat[t], heat_1, heat_2, eta_el_1, eta_el_2) - M * (1 - asset.y1[t])) *asset.bin[t]
        asset.electrical_efficiency_depends_on_thermal_load1_lower = Constraint(t, rule=electrical_efficiency_depends_on_thermal_load_constr1_lower)

        def electrical_efficiency_depends_on_thermal_load_constr2_lower(asset, t):
            return asset.eta_el[t] >= (linear_function(asset.heat[t], heat_2, heat_3, eta_el_2, eta_el_3) - M * (1 - asset.y2[t]))*asset.bin[t]
        asset.electrical_efficiency_depends_on_thermal_load2_lower = Constraint(t, rule=electrical_efficiency_depends_on_thermal_load_constr2_lower)

        ########################################## NOT IMPLEMENTED ##########################################

        # Second stage constraints
        # Dispatch constraints

        # asset.dispatch_heat_out = Port()
        # asset.dispatch_heat_out.add(
        #     asset.dispatch_heat,
        #     'heat',
        #     Port.Extensive,
        #     include_splitfrac=False
        # )

        # asset.dispatch_power_out = Port()
        # asset.dispatch_power_out.add(
        #     asset.dispatch_power,
        #     'power',
        #     Port.Extensive,
        #     include_splitfrac=False
        # )

        # asset.dispatch_gas_in = Port()
        # asset.dispatch_gas_in.add(
        #     asset.dispatch_gas,
        #     'gas',
        #     Port.Extensive,
        #     include_splitfrac=False
        # )
        
        # def dispatch_y_constraint1_upper(asset, t):
        #     """Big-M constraint 1 - upper bound"""
        #     return asset.dispatch_y1[t] + asset.dispatch_y2[t] == asset.dispatch_bin[t]
        # asset.y_constr1_upper = Constraint(t, rule=dispatch_y_constraint1_upper)


        # def dispatch_thermal_load_max_rule(asset, t):
        #     """Rule for the maximum thermal load."""
        #     thermal_load_max = chp_op_data.loc[3, 'heat']
        #     return asset.heat[t] + asset.dispatch_heat[t] <= thermal_load_max * asset.dispatch_bin[t]
        # asset.thermal_load_max_constr = Constraint(t, rule=dispatch_thermal_load_max_rule)

        # def dispatch_thermal_load_min_rule(asset, t):
        #     """Rule for the minimum thermal load."""
        #     thermal_load_min = chp_op_data.loc[1, 'heat']
        #     return thermal_load_min * asset.dispatch_bin[t] <= asset.heat[t] + asset.dispatch_heat[t]
        # asset.thermal_load_min_constr = Constraint(t, rule=dispatch_thermal_load_min_rule)

        # def dispatch_gas_depends_on_thermal_load_rule2(asset, t):
        #     return asset.heat[t] + asset.dispatch_heat[t] <= heat_2 *asset.dispatch_y1[t]
        # asset.gas_depends_on_thermal_load2 = Constraint(t, rule=dispatch_gas_depends_on_thermal_load_rule2)
    

        # def dispatch_gas_depends_on_thermal_load_rule3(asset, t):
        #     return asset.heat[t] + asset.dispatch_heat[t] >= heat_2 * asset.dispatch_y2[t]
        # asset.gas_depends_on_thermal_load3 = Constraint(t, rule=dispatch_gas_depends_on_thermal_load_rule3)

        # # Upper bound
        # def dispatch_power_depends_on_thermal_load_constr1(asset, t):
        #     return asset.power[t] + asset.dispatch_power[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, power_1, power_2)  + M * (1 - asset.dispatch_y1[t]))*asset.dispatch_bin[t]
        # asset.power_depends_on_thermal_load1 = Constraint(t, rule=dispatch_power_depends_on_thermal_load_constr1)

        # def dispatch_power_depends_on_thermal_load_constr2(asset, t):
        #     return asset.power[t] + asset.dispatch_power[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, power_2, power_3) + M * (1 - asset.dispatch_y2[t]))* asset.dispatch_bin[t]
        # asset.power_depends_on_thermal_load2 = Constraint(t, rule=dispatch_power_depends_on_thermal_load_constr2)

        # # ______ Lower Bound Constraints for gas consumption depending on the thermal load ______

        # def dispatch_power_depends_on_thermal_load_constr1_lower(asset, t):
        #     return asset.power[t] + asset.dispatch_power[t] >= linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, power_1, power_2) - M * (1 - asset.dispatch_y1[t])
        # asset.power_depends_on_thermal_load1_lower = Constraint(t, rule=dispatch_power_depends_on_thermal_load_constr1_lower)

        # def dispatch_power_depends_on_thermal_load_constr2_lower(asset, t): 
        #     return asset.power[t] + asset.dispatch_power[t] >= linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, power_2, power_3) - M * (1 - asset.dispatch_y2[t])
        # asset.power_depends_on_thermal_load2_lower = Constraint(t, rule=dispatch_power_depends_on_thermal_load_constr2_lower)

        
        # # Big-M constraints for gas depending on thermal load
        
        # # Upper bound
        # def dispatch_gas_depends_on_thermal_load_constr1(asset, t):
        #     return asset.gas[t] + asset.dispatch_gas[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, gas_1, gas_2) + M * (1 - asset.dispatch_y1[t])) * asset.dispatch_bin[t]
        # asset.gas_depends_on_thermal_load1 = Constraint(t, rule=dispatch_gas_depends_on_thermal_load_constr1)

        # def dispatch_gas_depends_on_thermal_load_constr2(asset, t):
        #     return asset.gas[t] + asset.dispatch_gas[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, gas_2, gas_3)  + M * (1 - asset.dispatch_y2[t])) *asset.dispatch_bin[t]
        # asset.gas_depends_on_thermal_load2 = Constraint(t, rule=dispatch_gas_depends_on_thermal_load_constr2)
        
        # # Lower bound
        # def dispatch_gas_depends_on_thermal_load_constr1_lower(asset, t):
        #     return asset.gas[t] + asset.dispatch_gas[t] >= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, gas_1, gas_2)  - M * (1 - asset.dispatch_y1[t])) *asset.dispatch_bin[t]
        # asset.gas_depends_on_thermal_load1_lower = Constraint(t, rule=dispatch_gas_depends_on_thermal_load_constr1_lower)

        # def dispatch_gas_depends_on_thermal_load_constr2_lower(asset, t):
        #     return asset.gas[t] + asset.dispatch_gas[t] >= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, gas_2, gas_3) - M * (1 - asset.dispatch_y2[t])) *asset.dispatch_bin[t]
        # asset.gas_depends_on_thermal_load2_lower = Constraint(t, rule=dispatch_gas_depends_on_thermal_load_constr2_lower)

        #  # Big-M constraints for thermal efficiency depending on thermal load

        # # Upper bound
        # def dispatch_thermal_efficiency_depends_on_thermal_load_constr1(asset, t):
        #     return asset.dispatch_eta_th[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, eta_th_1, eta_th_2) + M * (1 - asset.dispatch_y1[t])) *asset.dispatch_bin[t]
        # asset.thermal_efficiency_depends_on_thermal_load1 = Constraint(t, rule=dispatch_thermal_efficiency_depends_on_thermal_load_constr1)
       
        # def dispatch_thermal_efficiency_depends_on_thermal_load_constr2(asset, t):
        #     return asset.dispatch_eta_th[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, eta_th_2, eta_th_3) + M * (1 - asset.dispatch_y2[t]))*asset.dispatch_bin[t]
        # asset.thermal_efficiency_depends_on_thermal_load2 = Constraint(t, rule=dispatch_thermal_efficiency_depends_on_thermal_load_constr2)

        # # Lower bound
        # def dispatch_thermal_efficiency_depends_on_thermal_load_constr1_lower(asset, t):
        #     return asset.dispatch_eta_th[t] >= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, eta_th_1, eta_th_2) - M * (1 - asset.dispatch_y1[t])) *asset.dispatch_bin[t]
        # asset.thermal_efficiency_depends_on_thermal_load1_lower = Constraint(t, rule=dispatch_thermal_efficiency_depends_on_thermal_load_constr1_lower)

        # def dispatch_thermal_efficiency_depends_on_thermal_load_constr2_lower(asset, t):
        #     return asset.dispatch_eta_th[t] >= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, eta_th_2, eta_th_3) - M * (1 - asset.dispatch_y2[t])) *asset.dispatch_bin[t]
        # asset.thermal_efficiency_depends_on_thermal_load2_lower = Constraint(t, rule=dispatch_thermal_efficiency_depends_on_thermal_load_constr2_lower)
   
        # # Upper bound
        # def dispatch_electrical_efficiency_depends_on_thermal_load_constr1(asset, t):
        #     return asset.dispatch_eta_el[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, eta_el_1, eta_el_2) + M * (1 - asset.dispatch_y1[t])) *asset.dispatch_bin[t]
        # asset.electrical_efficiency_depends_on_thermal_load1 = Constraint(t, rule=dispatch_electrical_efficiency_depends_on_thermal_load_constr1)


        # def dispatch_electrical_efficiency_depends_on_thermal_load_constr2(asset, t):
        #     return asset.dispatch_eta_el[t] <= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, eta_el_2, eta_el_3) + M * (1 - asset.dispatch_y2[t]))*asset.dispatch_bin[t]
        # asset.electrical_efficiency_depends_on_thermal_load2 = Constraint(t, rule=dispatch_electrical_efficiency_depends_on_thermal_load_constr2)

        # # Lower bound
        # def dispatch_electrical_efficiency_depends_on_thermal_load_constr1_lower(asset, t):
        #     return asset.dispatch_eta_el[t] >= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_1, heat_2, eta_el_1, eta_el_2) - M * (1 - asset.dispatch_y1[t])) *asset.dispatch_bin[t]
        # asset.electrical_efficiency_depends_on_thermal_load1_lower = Constraint(t, rule=dispatch_electrical_efficiency_depends_on_thermal_load_constr1_lower)

        # def dispatch_electrical_efficiency_depends_on_thermal_load_constr2_lower(asset, t):
        #     return asset.dispatch_eta_el[t] >= (linear_function(asset.heat[t] + asset.dispatch_heat[t], heat_2, heat_3, eta_el_2, eta_el_3) - M * (1 - asset.dispatch_y2[t]))*asset.dispatch_bin[t]
        # asset.electrical_efficiency_depends_on_thermal_load2_lower = Constraint(t, rule=dispatch_electrical_efficiency_depends_on_thermal_load_constr2_lower)

        #######################################################################################################