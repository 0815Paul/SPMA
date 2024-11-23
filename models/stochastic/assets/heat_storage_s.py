import pandas as pd 
from pyomo.environ import *
from pyomo.network import * 

class HeatStorage:

    def __init__(self, name, filepath, index_col=0):
        self.name = name
        self.get_data(filepath, index_col)

    def get_data(self, filepath, index_col):
        self.data = pd.read_csv(
            filepath,
            index_col=index_col
        )

    def add_to_model(self, model):
        model.add_component(
            self.name,
            Block(rule=self.heat_storage_block_rule)
        )
    
    def heat_storage_block_rule(self, asset):

        # Get index from model
        t = asset.model().t

        # Declare components
        asset.heat_charge = Var(t, within=NonNegativeReals)
        asset.bin_charge = Var(t, within=Binary)
        asset.heat_discharge = Var(t, within=NonNegativeReals)
        asset.bin_discharge = Var(t, within=Binary)
        asset.heat_balance = Var(t, within=Reals)
        asset.heat_capacity = Var(t, within=NonNegativeReals)

        # Declare Params
        asset.initial_soc = Param(initialize=self.data.loc['max', 'content']*0.8)
        
        # Second Stage Components
        asset.dispatch_heat_capacity = Var(t, within=NonNegativeReals)
        asset.dispatch_heat_charge = Var(t, within=NonNegativeReals)
        asset.dispatch_heat_discharge = Var(t, within=NonNegativeReals)
        asset.dispatch_storage_capacity = Var(t, within=NonNegativeReals)
        asset.dispatch_extension = Var(t, within=NonNegativeReals)
        
        # Binary variable to control extension usage
        asset.use_extension = Var(t, within=Binary)
        
        # Parameters for big-M method
        epsilon = 1e-6  # Small positive value
        M = 1e6  # Large positive value (adjust as needed)

        asset.heat_in = Port()
        asset.heat_in.add(
            asset.heat_charge,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        asset.heat_out = Port()
        asset.heat_out.add(
            asset.heat_discharge,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        # Declare construction rules for components
        def max_heat_charge_rule(asset, t):
            """Maximum heat charge constraint"""
            return asset.heat_charge[t] <= self.data.loc['max', 'heat'] * asset.bin_charge[t]
        asset.max_heat_charge_constr = Constraint(t, rule=max_heat_charge_rule)

        def max_heat_discharge_rule(asset, t):
            """Maximum heat discharge constraint"""
            return asset.heat_discharge[t] <= self.data.loc['max', 'heat'] * asset.bin_discharge[t]
        asset.max_heat_discharge_constr = Constraint(t, rule=max_heat_discharge_rule)

        def max_heat_capacity(asset, t):
            """Maximum heat capacity constraint"""
            return asset.heat_capacity[t] <= self.data.loc['max', 'content']
        asset.max_heat_capacity_constr = Constraint(t, rule=max_heat_capacity)

        def min_heat_capacity(asset, t):
            """Minimum heat capacity constraint"""
            return asset.heat_capacity[t] >= self.data.loc['min', 'content']
        asset.min_heat_capacity_constr = Constraint(t, rule=min_heat_capacity)

        def heat_balance_rule(asset, t):
            """Heat balance constraint"""
            return asset.heat_balance[t] == asset.heat_discharge[t] - asset.heat_charge[t]
        asset.heat_balance_constr = Constraint(t, rule=heat_balance_rule)
        
        def capacity_balance_rule(asset, t):
            """Capacity balance constraint"""
            if t == 1:
                return asset.heat_capacity[t] == asset.initial_soc - asset.heat_balance[t] 
            else:
                return asset.heat_capacity[t] == asset.heat_capacity[t-1] - asset.heat_balance[t]
        asset.capacity_balance_constr = Constraint(t, rule=capacity_balance_rule)

        def charge_discharge_binary_rule(asset, t):
            """Charge and discharge cannot happen simultaneously"""
            return asset.bin_charge[t] + asset.bin_discharge[t] <= 1
        asset.charge_discharge_constr = Constraint(t, rule=charge_discharge_binary_rule)

        def soc_cycle_rule(asset):
            """State of charge must be the same at the beginning and end"""
            return asset.heat_capacity[t.last()] == asset.heat_capacity[t.first()]
        asset.soc_cycle_constr = Constraint(rule=soc_cycle_rule)

        ##############################################################

        # Second Stage Constraints

        asset.dispatch_heat_in = Port()
        asset.dispatch_heat_in.add(
            asset.dispatch_heat_charge,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        asset.dispatch_heat_out = Port()
        asset.dispatch_heat_out.add(
            asset.dispatch_heat_discharge,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        # Maximum heat charge and discharge in the second stage
        def max_heat_charge_secondstage_rule(asset, t):
            """Second Stage Maximum heat charge constraint"""
            return (asset.heat_charge[t] + asset.dispatch_heat_charge[t]
                    <= self.data.loc['max', 'heat'])
        asset.max_heat_charge_secondstagerule = Constraint(t, rule=max_heat_charge_secondstage_rule)

        def max_heat_discharge_secondstage_rule(asset, t):
            """Second Stage Maximum heat discharge constraint"""
            return (asset.heat_discharge[t] + asset.dispatch_heat_discharge[t]
                    <= self.data.loc['max', 'heat'])
        asset.max_heat_discharge_secondstagerule = Constraint(t, rule=max_heat_discharge_secondstage_rule)

        # Capacity balance in the second stage
        # def capacity_balance_secondstage_rule(asset, t):
        #     """Second Stage Capacity balance constraint"""
        #     if t == 1:
        #         return (asset.dispatch_heat_capacity[t] == asset.initial_soc +
        #                 (asset.heat_charge[t] + asset.dispatch_heat_charge[t]) -
        #                 (asset.heat_discharge[t] + asset.dispatch_heat_discharge[t]))
        #     else:
        #         return (asset.dispatch_heat_capacity[t] == asset.dispatch_heat_capacity[t-1] +
        #                 (asset.heat_charge[t] + asset.dispatch_heat_charge[t]) -
        #                 (asset.heat_discharge[t] + asset.dispatch_heat_discharge[t]))
        # asset.capacity_balance_secondstage_rule = Constraint(t, rule=capacity_balance_secondstage_rule)

        # def capacity_balance_secondstage_rule(asset, t):
        #     """Second Stage Capacity balance constraint"""
        #     if t == 1:
        #         return asset.dispatch_heat_capacity[t] == asset.heat_capacity[t] + asset.dispatch_heat_charge[t] - asset.dispatch_heat_discharge[t]
        #     else:
        #         return asset.dispatch_heat_capacity[t] == asset.dispatch_heat_capacity[t-1] + asset.dispatch_heat_charge[t] - asset.dispatch_heat_discharge[t]
        # asset.capacity_balance_secondstage_rule = Constraint(t, rule=capacity_balance_secondstage_rule)

        def capacity_balance_secondstage_rule(asset, t):
            """Second Stage Capacity balance constraint"""
            return asset.dispatch_heat_capacity[t] == asset.heat_capacity[t] + asset.dispatch_heat_charge[t] - asset.dispatch_heat_discharge[t]
        asset.capacity_balance_secondstage_rule = Constraint(t, rule=capacity_balance_secondstage_rule)

        # Enforce that dispatch_heat_capacity[t] is the sum of storage and extension
        def extensible_capacity_secondstage_rule(asset, t):
            """Second Stage Extensible heat capacity constraint"""
            return (asset.dispatch_heat_capacity[t] ==
                    asset.dispatch_storage_capacity[t] + asset.dispatch_extension[t])
        asset.extensible_capacity_secondstage_rule = Constraint(t, rule=extensible_capacity_secondstage_rule)

        # Limit on storage capacity
        def max_storage_capacity_secondstage_rule(asset, t):
            """Second Stage Maximum storage capacity constraint"""
            return (asset.dispatch_storage_capacity[t] <= self.data.loc['max', 'content'])
        asset.max_storage_capacity_secondstage_rule = Constraint(t, rule=max_storage_capacity_secondstage_rule)

        # Enforce that extension is only used when storage capacity is at maximum
        def extension_usage_rule(asset, t):
            """Enforce extension usage only after storage capacity is maxed out"""
            return asset.dispatch_extension[t] <= M * asset.use_extension[t]
        asset.extension_usage_constr = Constraint(t, rule=extension_usage_rule)

        # Storage capacity must be at max before extension is used
        def storage_capacity_full_rule(asset, t):
            """Ensure storage capacity is full before using extension"""
            max_content = self.data.loc['max', 'content']
            return asset.dispatch_storage_capacity[t] >= max_content - M * (1 - asset.use_extension[t])
        asset.storage_capacity_full_constr = Constraint(t, rule=storage_capacity_full_rule)

        # Storage capacity cannot exceed maximum capacity
        def storage_capacity_limit_rule(asset, t):
            """Storage capacity limit considering epsilon"""
            max_content = self.data.loc['max', 'content']
            return asset.dispatch_storage_capacity[t] <= max_content - epsilon * asset.use_extension[t]
        asset.storage_capacity_limit_constr = Constraint(t, rule=storage_capacity_limit_rule)




        # Binary variable definition
        # Pyomo automatically handles binary variables, so no extra constraints are needed here

        # Non-negativity constraints are implicit in variable declarations
