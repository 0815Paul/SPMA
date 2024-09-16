import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class ElectricalGrid:
    """"Electrical Grid class"""
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
            Block(rule=self.electrical_grid_block_rule)
        )

    def electrical_grid_block_rule(self, asset):
        
        # Get index from model
        t = asset.model().t

        # Declare components
        asset.power_balance = Var(t, within=Reals)
        asset.power_supply = Var(t, within=NonNegativeReals)
        asset.power_feedin = Var(t, within=NonNegativeReals)


        asset.power_in = Port()
        asset.power_in.add(
            asset.power_feedin,
            'power',
            Port.Extensive,
            include_splitfrac=False
        )
        asset.power_out = Port()
        asset.power_out.add(
            asset.power_supply,
            'power',
            Port.Extensive,
            include_splitfrac=False
        )

        def max_power_supply_rule(asset, t):
            """Maximum power supply constraint"""
            return asset.power_supply[t] <= self.data.loc['max', 'power']
        asset.max_power_supply_constr = Constraint(t, rule=max_power_supply_rule)

        def max_power_feedin_rule(asset, t):
            """Maximum power feed-in constraint"""
            return asset.power_feedin[t] <= self.data.loc['max', 'power']
        asset.max_power_feedin_constr = Constraint(t, rule=max_power_feedin_rule)

        def power_balance_rule(asset, t):
            """ Power balance = power supply - power feed-in"""
            return asset.power_balance[t] == asset.power_supply[t] - asset.power_feedin[t]
        asset.power_balance_constr = Constraint(t, rule=power_balance_rule)


class NGasGrid:
    """"Natural Gas Grid class"""
    def __init__(self, name):
        self.name = name
    
    def add_to_model(self, model):
        model.add_component(
            self.name,
            Block(rule=self.ngas_grid_block_rule)
        )

    def ngas_grid_block_rule(self, asset):
        
        # Get index from model
        t = asset.model().t

        # Declare components
        asset.gas_balance = Var(t, within=Reals)

        asset.gas_out = Port()
        asset.gas_out.add(
            asset.gas_balance,
            'gas',
            Port.Extensive,
            include_splitfrac=False
        )

class HeatGrid:
    """"Heat Grid class"""
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
            Block(rule=self.heat_grid_block_rule)
        )

    def heat_grid_block_rule(self, asset):
        
        # Get index from model
        t = asset.model().t

        # Declare components
        asset.heat_balance = Var(t, within=NonNegativeReals)
        asset.heat_supply = Var(t, within=NonNegativeReals)
        asset.heat_feedin = Var(t, within=NonNegativeReals)
        
        # Declare ports
        asset.heat_in = Port()
        asset.heat_in.add(
            asset.heat_feedin,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )
        asset.heat_out = Port()
        asset.heat_out.add(
            asset.heat_supply,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        # Declare constraints
        def heat_balance_rule(asset, t):
            return asset.heat_balance[t] ==  asset.heat_feedin[t] - asset.heat_supply[t]
        asset.heat_balance_constr = Constraint(t, rule=heat_balance_rule)

        def supply_heat_demand_rule(asset, t):
            """ Supply heat demand"""
            return asset.heat_balance[t] == 0
        asset.supply_heat_demand_constr = Constraint(t, rule=supply_heat_demand_rule)

        def heat_supply_rule(asset, t):
            """ Heat supply"""
            #print("heat_supply:",asset.heat_supply[t])
            return asset.heat_supply[t] == asset.model().heat_demand[t]
        asset.heat_supply_constr = Constraint(t, rule=heat_supply_rule)

      