import pandas as pd 

from pyomo.environ import *
from pyomo.network import * 

class HeatStorage:

    def __init__(self, name, filepath, index_col=0):
        self.name = name
        self.get_data = (filepath, index_col)

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
        asset.bin_charge = Var(t, within=Binary)
        asset.bin_discharge = Var(t, within=Binary)
        asset.heat_charge = Var(t, within=NonNegativeReals)
        asset.heat_discharge = Var(t, within=NonNegativeReals)
        asset.heat_capacity = Var(within=NonNegativeReals)
        asset.heat_balance = Var(t, within=Reals)


        asset.heat_in = Port()
        asset.heat_in_add(
            asset.heat_charge,
            'heat',
            Port.Extensive,
            include_splitfrac=True
        )

        asset.heat_out = Port()
        asset.heat_out_add(
            asset.heat_discharge,
            'heat',
            Port.Extensive,
            include_splitfrac=True
        )   

        # Declare construction rules for components
        def max_heat_charge_rule(asset, t):
            """Maximum heat charge constraint"""
            return asset.heat_charge[t] <= self.data.loc['max', 'charge']*asset.bin_charge[t]
        asset.max_heat_charge_constr = Constraint(t, rule=max_heat_charge_rule)

        def max_heat_discharge_rule(asset, t):
            """Maximum heat discharge constraint"""
            return asset.heat_discharge[t] <= self.data.loc['max', 'discharge']*asset.bin_discharge[t]
        asset.max_heat_discharge_constr = Constraint(t, rule=max_heat_discharge_rule)

        def max_heat_capacity(asset, t):
            """Maximum heat capacity constraint"""
            return asset.heat_capacity[t] <= self.data.loc['max', 'capacity']
        asset.max_heat_capacity_constr = Constraint(t, rule=max_heat_capacity)

        def heat_balance_rule(asset, t):
            """Heat balance constraint"""
            return asset.heat_balance[t] == asset.heat_discharge[t]  - asset.heat_charge[t]
        asset.heat_balance_constr = Constraint(t, rule=heat_balance_rule)
        
        def capacity_balance_rule(asset, t):
            """Capacity balance constraint, heat capacity is the difference between the initial capacity and the heat balance at time t"""
            if t == 1:
                #return asset.heat_capacity[t] == self.data.loc['initial', 'capacity'] - asset.heat_balance[t]
                return asset.heat_capacity[t] == 10 - asset.heat_balance[t] 
            else:
                return asset.heat_capacity[t] == asset.heat_capacity[t-1] - asset.heat_balance[t]
        asset.capacity_balance_constr = Constraint(t, rule=capacity_balance_rule)

        def charge_discharge_rule(asset, t):
            """Charge and discharge constraint, only one of them can be used at a time"""
            return asset.bin_charge[t] + asset.bin_discharge[t] <= 1
        asset.charge_discharge_constr = Constraint(t, rule=charge_discharge_rule)



   